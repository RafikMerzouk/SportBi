import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from utils.log_utils import log_info, log_ok, log_warn, log_err
from utils.db_utils import get_connection, get_or_create_league

BASE_URL = "https://www.lnh.fr"
CALENDAR_PAGE = f"{BASE_URL}/liquimoly-starligue/calendrier"
AJAX_URL = f"{BASE_URL}/ajaxpost1"
LEAGUE_NAME = "Liqui Moly StarLigue"

RATE_LIMIT_SECONDS = 2.0
MAX_RETRIES = 5
_last_request_ts: Optional[float] = None

MONTH_MAP = {
    "janv": 1,
    "janvier": 1,
    "fevr": 2,
    "fevrier": 2,
    "mars": 3,
    "avr": 4,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7,
    "juillet": 7,
    "aout": 8,
    "sept": 9,
    "septembre": 9,
    "oct": 10,
    "octobre": 10,
    "nov": 11,
    "novembre": 11,
    "dec": 12,
    "decembre": 12,
}

DATE_RE = re.compile(
    r"(\d{1,2})\s+([^\s]+)(?:\s+(\d{2})h(\d{2}))?",
    re.IGNORECASE,
)
JOURNEE_RE = re.compile(r"J(\d+)", re.IGNORECASE)


@dataclass
class SeasonConfig:
    season_id: str
    start_year: int
    end_year: int
    label: str
    univers: str
    key: str


