from datetime import datetime

from utils.db_utils import (
    get_or_create_league,
    get_or_create_team,
    get_or_create_match,
    get_or_create_stat_name,
    upsert_team_score_for_match,
    get_or_create_player,
    upsert_player_stat_for_match,
    get_or_create_season,
    upsert_player_history,
)
from utils.log_utils import log_ok, log_info


NBA_STAT_LABELS = [
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
    "PLUS_MINUS",
]


def ensure_stat_labels():
    for label in NBA_STAT_LABELS:
        get_or_create_stat_name(label)


def ingest_nba_games(games: list[dict], league_name: str):
    if not games:
        return

    ensure_stat_labels()

    league_id = get_or_create_league(league_name)
    log_ok(f"Ligue prête : {league_name} ({league_id})")

    for game in games:
        season_label = game["season_label"]
        season_id = get_or_create_season(
            league_id,
            season_label,
            game["season_start"],
            game["season_end"],
            league_name=league_name,
        )

        home_team_id = get_or_create_team(
            game["home_team"]["name"],
            league_id=league_id,
            external_id=game["home_team"]["external_id"],
            league_name=league_name,
        )
        away_team_id = get_or_create_team(
            game["away_team"]["name"],
            league_id=league_id,
            external_id=game["away_team"]["external_id"],
            league_name=league_name,
        )

        match_id = get_or_create_match(
            start_dt=game["date"],
            league_id=league_id,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            external_id=game.get("game_id"),
            league_name=league_name,
        )

        # Scores équipe
        if game.get("home_score") is not None:
            upsert_team_score_for_match(home_team_id, match_id, game["home_score"], league_name=league_name)
        if game.get("away_score") is not None:
            upsert_team_score_for_match(away_team_id, match_id, game["away_score"], league_name=league_name)

        # Stats joueurs
        for ps in game.get("player_stats", []):
            player_id = get_or_create_player(
                full_name=ps["player_name"],
                first_name=None,
                number=None,
                job_id=None,
                is_active=None,
                team_id=None,
                external_id=ps["player_external_id"],
                league_name=league_name,
            )
            # Historique : rattache l'équipe du match
            upsert_player_history(
                player_id=player_id,
                team_id=home_team_id if ps["team_external_id"] == game["home_team"]["external_id"] else away_team_id,
                start_date=game["date"],
                end_date=None,
                number=None,
                job_id=None,
                league_name=league_name,
            )

            for stat_label, stat_value in ps["stats"].items():
                if stat_value is None:
                    continue
                upsert_player_stat_for_match(player_id, match_id, stat_label, stat_value, league_name=league_name)

        log_info(
            f"[NBA] Ingestion match {game.get('game_id')} "
            f"{game['home_team']['name']} {game.get('home_score')} - "
            f"{game.get('away_score')} {game['away_team']['name']}"
        )

    log_ok(f"[NBA] Ingestion terminée : {len(games)} matchs.")
