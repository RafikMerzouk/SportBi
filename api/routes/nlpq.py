# api/routes/nlpq.py (contract: LLM retourne directement sql + chart + params)
import json
import logging
from fastapi import APIRouter, HTTPException, Body, Response
import pandas as pd
from ..models import RequestSpec, ChartSpec
from ..services.query import run_query_df
from ..services.charts import plot_chart
from ..services.llm_agent import call_openai_chat

router = APIRouter()
logger = logging.getLogger("nlpq")

SCHEMA_MAPPING = {
    "NBA": "nba",
    "Liqui Moly StarLigue": "lnh",
    "La Boulangère Wonderligue": "lbwl",
    "Premier League": "pl",
    "Ligue 1 McDonald's": "ligue1",
    "Bundesliga": "bl1",
    "Serie A": "sa",
    "LaLiga": "pd",
}

LEAGUE_ALIASES = {
    "nba": "NBA",
    "premier league": "Premier League",
    "pl": "Premier League",
    "ligue 1": "Ligue 1 McDonald's",
    "ligue1": "Ligue 1 McDonald's",
    "l1": "Ligue 1 McDonald's",
    "la liga": "LaLiga",
    "laliga": "LaLiga",
    "liga": "LaLiga",
    "bundesliga": "Bundesliga",
    "serie a": "Serie A",
    "starligue": "Liqui Moly StarLigue",
    "lnh": "Liqui Moly StarLigue",
    "lbwl": "La Boulangère Wonderligue",
}

def _align_chart_columns(df: pd.DataFrame, chart_spec: ChartSpec) -> ChartSpec:
    """Rend les noms de colonnes insensibles à la casse entre SQL et chart."""
    colmap = {c.lower(): c for c in df.columns}

    def _match(name: str | None):
        if name is None:
            return None
        return colmap.get(name.lower(), name)

    def _match_list(names):
        if names is None:
            return None
        if isinstance(names, list):
            return [_match(n) for n in names]
        return _match(names)

    chart_spec.x = _match(chart_spec.x)
    chart_spec.y = _match_list(chart_spec.y)
    chart_spec.series = _match(chart_spec.series)
    return chart_spec


def _normalize_league(name: str | None, default: str) -> str:
    if not name:
        name = default
    key = name.strip().lower()
    return LEAGUE_ALIASES.get(key, name)


