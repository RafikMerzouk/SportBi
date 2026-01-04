import psycopg2
from utils.config import DB_CONFIG

SCHEMA_MAPPING = {
    "NBA": "nba",
    "Liqui Moly StarLigue": "lnh",
    "La Boulangère Wonderligue": "lbwl",
    "Premier League": "pl",
    "Ligue 1 McDonald's": "ligue1",
    "Bundesliga": "bl1",
    "Serie A": "sa",
    "LaLiga": "pd",
}


def _schema_for_league(league_name: str | None) -> str:
    if not league_name:
        return "public"
    return SCHEMA_MAPPING.get(league_name, "public")


def get_connection(league_name: str | None = None):
    schema = _schema_for_league(league_name)
    return psycopg2.connect(options=f"-c search_path={schema},public", **DB_CONFIG)


def get_or_create_season(league_id: str, label: str, start_date, end_date, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT seasonId FROM season
                WHERE leagueId = %s AND seasonLabel = %s
                """,
                (league_id, label),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO season (seasonId, leagueId, seasonLabel, startDate, endDate)
                VALUES (gen_random_uuid(), %s, %s, %s, %s)
                RETURNING seasonId
                """,
                (league_id, label, start_date, end_date),
            )
            (season_id,) = cur.fetchone()
            return season_id


def get_or_create_league(league_name: str):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT leagueId FROM league WHERE leagueName = %s",
                (league_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO league (leagueId, leagueName)
                VALUES (gen_random_uuid(), %s)
                RETURNING leagueId
                """,
                (league_name,),
            )
            (league_id,) = cur.fetchone()
            return league_id


def get_or_create_team(team_name: str, league_id=None, external_id=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            ext_as_str = str(external_id) if external_id is not None else None
            if ext_as_str is not None:
                cur.execute(
                    "SELECT teamId FROM team WHERE externalId::text = %s",
                    (ext_as_str,),
                )
                row = cur.fetchone()
                if row:
                    return row[0]

            cur.execute(
                "SELECT teamId FROM team WHERE teamName = %s",
                (team_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO team (teamId, teamName, leagueId, externalId)
                VALUES (gen_random_uuid(), %s, %s, %s)
                RETURNING teamId
                """,
                (team_name, league_id, ext_as_str),
            )

            (team_id,) = cur.fetchone()
            return team_id


def get_or_create_stat_name(label: str, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT statNameId FROM statName WHERE statNameLib = %s",
                (label,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO statName (statNameId, statNameLib)
                VALUES (gen_random_uuid(), %s)
                RETURNING statNameId
                """,
                (label,),
            )
            (stat_id,) = cur.fetchone()
            return stat_id


def get_or_create_match(start_dt, league_id, stadium_id=None, season_id=None, home_team_id=None, away_team_id=None, external_id=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            if external_id:
                cur.execute(
                    """
                    SELECT matchId
                    FROM match
                    WHERE externalId = %s
                      AND leagueId = %s
                    """,
                    (external_id, league_id),
                )
                row = cur.fetchone()
                if row:
                    return row[0]

            cur.execute(
                """
                SELECT matchId
                FROM match
                WHERE startDateMatch = %s
                  AND leagueId = %s
                  AND (stadiumId IS NOT DISTINCT FROM %s)
                  AND (homeTeamId IS NOT DISTINCT FROM %s)
                  AND (awayTeamId IS NOT DISTINCT FROM %s)
                  AND (seasonId IS NOT DISTINCT FROM %s)
                """,
                (start_dt, league_id, stadium_id, home_team_id, away_team_id, season_id),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO match (matchId, startDateMatch, leagueId, stadiumId, seasonId, homeTeamId, awayTeamId, externalId)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s)
                RETURNING matchId
                """,
                (start_dt, league_id, stadium_id, season_id, home_team_id, away_team_id, external_id),
            )
            (match_id,) = cur.fetchone()
            return match_id


def get_or_create_player(full_name: str, first_name=None, number=None, job_id=None, is_active=None, team_id=None, external_id=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            if external_id:
                cur.execute(
                    "SELECT playerId FROM player WHERE externalId = %s",
                    (external_id,),
                )
                row = cur.fetchone()
                if row:
                    return row[0]

            cur.execute(
                "SELECT playerId FROM player WHERE playerName = %s AND (playerFirstName IS NOT DISTINCT FROM %s)",
                (full_name, first_name),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO player (playerId, playerName, playerFirstName, playerNumber, playerJob, isActif, teamId, externalId)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s)
                RETURNING playerId
                """,
                (full_name, first_name, number, job_id, is_active, team_id, external_id),
            )
            (player_id,) = cur.fetchone()
            return player_id


def upsert_player_history(player_id, team_id, start_date, end_date=None, number=None, job_id=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO playerHistory (playerId, playerName, playerFirstName, playerNumber, playerJob, teamId, startDate, endDate)
                SELECT p.playerId, p.playerName, p.playerFirstName, %s, %s, %s, %s, %s
                FROM player p
                WHERE p.playerId = %s
                ON CONFLICT (playerId, startDate)
                DO UPDATE SET
                  teamId = EXCLUDED.teamId,
                  endDate = EXCLUDED.endDate,
                  playerNumber = EXCLUDED.playerNumber,
                  playerJob = EXCLUDED.playerJob
                """,
                (number, job_id, team_id, start_date, end_date, player_id),
            )
            conn.commit()


def get_or_create_coach(coach_name: str, external_id=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            if external_id:
                cur.execute(
                    "SELECT coachId FROM coach WHERE externalId = %s",
                    (external_id,),
                )
                row = cur.fetchone()
                if row:
                    return row[0]

            cur.execute(
                "SELECT coachId FROM coach WHERE coachName = %s",
                (coach_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO coach (coachId, coachName, externalId)
                VALUES (gen_random_uuid(), %s, %s)
                RETURNING coachId
                """,
                (coach_name, external_id),
            )
            (coach_id,) = cur.fetchone()
            return coach_id


def upsert_coach_team(coach_id, team_id, start_date, end_date=None, role=None, league_name: str | None = None):
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO coachTeam (coachId, teamId, startDate, endDate, role)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (coachId, teamId, startDate)
                DO UPDATE SET endDate = EXCLUDED.endDate,
                              role = EXCLUDED.role
                """,
                (coach_id, team_id, start_date, end_date, role),
            )
            conn.commit()


def upsert_team_score_for_match(team_id, match_id, score_value, stat_label="SCORE", league_name: str | None = None):
    stat_id = get_or_create_stat_name(stat_label, league_name=league_name)

    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO statTeamMatch (teamId, matchId, statNameId, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (teamId, matchId, statNameId)
                DO UPDATE SET value = EXCLUDED.value
                """,
                (team_id, match_id, stat_id, float(score_value)),
            )
            conn.commit()


def upsert_player_stat_for_match(player_id, match_id, stat_label, stat_value, league_name: str | None = None):
    stat_id = get_or_create_stat_name(stat_label, league_name=league_name)
    with get_connection(league_name) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO statPlayerMatch (playerId, matchId, statNameId, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (playerId, matchId, statNameId)
                DO UPDATE SET value = EXCLUDED.value
                """,
                (player_id, match_id, stat_id, float(stat_value)),
            )
            conn.commit()