def _throttled_request(method: str, url: str, **kwargs) -> str:
    """HTTP client with a small throttle and retry."""
    global _last_request_ts

    for attempt in range(1, MAX_RETRIES + 1):
        if _last_request_ts is not None:
            elapsed = time.time() - _last_request_ts
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)

        try:
            log_info(f"[HTTP] {method} {url} (try {attempt})")
            resp = requests.request(
                method,
                url,
                headers={"User-Agent": "lnh-scraper/1.0 (contact: you@example.com)"},
                timeout=25,
                **kwargs,
            )

            if resp.status_code == 429:
                if attempt == MAX_RETRIES:
                    log_err(f"[HTTP] 429 Too Many Requests for {url}")
                    resp.raise_for_status()
                wait = RATE_LIMIT_SECONDS * attempt
                log_warn(f"[HTTP] 429 on {url}, sleeping {wait:.1f}s")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            _last_request_ts = time.time()
            log_ok(f"[HTTP] {url} -> {resp.status_code}")
            return resp.text

        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                log_err(f"[HTTP] Failed {url} after {attempt} tries: {exc}")
                raise
            wait = RATE_LIMIT_SECONDS * attempt
            log_warn(f"[HTTP] Error {exc} on {url}, retry in {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"Unable to fetch {url}")


def _normalize_month(token: str) -> Optional[int]:
    """Convert 'déc.'/'janv' to month integer."""
    normalized = unicodedata.normalize("NFD", token.lower())
    normalized = "".join(ch for ch in normalized if ord(ch) < 128)
    normalized = normalized.replace(".", "")
    return MONTH_MAP.get(normalized)


def _parse_date(date_str: str, season_start: int, season_end: int) -> Optional[datetime]:
    """
    Parse 'ven. 05 déc. 19h00' or 'sam. 18 sept.' using the season to pick the correct year.
    """
    m = DATE_RE.search(date_str)
    if not m:
        log_warn(f"[PARSE] Impossible de lire la date '{date_str}'")
        return None

    day, month_token, hour, minute = m.groups()
    month = _normalize_month(month_token)
    if not month:
        log_warn(f"[PARSE] Mois inconnu '{month_token}' dans '{date_str}'")
        return None

    year = season_start if month >= 7 else season_end
    if hour is None or minute is None:
        # Anciennes saisons sans horaire : fallback 20h00
        log_warn(f"[PARSE] Horaire manquant dans '{date_str}', fallback 20h00.")
        hour, minute = "20", "00"
    try:
        return datetime(year, month, int(day), int(hour), int(minute))
    except ValueError:
        log_warn(f"[PARSE] Date invalide '{date_str}' pour saison {season_start}-{season_end}")
        return None


def _parse_season_label(label: str) -> Optional[tuple[int, int]]:
    m = re.search(r"(20\d{2})\s*/\s*(20\d{2})", label)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _extract_form_config() -> tuple[list[SeasonConfig], list[str]]:
    """Collects seasons, univers, and months from the calendar page."""
    html = _throttled_request("GET", CALENDAR_PAGE)
    soup = BeautifulSoup(html, "html.parser")

    form = soup.find("form", id=re.compile(r"^calendar-form-"))
    if not form:
        raise RuntimeError("Formulaire calendrier introuvable sur la page LNH.")

    univers_input = form.find("input", {"name": "univers"})
    key_input = form.find("input", {"name": "key"})
    univers = univers_input["value"]
    key = key_input["value"]

    months = [
        opt.get("value")
        for opt in form.select("select.months-wrapper-filter option")
        if opt.get("value")
    ]

    seasons: list[SeasonConfig] = []
    for opt in form.find("select", {"name": "seasons_id"}).find_all("option"):
        season_id = opt.get("value")
        label = opt.get_text(strip=True)
        years = _parse_season_label(label)
        if not season_id or not years:
            continue
        seasons.append(
            SeasonConfig(
                season_id=season_id,
                start_year=years[0],
                end_year=years[1],
                label=label,
                univers=univers,
                key=key,
            )
        )

    log_ok(f"[CFG] {len(seasons)} saisons détectées ({months} mois).")
    return seasons, months


def _fetch_month(season: SeasonConfig, month: str) -> str:
    payload = {
        "seasons_id": season.season_id,
        "days_id": "all",
        "teams_id": "all",
        "univers": season.univers,
        "key": season.key,
        "current_month": month,
        "type": "all",
        "type_id": "all",
        "contents_controller": "sportsCalendars",
        "contents_action": "index_ajax",
        "cache": "yes",
        "cacheKeys": "univers,contents_controller,contents_action,type,seasons_id,days_id,teams_id,current_month",
    }
    return _throttled_request("POST", AJAX_URL, data=payload)


def _parse_matches(calendar_html: str, season: SeasonConfig) -> list[dict]:
    soup = BeautifulSoup(calendar_html, "html.parser")
    matches: list[dict] = []

    for item in soup.find_all("div", class_="calendars-listing-item"):
        comp_block = item.find("div", class_="col-competitions")
        if not comp_block:
            continue
        comp_strings = list(comp_block.stripped_strings)
        if len(comp_strings) < 2:
            continue

        competition_label = comp_strings[0]
        date_str = comp_strings[1]

        journee_match = JOURNEE_RE.search(competition_label)
        journee = journee_match.group(1) if journee_match else None

        match_dt = _parse_date(date_str, season.start_year, season.end_year)
        if not match_dt:
            continue

        team_names = [tn.get_text(strip=True) for tn in item.select("div.team-name")]
        if len(team_names) != 2:
            log_warn("[PARSE] équipes introuvables sur un bloc match")
            continue
        home_team, away_team = team_names

        scores_div = item.find("div", class_="scores")
        home_score = away_score = None
        if scores_div:
            score_text = scores_div.get_text(strip=True)
            m = re.match(r"(\d+)\s*-\s*(\d+)", score_text)
            if m:
                home_score, away_score = int(m.group(1)), int(m.group(2))

        source_link = item.find("a", class_="icon-item")
        source_url = source_link["href"] if source_link and source_link.has_attr("href") else CALENDAR_PAGE

        matches.append(
            {
                "league_name": LEAGUE_NAME,
                "season_label": season.label,
                "season_start": datetime(season.start_year, 7, 1),
                "season_end": datetime(season.end_year, 7, 1),
                "date": match_dt,
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "journee": journee,
                "source_url": source_url,
            }
        )

    log_info(f"[PARSE] {len(matches)} match(s) trouvés pour {season.label}.")
    return matches


def _extract_match_stats(match_url: str) -> dict:
    """
    Récupère les stats équipes depuis l'onglet 'Stats match' (ajaxpost1).
    On retourne {'home': {...}, 'away': {...}} ; best effort, HTML non structuré.
    """
    stats = {"home": {}, "away": {}}
    try:
        html = _throttled_request("GET", match_url)
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", id="calendars-form")
        if not form:
            return stats

        calendars_id = form.find("input", {"name": "calendars_id"})["value"]
        seasons_id = form.find("input", {"name": "seasons_id"})["value"]

        payload = {
            "contents_controller": "sportsCalendars",
            "contents_action": "view_tab_stats",
            "calendars_id": calendars_id,
            "seasons_id": seasons_id,
            "logged": "_no",
            "cache": "true",
        }
        ajax_html = _throttled_request("POST", f"{BASE_URL}/ajaxpost1", data=payload)
        ajax_soup = BeautifulSoup(ajax_html, "html.parser")

        for row in ajax_soup.select("div.confrontations-row"):
            label = row.find("div", class_="col-label")
            if not label:
                continue
            label_txt = " ".join(label.get_text(" ", strip=True).split())
            cols = row.find_all("div", class_="col-stat")
            if len(cols) != 2:
                continue
            home_val_raw = cols[0].get_text(strip=True)
            away_val_raw = cols[1].get_text(strip=True)

            def parse_val(v: str):
                if "/" in v:
                    parts = [p.strip() for p in v.split("/") if p.strip()]
                    try:
                        nums = [int(p) for p in parts]
                        return nums if len(nums) > 1 else nums[0]
                    except ValueError:
                        return v
                try:
                    return int(v)
                except ValueError:
                    return v

            stats["home"][label_txt] = parse_val(home_val_raw)
            stats["away"][label_txt] = parse_val(away_val_raw)

    except Exception as e:
        log_warn(f"[STATS] Impossible de récupérer stats pour {match_url}: {e}")
    return stats


def _season_has_matches(league_id, season: SeasonConfig) -> bool:
    """Retourne True si au moins un match existe déjà pour cette saison (évite re-scrape)."""
    start_dt = datetime(season.start_year, 7, 1)
    end_dt = datetime(season.end_year, 7, 1)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM match
            WHERE leagueid = %s
              AND startdatematch >= %s
              AND startdatematch < %s
            LIMIT 1
            """,
            (league_id, start_dt, end_dt),
        )
        return cur.fetchone() is not None


def scrape_lnh_calendar():
    """Scrape toutes les saisons exposées sur le site LNH (Liqui Moly StarLigue)."""
    seasons, months = _extract_form_config()
    all_matches: list[dict] = []
    seen = set()

    log_info(f"[CAL] Lancement scraping {LEAGUE_NAME} ({len(seasons)} saisons).")

    league_id = get_or_create_league(LEAGUE_NAME)

    for season in seasons:
        if _season_has_matches(league_id, season):
            log_info(f"[CAL] Saison {season.label} déjà en base, skip.")
            continue

        before = len(all_matches)
        for month in months:
            html = _fetch_month(season, month)
            month_matches = _parse_matches(html, season)

            for match in month_matches:
                key = (
                    match["date"],
                    match["home_team"],
                    match["away_team"],
                    match.get("home_score"),
                    match.get("away_score"),
                )
                if key in seen:
                    continue
                seen.add(key)
                match["team_stats"] = _extract_match_stats(match["source_url"])
                all_matches.append(match)

        season_count = len(all_matches) - before
        log_ok(f"[CAL] Saison {season.label} : {season_count} matchs.")

    log_ok(f"[CAL] TOTAL {LEAGUE_NAME} : {len(all_matches)} matchs collectés.")
    return all_matches


__all__ = ["scrape_lnh_calendar", "LEAGUE_NAME"]
