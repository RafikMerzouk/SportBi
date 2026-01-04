# api/services/nlp_pipeline.py
# Pipeline NLP modulaire (stub actuel, prêt pour extension embeddings/FAISS)
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import numpy as np
from .nlp_index import NLPIndex, get_global_index
try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None


@dataclass
class NLPEntity:
    name: Optional[str]
    league: Optional[str]
    score: Optional[float] = None
    method: str = "keyword"


@dataclass
class NLPIntent:
    kind: str  # "wins_by_team" | "goals_avg" | "goals_total" | "matches_per_season" | "issues"
    filters: Dict[str, Any]
    confidence: float = 0.4
    method: str = "heuristic"


TEAM_KEYWORDS = {
    # football
    "barcelone": ("barcelone", "LaLiga"),
    "fc barcelone": ("barcelone", "LaLiga"),
    "real madrid": ("real madrid", "LaLiga"),
    "psg": ("paris", "Ligue 1 McDonald's"),
    "paris": ("paris", "Ligue 1 McDonald's"),
    "bayern": ("bayern", "Bundesliga"),
    "juventus": ("juventus", "Serie A"),
    "juve": ("juventus", "Serie A"),
    "liverpool": ("liverpool", "Premier League"),
    "manchester city": ("manchester city", "Premier League"),
    "man city": ("manchester city", "Premier League"),
    "manchester united": ("manchester united", "Premier League"),
    "chelsea": ("chelsea", "Premier League"),
    "arsenal": ("arsenal", "Premier League"),
    # nba
    "lakers": ("lakers", "NBA"),
    "celtics": ("celtics", "NBA"),
    "knicks": ("knicks", "NBA"),
    "bulls": ("bulls", "NBA"),
    "warriors": ("warriors", "NBA"),
}

INTENT_TEMPLATES = {
    "wins_by_team": [
        "nombre de victoires de l'équipe par saison",
        "combien de matchs gagnés par cette équipe",
        "wins per season for this team",
    ],
    "issues": [
        "répartition victoires nuls défaites",
        "issues des matchs global",
        "home win vs away win vs draw",
    ],
    "goals_avg": [
        "buts moyens par match par saison",
        "average points per game per season",
        "score moyen",
    ],
    "goals_total": [
        "nombre total de buts par saison",
        "total points per season",
        "total goals scored",
    ],
    "matches_per_season": [
        "nombre de matchs par saison",
        "how many games per season",
    ],
}

_MODEL_CACHE: Optional[SentenceTransformer] = None

def _ensure_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    global _MODEL_CACHE
    if SentenceTransformer is None:
        return None
    if _MODEL_CACHE is None:
        _MODEL_CACHE = SentenceTransformer(model_name)
    return _MODEL_CACHE


def _entity_from_index(prompt: str, idx: NLPIndex) -> Optional[NLPEntity]:
    results = idx.search(prompt, top_k=3) if idx else []
    if not results:
        return None
    best, score = results[0]
    if score < 0.35:  # seuil de confiance minimal
        return None
    return NLPEntity(name=best.name, league=best.league, score=score, method="embedding")


def detect_entity(prompt: str) -> NLPEntity:
    # 1) embeddings via index global (si dispo)
    idx = get_global_index()
    ent = _entity_from_index(prompt, idx) if idx else None
    if ent:
        return ent
    # 2) fallback mots-clés
    p = prompt.lower()
    for kw, (team, league) in TEAM_KEYWORDS.items():
        if kw in p:
            return NLPEntity(name=team, league=league, score=0.6, method="keyword")
    return NLPEntity(name=None, league=None, score=None, method="none")


def detect_intent(prompt: str, entity: NLPEntity) -> NLPIntent:
    p = prompt.lower()
    filters: Dict[str, Any] = {}

    # Try embedding-based intent matching
    model = None
    idx = get_global_index()
    if idx and idx.model:
        model = idx.model
    elif SentenceTransformer is not None:
        model = _ensure_model()

    if model is not None:
        intents = list(INTENT_TEMPLATES.keys())
        templ_sentences: List[str] = []
        for intent in intents:
            templ_sentences.extend(INTENT_TEMPLATES[intent])

        emb_prompt = model.encode([prompt], normalize_embeddings=True)
        emb_templates = model.encode(templ_sentences, normalize_embeddings=True)
        sims = (emb_templates @ emb_prompt.T).squeeze()  # cos-sim car embeddings normalisés

        # regrouper par intent
        best_intent = None
        best_score = -1.0
        idx_start = 0
        for intent in intents:
            block = INTENT_TEMPLATES[intent]
            block_size = len(block)
            block_scores = sims[idx_start: idx_start + block_size]
            score = float(np.max(block_scores))
            if score > best_score:
                best_score = score
                best_intent = intent
            idx_start += block_size

        # règle spécifique si équipe détectée et mots-clés de win
        if entity.name and ("victoire" in p or "win" in p or "gagn" in p):
            best_intent = "wins_by_team"
            best_score = max(best_score, 0.6)

        if best_intent:
            return NLPIntent(kind=best_intent, filters=filters, confidence=best_score, method="embedding")

    # Fallback heuristics
    if entity.name and ("issue" in p or "victoire" in p or "win" in p or "gagn" in p):
        return NLPIntent(kind="wins_by_team", filters=filters, confidence=0.55, method="heuristic")
    if "issue" in p or "victoire" in p or "win" in p:
        return NLPIntent(kind="issues", filters=filters, confidence=0.5, method="heuristic")
    if "but" in p or "points" in p or "score" in p:
        if "total" in p:
            return NLPIntent(kind="goals_total", filters=filters, confidence=0.5, method="heuristic")
        return NLPIntent(kind="goals_avg", filters=filters, confidence=0.5, method="heuristic")
    return NLPIntent(kind="matches_per_season", filters=filters, confidence=0.4, method="heuristic")


def analyze_prompt(prompt: str) -> Dict[str, Any]:
    entity = detect_entity(prompt)
    intent = detect_intent(prompt, entity)
    return {
        "entity": {
            "name": entity.name,
            "league": entity.league,
            "score": entity.score,
            "method": entity.method,
        },
        "intent": intent.kind,
        "filters": intent.filters,
        "confidence": intent.confidence,
        "method": intent.method,
    }
