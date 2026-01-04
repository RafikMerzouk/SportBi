from datetime import datetime

from utils.db_utils import (
    get_or_create_league,
    get_or_create_team,
    get_or_create_match,
    upsert_team_score_for_match,
    get_or_create_player,
    upsert_player_stat_for_match,
    get_or_create_season,
    upsert_player_history,
    get_or_create_coach,
    upsert_coach_team,
)
from utils.log_utils import log_ok, log_info


LBWL_STAT_LABELS = [
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
    "MIN",
    "FGM",
    "FGA",
    "FG3M",
    "FG3A",
    "FTM",
    "FTA",
]


def ensure_stat_labels():
    for label in LBWL_STAT_LABELS:
        upsert_team_score_for_match  # noop to keep import; labels auto-créés via upsert_player_stat_for_match


def _season_from_date(dt: datetime) -> tuple[str, datetime, datetime]:
    year = dt.year
    if dt.month >= 7:
        start_year = year
    else:
        start_year = year - 1
    label = f"{start_year}-{str(start_year + 1)[-2:]}"
    return label, datetime(start_year, 7, 1), datetime(start_year + 1, 7, 1)


def ingest_lbwl_games(games: list[dict], league_name: str):
    if not games:
        return

    def _to_number(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    league_id = get_or_create_league(league_name)
    log_ok(f"Ligue prête : {league_name} ({league_id})")

    for game in games:
        season_label, season_start, season_end = _season_from_date(game["date"])
        season_id = get_or_create_season(league_id, season_label, season_start, season_end, league_name=league_name)

        home_team = game["home_team"]
        away_team = game["away_team"]

        home_team_id = get_or_create_team(home_team["name"], league_id, external_id=home_team.get("external_id"), league_name=league_name)
        away_team_id = get_or_create_team(away_team["name"], league_id, external_id=away_team.get("external_id"), league_name=league_name)

        match_id = get_or_create_match(
            start_dt=game["date"],
            league_id=league_id,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            external_id=game.get("game_id"),
            league_name=league_name,
        )

        if game.get("home_score") is not None:
            num = _to_number(game["home_score"])
            if num is not None:
                upsert_team_score_for_match(home_team_id, match_id, num, league_name=league_name)
        if game.get("away_score") is not None:
            num = _to_number(game["away_score"])
            if num is not None:
                upsert_team_score_for_match(away_team_id, match_id, num, league_name=league_name)

        # Team stats
        for label, val in (game.get("team_stats", {}).get("home") or {}).items():
            num = _to_number(val)
            if num is None:
                continue
            upsert_team_score_for_match(home_team_id, match_id, num, stat_label=label)
        for label, val in (game.get("team_stats", {}).get("away") or {}).items():
            num = _to_number(val)
            if num is None:
                continue
            upsert_team_score_for_match(away_team_id, match_id, num, stat_label=label)

        # Coaches
        for coach in game.get("coaches", []):
            coach_id = get_or_create_coach(coach["name"], external_id=coach.get("external_id"), league_name=league_name)
            upsert_coach_team(
                coach_id,
                home_team_id if coach.get("team") == "home" else away_team_id,
                start_date=game["date"],
                end_date=None,
                role=coach.get("role"),
                league_name=league_name,
            )

        # Player stats
        for ps in game.get("player_stats", []):
            player_id = get_or_create_player(
                full_name=ps["player_name"],
                first_name=ps.get("first_name"),
                number=ps.get("number"),
                job_id=None,
                is_active=None,
                team_id=None,
                external_id=ps.get("player_external_id"),
                league_name=league_name,
            )
            upsert_player_history(
                player_id=player_id,
                team_id=home_team_id if ps["team_side"] == "home" else away_team_id,
                start_date=game["date"],
                end_date=None,
                number=ps.get("number"),
                job_id=None,
                league_name=league_name,
            )
            for stat_label, stat_value in ps["stats"].items():
                if stat_value is None:
                    continue
                upsert_player_stat_for_match(player_id, match_id, stat_label, stat_value, league_name=league_name)

        log_info(
            f"[LBWL] Ingestion match {game.get('game_id')} "
            f"{home_team['name']} {game.get('home_score')} - "
            f"{game.get('away_score')} {away_team['name']}"
        )

    log_ok(f"[LBWL] Ingestion terminée : {len(games)} matchs.")
