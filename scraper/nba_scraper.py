import time
from datetime import datetime
from typing import List, Dict, Any
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from utils.log_utils import log_info, log_ok, log_warn, log_err

BASE_URL = "https://stats.nba.com/stats"
LEAGUE_NAME = "NBA"

# Saisons cibles (année de début). 1996 = saison 1996-97.
SEASON_START_YEAR = 1996
CURRENT_YEAR = datetime.utcnow().year + (1 if datetime.utcnow().month >= 7 else 0)

RATE_LIMIT_SECONDS = 0.7
MAX_RETRIES = 8
_last_request_ts = None
_session = requests.Session()

# Headers proches de ce qu'envoie nba.com/stats (réduction des 403)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://www.nba.com/stats/",
    "Origin": "https://www.nba.com",
    "Host": "stats.nba.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}
# Précharge la session avec ces headers
_session.headers.update(DEFAULT_HEADERS)


def _reset_session():
    global _session
    _session = requests.Session()
    _session.headers.update(DEFAULT_HEADERS)


def _nba_get(endpoint: str, params: dict) -> dict:
    """Appel GET avec retry + rate limit basique."""
    global _last_request_ts
    url = f"{BASE_URL}/{endpoint}"

    for attempt in range(1, MAX_RETRIES + 1):
        if _last_request_ts is not None:
            elapsed = time.time() - _last_request_ts
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)
        try:
            log_info(f"[HTTP] GET {endpoint} {params} (try {attempt})")
            resp = _session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
            _last_request_ts = time.time()
            log_ok(f"[HTTP] {resp.url} -> {resp.status_code}")
            return resp.json()
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                log_err(f"[HTTP] Échec {endpoint}: {exc}")
                raise
            is_timeout = isinstance(exc, requests.Timeout) or "Read timed out" in str(exc)
            # Backoff plus agressif sur timeout/remote disconnect
            wait = RATE_LIMIT_SECONDS * (2 ** attempt) if is_timeout else RATE_LIMIT_SECONDS * (2 ** (attempt - 1))
            if is_timeout:
                log_warn(f"[HTTP] Timeout/connexion coupée {exc} -> reset session et retry dans {wait:.1f}s")
                _reset_session()
            else:
                log_warn(f"[HTTP] Erreur {exc} -> retry dans {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"Impossible d'appeler {endpoint}")


def _season_label(year_start: int) -> str:
    return f"{year_start}-{str(year_start + 1)[-2:]}"


def _get_games_for_season(year_start: int) -> List[Dict[str, Any]]:
    """Récupère les games (ids + home/away + date) via leaguegamefinder (par team) en dédupliquant sur GAME_ID."""
    season = _season_label(year_start)
    params = {
        "LeagueID": "00",
        "SeasonType": "Regular Season",
        "Season": season,
    }
    data = _nba_get("leaguegamefinder", params)
    results = data.get("resultSets", [])[0]
    headers = results.get("headers", [])
    rows = results.get("rowSet", [])

    idx_game_id = headers.index("GAME_ID")
    idx_game_date = headers.index("GAME_DATE")
    idx_matchup = headers.index("MATCHUP")
    idx_team_id = headers.index("TEAM_ID")
    idx_team_name = headers.index("TEAM_NAME")

    games: dict[str, Dict[str, Any]] = {}

    for row in rows:
        game_id = row[idx_game_id]
        game_date_str = row[idx_game_date]
        matchup = row[idx_matchup]
        team_id = row[idx_team_id]
        team_name = row[idx_team_name]

        try:
            game_date = datetime.strptime(game_date_str, "%Y-%m-%d")
        except ValueError:
            continue

        is_home = "vs." in matchup  # ex: "LAL vs. BOS" vs "LAL @ BOS"

        info = games.setdefault(
            game_id,
            {
                "game_id": game_id,
                "date": game_date,
                "season_start": datetime(year_start, 7, 1),
                "season_end": datetime(year_start + 1, 7, 1),
                "season_label": season,
                "home_team": None,
                "away_team": None,
            },
        )

        team_obj = {"name": team_name, "external_id": str(team_id)}
        if is_home:
            info["home_team"] = team_obj
        else:
            info["away_team"] = team_obj

    # Filtrer games avec home et away présents
    filtered = [g for g in games.values() if g["home_team"] and g["away_team"]]
    log_ok(f"[NBA] Saison {season}: {len(filtered)} games trouvés.")
    return filtered


def _fetch_boxscore(game_id: str) -> Dict[str, Any]:
    params = {
        "GameID": game_id,
        "StartPeriod": 0,
        "EndPeriod": 0,
        "StartRange": 0,
        "EndRange": 0,
        "RangeType": 0,
    }
    data = _nba_get("boxscoretraditionalv2", params)
    return data


def _parse_player_stats(box_json: dict) -> List[Dict[str, Any]]:
    """Renvoie une liste de stats joueurs pour un match."""
    result_sets = box_json.get("resultSets", [])
    players_rs = next((rs for rs in result_sets if rs.get("name") == "PlayerStats"), None)
    if not players_rs:
        return []

    headers = players_rs.get("headers", [])
    rows = players_rs.get("rowSet", [])

    idx_player_id = headers.index("PLAYER_ID")
    idx_player_name = headers.index("PLAYER_NAME")
    idx_team_id = headers.index("TEAM_ID")
    idx_team_name = headers.index("TEAM_NAME") if "TEAM_NAME" in headers else (headers.index("TEAM_ABBREVIATION") if "TEAM_ABBREVIATION" in headers else None)
    def idx(name, alt=None):
        if name in headers:
            return headers.index(name)
        if alt and alt in headers:
            return headers.index(alt)
        return None

    idx_pts = idx("PTS")
    idx_reb = idx("REB")
    idx_ast = idx("AST")
    idx_stl = idx("STL", "STL_TOV")  # certains endpoints renvoient STL_TOV
    idx_blk = idx("BLK")
    idx_tov = idx("TOV", "TO")
    idx_pf = idx("PF")
    idx_min = idx("MIN")
    idx_fg3m = idx("FG3M", "FG3M_A")
    idx_fg3a = idx("FG3A", "FG3M_A")
    idx_fgm = idx("FGM")
    idx_fga = idx("FGA")
    idx_ftm = idx("FTM")
    idx_fta = idx("FTA")
    idx_plus_minus = idx("PLUS_MINUS", "PLUS_MINUS_RATING")
    idx_pos = headers.index("START_POSITION")

    stats = []
    for row in rows:
        team_name_val = row[idx_team_name] if idx_team_name is not None else ""
        def val(idx_):
            return row[idx_] if idx_ is not None and idx_ < len(row) else None

        stats.append(
            {
                "player_external_id": str(row[idx_player_id]),
                "player_name": row[idx_player_name],
                "team_external_id": str(row[idx_team_id]),
                "team_name": team_name_val,
                "position": row[idx_pos],
                "stats": {
                    "PTS": val(idx_pts),
                    "REB": val(idx_reb),
                    "AST": val(idx_ast),
                    "STL": val(idx_stl),
                    "BLK": val(idx_blk),
                    "TOV": val(idx_tov),
                    "PF": val(idx_pf),
                    "MIN": _minutes_to_float(val(idx_min)) if val(idx_min) is not None else 0.0,
                    "FGM": val(idx_fgm),
                    "FGA": val(idx_fga),
                    "FG3M": val(idx_fg3m),
                    "FG3A": val(idx_fg3a),
                    "FTM": val(idx_ftm),
                    "FTA": val(idx_fta),
                    "PLUS_MINUS": val(idx_plus_minus),
                },
            }
        )
    return stats


def _minutes_to_float(minutes_str: str) -> float:
    if not minutes_str:
        return 0.0
    try:
        mins, secs = minutes_str.split(":")
        return int(mins) + int(secs) / 60.0
    except Exception:
        return 0.0


def scrape_nba_games(on_season_done=None):
    """
    Scrape toutes les saisons NBA depuis 1996 via stats.nba.com (boxscore traditionnel).
    Si on_season_done est fourni, il est appelé à chaque fin de saison avec (list_games, season_label).
    """
    start_from_id = os.getenv("NBA_START_GAME_ID")  # permet de reprendre à partir d'un gameId précis
    skip_until = bool(start_from_id)

    all_games: List[Dict[str, Any]] = []
    failed_games: list[str] = []
    for year in range(SEASON_START_YEAR, CURRENT_YEAR):
        try:
            season_games = _get_games_for_season(year)
        except Exception as e:
            log_warn(f"[NBA] Saison {_season_label(year)} sautée (erreur: {e})")
            continue
        # filtrage reprise éventuelle ; si l'ID demandé n'existe pas, on repart de zéro
        if skip_until:
            if not any(g["game_id"] == start_from_id for g in season_games):
                log_warn(f"[NBA] start_id {start_from_id} introuvable pour la saison {_season_label(year)}, on saute cette saison.")
                # on continue à chercher dans les saisons suivantes
                continue
            else:
                filtered = []
                for g in season_games:
                    if g["game_id"] == start_from_id:
                        skip_until = False
                        filtered.append(g)
                    elif not skip_until:
                        filtered.append(g)
                season_games = filtered

        def process_game(game):
            try:
                box = _fetch_boxscore(game["game_id"])
            except Exception as e:
                log_warn(f"[NBA] Boxscore manquant pour {game['game_id']}: {e}")
                failed_games.append(game["game_id"])
                return None
            players_stats = _parse_player_stats(box)
            home_score = sum((p["stats"].get("PTS") or 0) for p in players_stats if p["team_external_id"] == game["home_team"]["external_id"])
            away_score = sum((p["stats"].get("PTS") or 0) for p in players_stats if p["team_external_id"] == game["away_team"]["external_id"])

            game["home_score"] = home_score
            game["away_score"] = away_score
            game["player_stats"] = players_stats
            game["coaches"] = []  # endpoint coach non utilisé ici
            return game

        processed_games = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(process_game, g) for g in season_games]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    processed_games.append(res)

        # Ingestion immédiate par saison si callback fourni
        if on_season_done:
            try:
                on_season_done(processed_games, _season_label(year))
            except Exception as e:
                log_warn(f"[NBA] Ingestion saison {_season_label(year)} en erreur : {e}")

        all_games.extend(processed_games)
        log_ok(f"[NBA] Saison {_season_label(year)} traitée ({len(processed_games)}/{len(season_games)} games).")

    if failed_games:
        log_warn(f"[NBA] {len(failed_games)} game(s) sans boxscore : {failed_games[:10]}{'...' if len(failed_games)>10 else ''}")
    log_ok(f"[NBA] TOTAL games collectés : {len(all_games)}")
    return all_games


__all__ = ["scrape_nba_games", "LEAGUE_NAME"]
