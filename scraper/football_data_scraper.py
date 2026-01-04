"""
Scraper multi-ligues (5 grands championnats européens) via football-data.org.
Plan gratuit : calendrier + scores, pas de stats joueurs détaillées.
API_KEY requise : FOOTBALL_DATA_API_KEY.
"""

import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from utils.log_utils import log_info, log_ok, log_warn

# Codes football-data.org -> league names
COMPETITIONS = {
    "PL": "Premier League",
    "FL1": "Ligue 1 McDonald's",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "PD": "LaLiga",
}

API_URL_TPL = "https://api.football-data.org/v4/competitions/{code}/matches"
RATE_LIMIT_SECONDS = 0.6
MAX_RETRIES = 4
START_YEAR = 2000  # récupérer toutes les saisons depuis 2000


def _parse_match(m: Dict[str, Any], league_name: str) -> Dict[str, Any]:
    utc_date = m.get("utcDate")
    try:
        match_dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    except Exception:
        match_dt = datetime.utcnow()

    home = m.get("homeTeam", {}) or {}
    away = m.get("awayTeam", {}) or {}
    score = m.get("score", {}) or {}
    full_time = score.get("fullTime", {}) or {}

    def _ext(team):
        tid = team.get("id")
        return str(tid) if tid is not None else None

    return {
        "league_name": league_name,
        "game_id": str(m.get("id")) if m.get("id") is not None else None,
        "date": match_dt,
        "home_team": {"name": home.get("name"), "external_id": _ext(home)},
        "away_team": {"name": away.get("name"), "external_id": _ext(away)},
        "home_score": full_time.get("home"),
        "away_score": full_time.get("away"),
        "team_stats": {},
        "player_stats": [],
        "coaches": [],
    }


def _fetch_competition(code: str, league_name: str, headers: dict) -> List[Dict[str, Any]]:
    """
    Récupère les matchs d'une compétition (séquentiel par statut et par saison, backoff 429 exponentiel).
    """
    url = API_URL_TPL.format(code=code)

    def _fetch_status(status_value: str, season_year: int) -> List[Dict[str, Any]]:
        params = {"status": status_value, "limit": 200, "season": season_year}
        wait = RATE_LIMIT_SECONDS
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log_info(f"[HTTP] GET {url} {params} (try {attempt})")
                resp = requests.get(url, params=params, headers=headers, timeout=20)
                if resp.status_code == 429 and attempt < MAX_RETRIES:
                    log_warn(f"[HTTP] 429 rate limit -> pause {wait:.1f}s")
                    time.sleep(wait)
                    wait *= 2
                    continue
                resp.raise_for_status()
                log_ok(f"[HTTP] {resp.url} -> {resp.status_code}")
                data = resp.json()
                return data.get("matches", []) or []
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    log_warn(f"[{league_name}] échec statut {status_value}: {exc}")
                    return []
                log_warn(f"[{league_name}] Erreur {exc} -> retry dans {wait:.1f}s")
                time.sleep(wait)
                wait *= 2
        return []

    matches_data: List[Dict[str, Any]] = []
    current_year = datetime.utcnow().year
    for season_year in range(START_YEAR, current_year + 1):
        for status in ["FINISHED", "SCHEDULED,IN_PLAY,PAUSED"]:
            matches_data.extend(_fetch_status(status, season_year))

    seen = set()
    parsed = []
    for m in matches_data:
        mid = m.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        parsed.append(_parse_match(m, league_name))

    log_ok(f"[{league_name}] {len(parsed)} match(s) collectés.")
    return parsed


def scrape_football_data_matches(on_competition_done=None):
    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        log_warn("FOOTBALL_DATA_API_KEY non défini, aucun match récupéré.")
        return []

    headers = {"X-Auth-Token": api_key}

    all_matches: List[Dict[str, Any]] = []
    for code, league_name in COMPETITIONS.items():
        matches = _fetch_competition(code, league_name, headers)
        if on_competition_done and matches:
            try:
                on_competition_done(matches, league_name)
            except Exception as e:
                log_warn(f"[{league_name}] Ingestion immédiate en erreur : {e}")
        all_matches.extend(matches)

    log_ok(f"[FOOTBALL-DATA] TOTAL : {len(all_matches)} matchs collectés (5 ligues).")
    return all_matches


__all__ = ["scrape_football_data_matches", "COMPETITIONS"]
