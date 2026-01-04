# api/services/nlp_index.py
# Esquisse d'un index FAISS + embeddings. Fonctionne en mode dégradé si faiss/sentence-transformers
# ne sont pas installés ou si aucun index n'est construit.
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from ..db import engine

try:
    import faiss  # type: ignore
    import numpy as np
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - mode dégradé
    faiss = None
    np = None
    SentenceTransformer = None


@dataclass
class IndexedAlias:
    name: str
    league: str
    team_id: Optional[str] = None
    alias: Optional[str] = None


class NLPIndex:
    """
    Index sémantique pour retrouver une équipe/ligue via embeddings.
    Si faiss/transformers ne sont pas dispo, retourne simplement [] (fallback keywords pris en charge ailleurs).
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self.index = None
        self.metadata: List[IndexedAlias] = []

    def _ensure_model(self):
        if SentenceTransformer is None:
            return False
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
        return True

    def build(self, aliases: List[IndexedAlias]):
        if faiss is None or np is None:
            return False
        if not self._ensure_model():
            return False
        self.metadata = aliases
        corpus = [a.alias or a.name for a in aliases]
        emb = self.model.encode(corpus, convert_to_numpy=True, normalize_embeddings=True)
        dim = emb.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(emb)
        return True

    def search(self, text: str, top_k: int = 3) -> List[Tuple[IndexedAlias, float]]:
        if faiss is None or np is None or self.index is None or not self.metadata:
            return []
        if not self._ensure_model():
            return []
        q = self.model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
        scores, idxs = self.index.search(q, top_k)
        results: List[Tuple[IndexedAlias, float]] = []
        for i, score in zip(idxs[0], scores[0]):
            if i < 0 or i >= len(self.metadata):
                continue
            results.append((self.metadata[i], float(score)))
        return results


# Singleton facultatif (lazy). On peut imaginer le remplir depuis la DB via une fonction utilitaire.
_GLOBAL_INDEX: Optional[NLPIndex] = None


def get_global_index() -> Optional[NLPIndex]:
    return _GLOBAL_INDEX


def set_global_index(idx: NLPIndex):
    global _GLOBAL_INDEX
    _GLOBAL_INDEX = idx


def build_index_from_db(
    schema_to_league: Dict[str, str],
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    max_alias_per_team: int = 3,
) -> Optional[NLPIndex]:
    """
    Construit un index embeddings à partir des tables team de chaque schéma.
    Retourne None si faiss/transformers ne sont pas dispo.
    """
    if faiss is None or np is None or SentenceTransformer is None:
        return None

    idx = NLPIndex(model_name=model_name)
    aliases: List[IndexedAlias] = []
    seen = set()

    def _push(name: str, league: str, team_id: Optional[str] = None):
        key = (name.lower().strip(), league)
        if key in seen:
            return
        seen.add(key)
        aliases.append(IndexedAlias(name=name, league=league, team_id=team_id))

    with engine.connect() as conn:
        for schema, league in schema_to_league.items():
            try:
                conn.execute(text(f"SET search_path TO {schema},public"))
                rows = conn.execute(text("SELECT teamId, teamName FROM team WHERE teamName IS NOT NULL")).fetchall()
                for team_id, name in rows:
                    if not name:
                        continue
                    name = str(name).strip()
                    _push(name, league, team_id)
                    _push(name.lower(), league, team_id)
            except SQLAlchemyError:
                continue

    if not aliases:
        return None
    ok = idx.build(aliases)
    if not ok:
        return None
    set_global_index(idx)
    return idx
