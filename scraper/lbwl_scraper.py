import re
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from utils.log_utils import log_info, log_ok, log_warn, log_err

_session = requests.Session()

# Headers complets pour mimer un navigateur
FULL_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

BASE_URL = "https://basketlfb.com"
CALENDAR_URL = f"{BASE_URL}/laboulangerewonderligue/calendrier"
# Archives : pattern connu https://basketlfb.com/laboulangerewonderligue/calendrier/saison/<Année>
ARCHIVE_URL_TEMPLATE = f"{BASE_URL}/laboulangerewonderligue/calendrier/saison/{{year}}"
LEAGUE_NAME = "La Boulangère Wonderligue"

RATE_LIMIT_SECONDS = 0.6
MAX_RETRIES = 4
_last_request_ts: Optional[float] = None

FIBA_URL_RE = re.compile(r"https?://fibalivestats\.dcd\.shared\.geniussports\.com/u/FFBB/(\d+)", re.IGNORECASE)


def _throttled_request(method: str, url: str, **kwargs) -> str:
    global _last_request_ts
    for attempt in range(1, MAX_RETRIES + 1):
        if _last_request_ts is not None:
            elapsed = time.time() - _last_request_ts
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)
        try:
            log_info(f"[HTTP] {method} {url} (try {attempt})")
            resp = _session.request(
                method,
                url,
                headers=FULL_BROWSER_HEADERS,
                timeout=20,
                **kwargs,
            )
            resp.raise_for_status()
            _last_request_ts = time.time()
            log_ok(f"[HTTP] {url} -> {resp.status_code}")
            return resp.text
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                log_err(f"[HTTP] Échec {url}: {exc}")
                raise
            wait = RATE_LIMIT_SECONDS * attempt
            log_warn(f"[HTTP] Erreur {exc} -> retry dans {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"Impossible de récupérer {url}")


def _get_calendar_entries(extra_urls: list[str]):
    urls = [CALENDAR_URL] + extra_urls
    entries = []
    for url in urls:
        html = _throttled_request("GET", url)
        soup = BeautifulSoup(html, "html.parser")
        for div in soup.select("div.display-games__third-list__entry__container"):
            href = div.get("href") or ""
            m = FIBA_URL_RE.search(href)
            if not m:
                continue
            match_id = m.group(1)
            title = div.get("title") or ""
            referer = href if href.startswith("http") else (BASE_URL + href)
            raw_text = div.get_text(" ", strip=True)
            entries.append({"match_id": match_id, "title": title, "fiba_url": referer, "raw_text": raw_text})
    log_ok(f"[CAL] {len(entries)} match(s) avec FIBA LiveStats détectés.")
    return entries


def _fetch_fibalive_json(match_id: str, referer: str) -> dict:
    url = f"https://fibalivestats.dcd.shared.geniussports.com/data/{match_id}/data.json"
    # Warm-up: charge la page FIBA pour récupérer cookies éventuels
    try:
        _session.get(referer, headers=FULL_BROWSER_HEADERS, timeout=15)
    except Exception:
        pass

    headers = {
        **FULL_BROWSER_HEADERS,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": referer,
        "Origin": "https://fibalivestats.dcd.shared.geniussports.com",
        "X-Requested-With": "XMLHttpRequest",
        "Host": "fibalivestats.dcd.shared.geniussports.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }
    resp = _session.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _season_label_from_date(dt: datetime) -> str:
    start_year = dt.year if dt.month >= 7 else dt.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _team_display_name(team: dict) -> Optional[str]:
    """
    Fallback helper to always have a team name; avoids NULL inserts.
    """
    for key in ("teamName", "shortName", "name", "code"):
        val = (team.get(key) or "").strip()
        if val:
            return val
    return None


def _parse_game(entry: dict, data: dict) -> Optional[dict]:
    tm = data.get("tm", {})
    if not tm or "1" not in tm or "2" not in tm:
        return None

    # Détection home/away via le title "TeamA vs TeamB"
    home_name = away_name = None
    if entry["title"] and " vs " in entry["title"]:
        parts = entry["title"].split(" vs ")
        if len(parts) == 2:
            home_name, away_name = parts[0].strip(), parts[1].strip()

    team1 = tm["1"]
    team2 = tm["2"]

    # fallback : team1 = home si on ne peut pas matcher
    if home_name and away_name:
        def match_team(name, t):
            return name.lower() in (t.get("teamName") or "").lower() or name.lower() in (t.get("shortName") or "").lower()
        if match_team(home_name, team1) and match_team(away_name, team2):
            home_team = team1
            away_team = team2
        elif match_team(home_name, team2) and match_team(away_name, team1):
            home_team = team2
            away_team = team1
        else:
            home_team, away_team = team1, team2
    else:
        home_team, away_team = team1, team2

    # Assurer qu'on a bien un nom pour chaque équipe (sinon on skip pour éviter NULL).
    home_name_safe = _team_display_name(home_team)
    away_name_safe = _team_display_name(away_team)
    if not home_name_safe or not away_name_safe:
        log_warn(f"[LBWL] Nom d'équipe manquant pour le match {entry.get('match_id')}, skip.")
        return None

    # Date : pas fournie directement, on peut utiliser "clock" absent; fallback = now
    # FIBA LiveStats ne fournit pas la date ici; on laisse la date actuelle pour éviter crash.
    game_date = datetime.utcnow()

    home_score = home_team.get("score")
    away_score = away_team.get("score")

    # Team stats agrégées
    team_stats = {
        "home": {
            "PTS": home_team.get("tot_sPoints"),
            "REB": home_team.get("tot_sReboundsTotal"),
            "AST": home_team.get("tot_sAssists"),
            "TOV": home_team.get("tot_sTurnovers"),
            "STL": home_team.get("tot_sSteals"),
            "BLK": home_team.get("tot_sBlocks"),
            "FGA": home_team.get("tot_sFieldGoalsAttempted"),
            "FGM": home_team.get("tot_sFieldGoalsMade"),
            "FG3A": home_team.get("tot_sThreePointersAttempted"),
            "FG3M": home_team.get("tot_sThreePointersMade"),
            "FTA": home_team.get("tot_sFreeThrowsAttempted"),
            "FTM": home_team.get("tot_sFreeThrowsMade"),
        },
        "away": {
            "PTS": away_team.get("tot_sPoints"),
            "REB": away_team.get("tot_sReboundsTotal"),
            "AST": away_team.get("tot_sAssists"),
            "TOV": away_team.get("tot_sTurnovers"),
            "STL": away_team.get("tot_sSteals"),
            "BLK": away_team.get("tot_sBlocks"),
            "FGA": away_team.get("tot_sFieldGoalsAttempted"),
            "FGM": away_team.get("tot_sFieldGoalsMade"),
            "FG3A": away_team.get("tot_sThreePointersAttempted"),
            "FG3M": away_team.get("tot_sThreePointersMade"),
            "FTA": away_team.get("tot_sFreeThrowsAttempted"),
            "FTM": away_team.get("tot_sFreeThrowsMade"),
        },
    }

    player_stats = []
    for side, t in (("home", home_team), ("away", away_team)):
        pl = t.get("pl", {}) or {}
        for pno, p in pl.items():
            player_stats.append(
                {
                    "team_side": side,
                    "team_external_id": t.get("code"),
                    "player_name": p.get("name") or f"{p.get('firstName','')} {p.get('familyName','')}".strip(),
                    "first_name": p.get("firstName"),
                    "number": p.get("shirtNumber"),
                    "player_external_id": f"ffbb-{p.get('pno')}",
                    "stats": {
                        "PTS": p.get("sPoints"),
                        "REB": p.get("sReboundsTotal"),
                        "AST": p.get("sAssists"),
                        "STL": p.get("sSteals"),
                        "BLK": p.get("sBlocks"),
                        "TOV": p.get("sTurnovers"),
                        "PF": p.get("sFoulsPersonal"),
                        "MIN": _minutes_to_float(p.get("sMinutes")),
                        "FGM": p.get("sFieldGoalsMade"),
                        "FGA": p.get("sFieldGoalsAttempted"),
                        "FG3M": p.get("sThreePointersMade"),
                        "FG3A": p.get("sThreePointersAttempted"),
                        "FTM": p.get("sFreeThrowsMade"),
                        "FTA": p.get("sFreeThrowsAttempted"),
                    },
                }
            )

    coaches = []
    if home_team.get("coach"):
        coaches.append({"name": home_team["coach"], "team": "home", "role": "Head Coach"})
    if away_team.get("coach"):
        coaches.append({"name": away_team["coach"], "team": "away", "role": "Head Coach"})

    return {
        "league_name": LEAGUE_NAME,
        # LBWL calendrier actuel ne donne pas la saison; on la déduit de la date fallback
        "season_label": _season_label_from_date(game_date),
        "season_start": datetime(game_date.year if game_date.month >= 7 else game_date.year - 1, 7, 1),
        "season_end": datetime(game_date.year if game_date.month >= 7 else game_date.year - 1 + 1, 7, 1),
        "game_id": entry["match_id"],
        "date": game_date,
        "home_team": {"name": home_name_safe, "external_id": home_team.get("code") or home_name_safe},
        "away_team": {"name": away_name_safe, "external_id": away_team.get("code") or away_name_safe},
        "home_score": home_score,
        "away_score": away_score,
        "team_stats": team_stats,
        "player_stats": player_stats,
        "coaches": coaches,
    }


def _minutes_to_float(minutes_str: str) -> float:
    if not minutes_str:
        return 0.0
    try:
        mins, secs = minutes_str.split(":")
        return int(mins) + int(secs) / 60.0
    except Exception:
        return 0.0


def scrape_wonderligue_calendar():
    """
    Scrape LBWL via FIBA LiveStats : scores + stats équipes + stats joueurs.
    Par défaut saison courante. Si des dossiers archives existent (ex: 2024-25), on peut les rajouter.
    """
    extra_urls: list[str] = []
    # Pattern confirmé : /calendrier/saison/<Année> (année de début).
    current_year = datetime.utcnow().year
    for year in range(2003, current_year + 1):
        extra_urls.append(ARCHIVE_URL_TEMPLATE.format(year=year))

    entries = _get_calendar_entries(extra_urls)
    matches: list[dict] = []
    for entry in entries:
        try:
            data = _fetch_fibalive_json(entry["match_id"], entry.get("fiba_url") or CALENDAR_URL)
            game = _parse_game(entry, data)
            if game:
                matches.append(game)
        except Exception as e:
            log_warn(f"[LBWL] Impossible de parser match {entry['match_id']}: {e}")

    log_ok(f"[LBWL] TOTAL : {len(matches)} matchs collectés.")
    return matches


__all__ = ["scrape_wonderligue_calendar", "LEAGUE_NAME"]
