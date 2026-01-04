# api/services/llm_agent.py
from __future__ import annotations

import os
import json
import requests
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import HTTPException

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _load_init_sql() -> str:
    candidates = [
        Path(__file__).resolve().parents[2] / "db" / "init.sql",  # /app/db/init.sql si monté
        Path(__file__).resolve().parents[1] / "init.sql",         # fallback local
    ]
    for path in candidates:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                continue
    return "-- init.sql introuvable dans le conteneur, utiliser le schema résumé."


INIT_SQL_SNIPPET = _load_init_sql()

def call_openai_chat(prompt: str) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY manquant pour l'agent NLP.")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    # Contexte unique : tu dois renvoyer directement sql + chart + params (facultatif) + league (facultatif)
    sys_prompt = (
        "Tu es un assistant qui génère un JSON strict pour alimenter une API de rendering de graphiques.\n"
        "Travaille en deux étapes (raisonnement interne) :\n"
        "  1) Construire une requête SQL valide et sûre, compatible avec le schéma fourni.\n"
        "  2) Emballer cette requête dans le JSON final (et rien d'autre).\n"
        "Réponds UNIQUEMENT en JSON compact, sans texte, sans markdown.\n"
        "JSON attendu: {\"sql\": \"<requête SQL unique, sans point-virgule final>\", \"params\": {…}, \"chart\": {\"type\": \"bar|line|area|pie|scatter\", \"x\": \"<col ou null>\", \"y\": \"<col ou liste>\", \"series\": \"<col ou null>\", \"title\": \"<titre>\", \"options\": {\"orientation\": \"vertical|horizontal\", \"stacked\": false, \"theme\": \"light\"}}, \"league\": \"<nom ligue ou null>\"}\n"
        "Ligues supportées en base (leagueName): NBA, Liqui Moly StarLigue, La Boulangère Wonderligue, Premier League, Ligue 1 McDonald's, Bundesliga, Serie A, LaLiga.\n"
        "Schema principal (résumé init.sql) :\n"
        "  season(seasonId UUID PK, seasonLabel TEXT)\n"
        "  team(teamId UUID PK, teamName TEXT, leagueId UUID?)\n"
        "  match(matchId UUID PK, seasonId UUID FK->season, homeTeamId UUID FK->team, awayTeamId UUID FK->team, startDateMatch TIMESTAMP)\n"
        "  statName(statNameId UUID PK, statNameLib TEXT) ; 'SCORE' est le libellé pour les points/buts.\n"
        "  statTeamMatch(matchId UUID FK->match, teamId UUID FK->team, statNameId UUID FK->statName, value NUMERIC)\n"
        "Bonnes pratiques SQL :\n"
        "  - Toujours joindre statTeamMatch à statName en filtrant sn.statNameLib = 'SCORE' pour récupérer les points/buts.\n"
        "  - Pour les victoires par équipe : comparer home_score et away_score via une CTE scores (group by matchId) puis filtrer sur teamName ILIKE :team_pattern.\n"
        "  - Utiliser des alias cohérents (m=match, stm=statTeamMatch, sn=statName, s=season, t=team) et ne jamais inventer d'autres colonnes (ex: pas de seasonId sur statTeamMatch).\n"
        "  - Ne JAMAIS préfixer les tables avec un nom de schéma (ex: pas de LaLiga.season).\n"
        "  - Si tu utilises s.seasonLabel, assure-toi d'avoir LEFT JOIN season s ON m.seasonId = s.seasonId dans la requête finale.\n"
        "  - ALIAS obligatoire pour toutes les colonnes projetées : donne des noms simples en snake_case (ex: season, wins, goals) et réutilise EXACTEMENT ces noms dans le champ chart.x / chart.y.\n"
        "  - Pas de DDL/DML, pas de ';' final, une seule requête courte (ou 1 CTE max).\n"
        "Normalisation des clubs (pas de longue liste, juste des règles d'interprétation) :\n"
        "  - Si le prompt contient un diminutif ou surnom, déduis le club officiel de la ligue visée (ex: 'barca', 'barça', 'blaugrana' -> FC Barcelona en LaLiga ; 'psg' ou 'paris' -> Paris Saint-Germain ; 'om' -> Olympique de Marseille).\n"
        "  - Si ambigu (plusieurs clubs dans la même ville), choisis le club le plus célèbre sauf indication contraire, mais ne change pas de ligue hintée.\n"
        "Règles ligue/équipe :\n"
        "  - Si le prompt mentionne une ligue sans équipe, agrège au niveau ligue (ex: répartition issues = home_win/away_win/draw pour tous les matches de la ligue) et ne filtre aucune équipe.\n"
        "  - Si le prompt mentionne une équipe, filtre uniquement cette équipe dans la ligue hintée (teamName ILIKE :team_pattern) et reste dans le schéma sélectionné (pas de WHERE leagueName = ...).\n"
        "  - Toujours appliquer le scope de ligue via le schéma actif, sans ajouter de préfixe de schéma.\n"
        "Hints (league=..., team=...) seront fournis dans le prompt utilisateur : tu DOIS les respecter (ne change pas de ligue si elle est hintée).\n"
        "Si tu peux déduire la ligue depuis l'équipe (ex: Barcelona -> LaLiga, PSG -> Ligue 1 McDonald's), fais-le, mais ne contredis jamais un hint explicite.\n"
        "Mets params si besoin (ex: team_pattern), sinon un objet vide.\n"
        "init.sql complet:\n"
        f"{INIT_SQL_SNIPPET}\n"
    )
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=20)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse LLM invalide (JSON parse error).")


def normalize_llm_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Nettoie les champs inattendus et impose les clefs attendues
    intent = payload.get("intent")
    team = payload.get("team")
    league = payload.get("league")
    filters = payload.get("filters") or {}
    season_start = filters.get("season_start")
    season_end = filters.get("season_end")
    return {
        "intent": intent,
        "team": team,
        "league": league,
        "filters": {
            "season_start": season_start,
            "season_end": season_end,
        },
    }