@router.post("/nlpq", summary="Génère un graphique via agent LLM (renvoie un PNG)")
def nlpq(
    prompt: str = Body(..., embed=True, description="Prompt en langage naturel"),
    league: str = Body("NBA", embed=True, description="Nom de la ligue (fallback)"),
):
    try:
        # hints league/team via heuristique locale
        prompt_league = None
        try:
            from ..services.nlp_pipeline import analyze_prompt
            ana = analyze_prompt(prompt)
            prompt_league = ana.get("entity", {}).get("league")
            prompt_team = ana.get("entity", {}).get("name")
        except Exception:
            prompt_team = None

        hint_league = prompt_league or league
        user_prompt = prompt
        if hint_league or prompt_team:
            user_prompt += f"\nHINT: league={hint_league or ''}; team={prompt_team or ''}"

        # 1) Appel LLM qui doit renvoyer {sql, chart, params?, league?}
        base_prompt = user_prompt
        try:
            llm_resp = call_openai_chat(base_prompt)
        except HTTPException as e:
            # Si la réponse LLM n'était pas du JSON valide, on retente en forçant la consigne
            if "JSON parse error" in str(e.detail):
                fix_prompt = (
                    f"{base_prompt}\n"
                    "Ta réponse précédente n'était pas un JSON valide. "
                    "Réponds STRICTEMENT en JSON compact conforme au format attendu {sql, params, chart, league} sans markdown."
                )
                llm_resp = call_openai_chat(fix_prompt)
            else:
                raise

        last_error = None
        max_retries = 2  # total 3 tentatives avec la première
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "LLM response",
                    extra={
                        "attempt": attempt,
                        "prompt": base_prompt,
                        "llm_resp": llm_resp,
                    },
                )
            except Exception:
                pass
            # normalisation league
            resolved_league = _normalize_league(llm_resp.get("league"), hint_league or league)
            if resolved_league not in SCHEMA_MAPPING:
                raise HTTPException(status_code=400, detail=f"Ligue inconnue: {resolved_league}")
            schema = SCHEMA_MAPPING[resolved_league]

            sql = llm_resp.get("sql")
            chart_payload = llm_resp.get("chart")
            params = llm_resp.get("params") or {}
            if not sql or not chart_payload:
                raise HTTPException(status_code=400, detail="Réponse LLM invalide (sql ou chart manquant).")

            # Si le prompt ne mentionne aucune équipe, on rejette les réponses qui introduisent un filtre d'équipe
            if not prompt_team:
                has_team_param = any("team" in k for k in params.keys())
                has_team_filter = "teamName" in sql or "teamId" in sql
                if has_team_param or has_team_filter:
                    if attempt >= max_retries:
                        raise HTTPException(status_code=400, detail="Réponse LLM invalide: filtre d'équipe alors que le prompt ne mentionne pas d'équipe.")
                    correction_prompt = (
                        f"{base_prompt}\n"
                        f"Le prompt ne mentionne aucune équipe. Ta réponse introduit un filtre d'équipe (team*). "
                        f"Corrige en supprimant tout filtre d'équipe et agrège au niveau ligue uniquement. "
                        f"Rappels: reste sur la ligue {resolved_league}, pas de schéma préfixé, JSON strict."
                    )
                    llm_resp = call_openai_chat(correction_prompt)
                    continue

            try:
                chart_spec = ChartSpec(**chart_payload)
                spec = RequestSpec(sql=sql, params=params, chart=chart_spec, schema=schema)
                df = run_query_df(spec.sql, spec.params, schema=spec.schema)
            except Exception as e:
                last_error = str(e)
                if attempt >= max_retries:
                    raise HTTPException(status_code=400, detail=f"Erreur exécution requête après corrections: {last_error}")
                # Demande à l'agent de corriger la requête à partir de l'erreur SQL
                debug_json = json.dumps(
                    {"sql": sql, "params": params, "chart": chart_payload, "league": resolved_league},
                    ensure_ascii=False,
                )
                correction_prompt = (
                    f"{base_prompt}\n"
                    f"La tentative {attempt + 1} a échoué (ligue={resolved_league}).\n"
                    f"Erreur SQL: {last_error}\n"
                    f"JSON fourni: {debug_json}\n"
                    "Corrige la requête SQL (et params/chart si nécessaire) et renvoie STRICTEMENT le même format JSON attendu. "
                    f"Ne change pas de ligue (reste sur {resolved_league}). "
                    "Assure-toi de LEFT JOIN season s ON m.seasonId = s.seasonId avant d'utiliser s.seasonLabel (colonne existante, non préfixée), "
                    "et n'utilise jamais de préfixe de schéma."
                )
                llm_resp = call_openai_chat(correction_prompt)
                continue
            break  # succès

        if df.empty:
            df = pd.DataFrame([{"info": "Aucune donnée", "value": 0}])
            chart_spec = ChartSpec(type="bar", x="info", y="value", title="Aucune donnée disponible")
            png = plot_chart(df, chart_spec)
            return Response(content=png, media_type="image/png", headers={"Content-Disposition": 'inline; filename=\"nlpq.png\"'})

        chart_to_plot = _align_chart_columns(df, spec.chart)
        png = plot_chart(df, chart_to_plot)
        return Response(
            content=png,
            media_type="image/png",
            headers={"Content-Disposition": 'inline; filename=\"nlpq.png\"'}
        )
    except HTTPException:
        raise
    except Exception as e:  # catch-all pour éviter les 500 silencieux
        raise HTTPException(status_code=500, detail=f"Erreur interne nlpq: {e}")
