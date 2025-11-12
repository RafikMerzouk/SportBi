import psycopg2
from utils.config import DB_CONFIG


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_or_create_league(league_name: str):
    with get_connection() as conn:
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


def get_or_create_team(team_name: str, league_id=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT teamId FROM team WHERE teamName = %s",
                (team_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            if league_id:
                cur.execute(
                    """
                    INSERT INTO team (teamId, teamName, leagueId)
                    VALUES (gen_random_uuid(), %s, %s)
                    RETURNING teamId
                    """,
                    (team_name, league_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO team (teamId, teamName)
                    VALUES (gen_random_uuid(), %s)
                    RETURNING teamId
                    """,
                    (team_name,),
                )

            (team_id,) = cur.fetchone()
            return team_id


def get_or_create_stat_name(label: str):
    with get_connection() as conn:
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


def get_or_create_match(start_dt, league_id, stadium_id=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT matchId
                FROM match
                WHERE startDateMatch = %s
                  AND leagueId = %s
                  AND (stadiumId IS NOT DISTINCT FROM %s)
                """,
                (start_dt, league_id, stadium_id),
            )
            row = cur.fetchone()
            if row:
                return row[0]

            cur.execute(
                """
                INSERT INTO match (matchId, startDateMatch, leagueId, stadiumId)
                VALUES (gen_random_uuid(), %s, %s, %s)
                RETURNING matchId
                """,
                (start_dt, league_id, stadium_id),
            )
            (match_id,) = cur.fetchone()
            return match_id


def upsert_team_score_for_match(team_id, match_id, score_value, stat_label="SCORE"):
    stat_id = get_or_create_stat_name(stat_label)

    with get_connection() as conn:
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
