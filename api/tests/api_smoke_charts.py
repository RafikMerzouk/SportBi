"""
Script de test : appelle l'API /render base64 pour vérifier l'accès aux données.
Génère 2-3 graphiques simples par ligue (nombre de matches par saison, total buts).
"""

import os
from pathlib import Path

import requests

API_URL = os.getenv("API_URL", "http://localhost:8080")
OUT_DIR = Path(os.getenv("OUT_DIR", "./tmp_api_charts"))

LEAGUES = [
    ("Premier League", "pl"),
    ("Ligue 1 McDonald's", "ligue1"),
    ("Bundesliga", "bl1"),
    ("Serie A", "sa"),
    ("LaLiga", "pd"),
    ("NBA", "nba"),
    ("Liqui Moly StarLigue", "lnh"),
    ("La Boulangère Wonderligue", "lbwl"),
]


def call_chart(sql: str, chart: dict, name: str, params: dict, schema: str | None):
    payload = {"sql": sql, "params": params, "chart": chart, "schema": schema}
    resp = requests.post(f"{API_URL}/render", json=payload, timeout=30)
    resp.raise_for_status()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.png"
    out.write_bytes(resp.content)
    print(f"OK {name} -> {out}")


def run():
    for league, schema in LEAGUES:
        safe = league.lower().replace(" ", "_").replace("'", "")
        # 1) Matches par saison
        sql_season = """
        SELECT s.seasonLabel AS saison, COUNT(m.matchId) AS matches
        FROM match m
        JOIN league l ON m.leagueId = l.leagueId
        LEFT JOIN season s ON m.seasonId = s.seasonId
        WHERE l.leagueName = :league
        GROUP BY 1
        ORDER BY 1
        """
        chart_season = {"type": "line", "x": "saison", "y": "matches", "title": f"{league} - matches par saison"}
        params = {"league": league}

        try:
            call_chart(sql_season, chart_season, f"{safe}_matches_par_saison", params, schema)
        except Exception as e:
            print(f"[WARN] {league} matches/saison: {e}")

        # 2) Buts/match en moyenne par saison (si score disponible)
        sql_goals = """
        WITH scores AS (
          SELECT m.matchId, m.seasonId, stm.value AS score, m.homeTeamId, stm.teamId
          FROM match m
          JOIN league l ON m.leagueId = l.leagueId
          JOIN statTeamMatch stm ON stm.matchId = m.matchId
          JOIN statName sn ON stm.statNameId = sn.statNameId AND sn.statNameLib = 'SCORE'
          WHERE l.leagueName = :league
        ), home_away AS (
          SELECT m.matchId,
                 MAX(CASE WHEN stm.teamId = m.homeTeamId THEN stm.value END) AS home_score,
                 MAX(CASE WHEN stm.teamId = m.awayTeamId THEN stm.value END) AS away_score,
                 m.seasonId
          FROM match m
          JOIN league l ON m.leagueId = l.leagueId AND l.leagueName = :league
          JOIN statTeamMatch stm ON stm.matchId = m.matchId
          JOIN statName sn ON stm.statNameId = sn.statNameId AND sn.statNameLib = 'SCORE'
          GROUP BY m.matchId, m.seasonId
        )
        SELECT COALESCE(s.seasonLabel,'N/A') AS saison,
               AVG(home_score + away_score) AS buts_moy
        FROM home_away ha
        LEFT JOIN season s ON ha.seasonId = s.seasonId
        GROUP BY 1
        ORDER BY 1
        """
        chart_goals = {"type": "line", "x": "saison", "y": "buts_moy", "title": f"{league} - buts/match"}
        try:
            call_chart(sql_goals, chart_goals, f"{safe}_buts_par_match", params, schema)
        except Exception as e:
            print(f"[WARN] {league} buts/match: {e}")

        # 3) Répartition des victoires domicile/extérieur (si scores)
        sql_home_away = """
        WITH scores AS (
          SELECT m.matchId,
                 MAX(CASE WHEN stm.teamId = m.homeTeamId AND sn.statNameLib = 'SCORE' THEN stm.value END) AS home_score,
                 MAX(CASE WHEN stm.teamId = m.awayTeamId AND sn.statNameLib = 'SCORE' THEN stm.value END) AS away_score
          FROM match m
          JOIN league l ON m.leagueId = l.leagueId AND l.leagueName = :league
          LEFT JOIN statTeamMatch stm ON stm.matchId = m.matchId
          LEFT JOIN statName sn ON stm.statNameId = sn.statNameId
          GROUP BY m.matchId
        )
        SELECT
          COALESCE(SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END),0) AS home_win,
          COALESCE(SUM(CASE WHEN home_score < away_score THEN 1 ELSE 0 END),0) AS away_win,
          COALESCE(SUM(CASE WHEN home_score = away_score THEN 1 ELSE 0 END),0) AS draw
        FROM scores
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """
        chart_home_away = {
            "type": "pie",
            "values": ["home_win", "away_win", "draw"],
            "title": f"{league} - répartition issues",
        }
        try:
            call_chart(sql_home_away, chart_home_away, f"{safe}_issues", params, schema)
        except Exception as e:
            print(f"[WARN] {league} issues: {e}")


if __name__ == "__main__":
    run()
