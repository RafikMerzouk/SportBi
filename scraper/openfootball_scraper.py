"""
Scraper OpenFootball : parse les fichiers texte des datasets locaux (football_data/*-master).
Collecte les matchs (scores) pour les 5 ligues majeures depuis les saisons disponibles.
Pas de stats détaillées (scores uniquement), ingestion via ingest_matches.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from utils.log_utils import log_info, log_ok, log_warn

# Dans le conteneur, /app est le dossier monté (scraper). Les datasets sont à côté : /app/football_data
BASE_DIR = Path(__file__).resolve().parent.parent / "football_data"

# Mapping répertoire -> nom de ligue et motif de fichier
LEAGUE_CONFIG = {
    "england-master": {"league_name": "Premier League", "glob": "1-*.txt", "base": BASE_DIR},
    "deutschland-master": {"league_name": "Bundesliga", "glob": "1-*.txt", "base": BASE_DIR},
    "italy-master": {"league_name": "Serie A", "glob": "1-*.txt", "base": BASE_DIR},
    "espana-master": {"league_name": "LaLiga", "glob": "1-*.txt", "base": BASE_DIR},
    # Ligue 1 : fichiers dans europe-master/france avec suffixe fr1
    "france": {
        "league_name": "Ligue 1 McDonald's",
        "glob": "*_fr1.txt",
        "base": BASE_DIR / "europe-master",
    },
}


DATE_LINE_RE = re.compile(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3})/(\d{1,2})(?: (\d{4}))?", re.IGNORECASE)
MATCH_LINE_RE = re.compile(r"^\s*(\d{1,2}\.\d{2})\s+(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)")


def _season_bounds(season_folder: str) -> tuple[datetime, datetime, str]:
    # season_folder comme "2014-15"
    try:
        start_year = int(season_folder.split("-")[0])
    except Exception:
        start_year = datetime.utcnow().year
    season_label = f"{start_year}-{str(start_year + 1)[-2:]}"
    start_date = datetime(start_year, 7, 1)
    end_date = datetime(start_year + 1, 7, 1)
    return start_date, end_date, season_label


def _parse_file(path: Path, league_name: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    season_start, season_end, season_label = _season_bounds(path.parent.name)
    current_date: Optional[datetime] = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.startswith("#") or raw_line.startswith("="):
            continue

        date_m = DATE_LINE_RE.match(raw_line)
        if date_m:
            dow, mon, day, year = date_m.groups()
            year_val = int(year) if year else (current_date.year if current_date else season_start.year)
            try:
                current_date = datetime.strptime(f"{mon}/{day}/{year_val}", "%b/%d/%Y")
            except Exception:
                current_date = season_start
            continue

        m = MATCH_LINE_RE.match(raw_line)
        if not m:
            continue
        if current_date is None:
            current_date = season_start

        time_str, home_name, away_name, home_score, away_score = m.groups()
        try:
            hm, _ = time_str.split(".")
            # conserver la date avec heure approx en UTC
            dt = current_date.replace(hour=int(hm), minute=0)
        except Exception:
            dt = current_date

        matches.append(
            {
                "league_name": league_name,
                "season_id": None,
                "season_label": season_label,
                "season_start": season_start,
                "season_end": season_end,
                "date": dt,
                "home_team": {"name": home_name.strip()},
                "away_team": {"name": away_name.strip()},
                "home_score": int(home_score),
                "away_score": int(away_score),
                "team_stats": {},
                "player_stats": [],
                "coaches": [],
                "game_id": f"{league_name}-{season_label}-{len(matches)+1}",
            }
        )

    return matches


def scrape_openfootball_matches():
    if not BASE_DIR.parent.exists():
        log_warn(f"Dossier OpenFootball introuvable : {BASE_DIR.parent}")
        return []

    all_matches: List[Dict[str, Any]] = []
    for folder, cfg in LEAGUE_CONFIG.items():
        base_dir = cfg.get("base", BASE_DIR)
        league_dir = base_dir / folder
        if not league_dir.exists():
            log_warn(f"[OPENFOOTBALL] dossier manquant : {league_dir}")
            continue

        league_name = cfg["league_name"]
        pattern = cfg.get("glob", "*.txt")
        league_matches: List[Dict[str, Any]] = []

        # recherche récursive pour couvrir les ligues avec fichiers à plat (france) ou par dossier (england, etc.)
        for fpath in sorted(league_dir.rglob(pattern)):
            if "france" in folder and not fpath.name.endswith("fr1.txt"):
                continue
            league_matches.extend(_parse_file(fpath, league_name))

        log_ok(f"[OPENFOOTBALL] {league_name}: {len(league_matches)} matchs collectés.")
        all_matches.extend(league_matches)

    log_ok(f"[OPENFOOTBALL] TOTAL : {len(all_matches)} matchs collectés (5 ligues).")
    return all_matches


__all__ = ["scrape_openfootball_matches"]
