from lbwl_scraper import LEAGUE_NAME
from utils.db_utils import (
    get_or_create_league,
    get_or_create_team,
    get_or_create_match,
    upsert_team_score_for_match,
)
from utils.log_utils import log_ok, log_info


def ingest_matches(matches):
    if not matches:
        log_info("Aucun match à ingérer.")
        return

    league_id = get_or_create_league(LEAGUE_NAME)
    log_ok(f"Ligue prête : {LEAGUE_NAME} ({league_id})")

    for m in matches:
        home_team_id = get_or_create_team(m["home_team"], league_id)
        away_team_id = get_or_create_team(m["away_team"], league_id)

        match_id = get_or_create_match(
            start_dt=m["date"],
            league_id=league_id,
            stadium_id=None,
        )

        if m.get("home_score") is not None:
            upsert_team_score_for_match(home_team_id, match_id, m["home_score"])

        if m.get("away_score") is not None:
            upsert_team_score_for_match(away_team_id, match_id, m["away_score"])

        log_ok(
            f"Ingestion/MàJ : {m['home_team']} {m.get('home_score')} - "
            f"{m.get('away_score')} {m['away_team']} ({m['date']})"
        )
