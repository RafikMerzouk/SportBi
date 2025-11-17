import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


# =========================
# Config DB (depuis l'env docker-compose)
# =========================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "lbwl")
DB_USER = os.getenv("DB_USER", "lbwl_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lbwl_pass")

ENGINE_URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'


# =========================
# Helpers BDD
# =========================
@st.cache_resource(show_spinner=False)
def get_engine():
    return create_engine(ENGINE_URL, pool_pre_ping=True)


def read_sql_df(q: str, params: dict | None = None, limit: int | None = None) -> pd.DataFrame:
    """Lecture DataFrame avec LIMIT optionnel si non présent dans la requête."""
    sql = q.strip()
    if limit and " limit " not in sql.lower():
        sql = sql.rstrip(";") + f" LIMIT {int(limit)}"
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def export_csv(df: pd.DataFrame, filename: str, label: str = "Télécharger CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")


# =========================
# UI de base
# =========================
st.set_page_config(page_title="LBWL Data Explorer", layout="wide")
st.sidebar.title("🏀 LBWL Explorer")
page = st.sidebar.radio("Navigation", ["Dashboard", "Matches", "Teams", "SQL (read-only)"])


# =========================
# Pré-chargements sûrs (avec alias corrects)
# =========================
try:
    teams_df = read_sql_df(
        """
        SELECT
          teamid   AS "teamId",
          teamname AS "teamName"
        FROM team
        ORDER BY teamname;
        """
    )
except Exception as e:
    st.error(f"Connexion BDD impossible : {e}")
    st.stop()

if teams_df is None or teams_df.empty:
    TEAM_NAME_TO_ID: dict[str, str] = {}
    TEAM_NAMES: list[str] = ["(Tous)"]
else:
    TEAM_NAME_TO_ID = {r["teamName"]: r["teamId"] for r in teams_df.to_dict(orient="records")}
    TEAM_NAMES = ["(Tous)"] + list(TEAM_NAME_TO_ID.keys())


# =====================================================================
# PAGE : DASHBOARD
# =====================================================================
if page == "Dashboard":
    st.title("📊 Dashboard")

    # KPIs rapides
    cols = st.columns(4)
    try:
        k_leagues = read_sql_df('SELECT COUNT(*) AS "count" FROM league;').iloc[0]["count"]
        k_teams   = read_sql_df('SELECT COUNT(*) AS "count" FROM team;').iloc[0]["count"]
        k_match   = read_sql_df('SELECT COUNT(*) AS "count" FROM match;').iloc[0]["count"]
        k_stats   = read_sql_df('SELECT COUNT(*) AS "count" FROM statTeamMatch;').iloc[0]["count"]
    except Exception as e:
        st.error(f"Erreur chargement métriques : {e}")
    else:
        cols[0].metric("Ligues", k_leagues)
        cols[1].metric("Équipes", k_teams)
        cols[2].metric("Matchs", k_match)
        cols[3].metric("Stats équipe-match", k_stats)

    st.markdown("### Derniers matchs (30)")
    # NB : le schéma ne stocke pas home/away. On utilise un ordre déterministe des noms.
    q_last = """
      WITH sc AS (
        SELECT
          stm.matchid      AS "matchId",
          stm.teamid       AS "teamId",
          stm.value        AS "score"
        FROM statTeamMatch stm
        JOIN statName sn ON sn.statNameId = stm.statNameId
        WHERE UPPER(sn.statNameLib) = 'SCORE'
      ),
      tlist AS (
        SELECT
          m.matchid        AS "matchId",
          array_agg(t.teamname ORDER BY t.teamname) AS "teams"
        FROM match m
        JOIN statTeamMatch s ON s.matchid = m.matchid
        JOIN team t ON t.teamid = s.teamid
        GROUP BY m.matchid
      )
      SELECT
        m.startdatematch  AS "date",
        (tlist.teams)[1]  AS "home",
        (tlist.teams)[2]  AS "away",
        MAX(CASE WHEN sc.teamId = (SELECT t1.teamid FROM team t1 WHERE t1.teamname = (tlist.teams)[1]) THEN sc.score END) AS "home_score",
        MAX(CASE WHEN sc.teamId = (SELECT t2.teamid FROM team t2 WHERE t2.teamname = (tlist.teams)[2]) THEN sc.score END) AS "away_score"
      FROM match m
      JOIN tlist ON tlist."matchId" = m.matchid
      LEFT JOIN sc ON sc."matchId" = m.matchid
      GROUP BY m.startdatematch, tlist.teams
      ORDER BY "date" DESC
      LIMIT 30;
    """
    try:
        df_last = read_sql_df(q_last)
        st.dataframe(df_last, use_container_width=True, height=460)
        if not df_last.empty:
            export_csv(df_last, "lbwl_last_matches.csv", "Exporter (CSV)")
    except Exception as e:
        st.info("Pas encore de données ou jointure différente. Scrappe d’abord puis reviens 😉")


# =====================================================================
# PAGE : MATCHES
# =====================================================================
elif page == "Matches":
    st.title("📅 Matches")
    st.caption("Filtre par dates et équipes | scores si statName = 'SCORE'.")

    today = date.today()
    default_start = today - relativedelta(months=18)

    c1, c2, c3, c4 = st.columns([1,1,1,1.6])
    with c1:
        d_start = st.date_input("Date min", value=default_start, format="DD/MM/YYYY")
    with c2:
        d_end = st.date_input("Date max", value=today, format="DD/MM/YYYY")
    with c3:
        sel_home = st.selectbox("Équipe A", TEAM_NAMES, index=0)
    with c4:
        sel_away = st.selectbox("Équipe B", TEAM_NAMES, index=0)

    # Requête lisible, aliasée, et limitée
    base_q = """
      WITH score AS (
        SELECT
          stm.matchid      AS "matchId",
          stm.teamid       AS "teamId",
          stm.value        AS "score"
        FROM statTeamMatch stm
        JOIN statName sn ON sn.statNameId = stm.statNameId
        WHERE UPPER(sn.statNameLib) = 'SCORE'
      ),
      teams_per_match AS (
        SELECT
          m.matchid        AS "matchId",
          array_agg(t.teamname ORDER BY t.teamname) AS "teams"
        FROM match m
        JOIN statTeamMatch s ON s.matchid = m.matchid
        JOIN team t ON t.teamid = s.teamid
        GROUP BY m.matchid
      )
      SELECT
        m.startdatematch  AS "date",
        (tpm."teams")[1]  AS "home",
        (tpm."teams")[2]  AS "away",
        MAX(CASE WHEN sc."teamId" = (SELECT t1.teamid FROM team t1 WHERE t1.teamname = (tpm."teams")[1]) THEN sc."score" END) AS "home_score",
        MAX(CASE WHEN sc."teamId" = (SELECT t2.teamid FROM team t2 WHERE t2.teamname = (tpm."teams")[2]) THEN sc."score" END) AS "away_score"
      FROM match m
      JOIN teams_per_match tpm ON tpm."matchId" = m.matchid
      LEFT JOIN score sc ON sc."matchId" = m.matchid
      WHERE m.startdatematch BETWEEN :dmin AND :dmax
    """

    params = {
        "dmin": f"{d_start} 00:00:00",
        "dmax": f"{d_end} 23:59:59",
    }

    if sel_home != "(Tous)":
        base_q += ' AND (tpm."teams")[1] = :home '
        params["home"] = sel_home
    if sel_away != "(Tous)":
        base_q += ' AND (tpm."teams")[2] = :away '
        params["away"] = sel_away

    base_q += ' GROUP BY m.startdatematch, tpm."teams" ORDER BY "date" DESC '

    try:
        dfm = read_sql_df(base_q, params=params, limit=1000)
        st.dataframe(dfm, use_container_width=True, height=560)
        if not dfm.empty:
            export_csv(dfm, "lbwl_matches_filtered.csv", "Exporter (CSV)")
    except Exception as e:
        st.error(f"Erreur de chargement : {e}")


# =====================================================================
# PAGE : TEAMS
# =====================================================================
elif page == "Teams":
    st.title("🧾 Teams")
    st.caption("Répartition par ligue & volume de matchs référencés.")

    q = """
      SELECT
        t.teamname AS "team",
        l.leaguename AS "league",
        COUNT(DISTINCT m.matchid) AS "matches_count"
      FROM team t
      LEFT JOIN league l ON l.leagueid = t.leagueid
      LEFT JOIN statTeamMatch stm ON stm.teamid = t.teamid
      LEFT JOIN match m ON m.matchid = stm.matchid
      GROUP BY t.teamname, l.leaguename
      ORDER BY "matches_count" DESC NULLS LAST, "team" ASC;
    """
    try:
        dft = read_sql_df(q)
        st.dataframe(dft, use_container_width=True, height=620)
        if not dft.empty:
            export_csv(dft, "lbwl_teams_overview.csv", "Exporter (CSV)")
    except Exception as e:
        st.error(f"Erreur : {e}")


# =====================================================================
# PAGE : SQL (read-only)
# =====================================================================
elif page == "SQL (read-only)":
    st.title("🧪 SQL (read-only)")
    st.caption("Exécute uniquement des requêtes SELECT. Le résultat est limité par le curseur.")

    default_sql = 'SELECT matchid AS "matchId", startdatematch AS "startDateMatch" FROM match ORDER BY 2 DESC;'
    limit = st.slider("LIMIT", 10, 5000, 500, step=10)
    sql = st.text_area("Votre requête SELECT", value=default_sql, height=180)
    run = st.button("Exécuter")

    if run:
        q = sql.strip().rstrip(";")
        if not q.lower().startswith("select"):
            st.error("Seules les requêtes SELECT sont autorisées ici.")
        else:
            try:
                dfs = read_sql_df(q, limit=limit)
                st.success(f"{len(dfs)} ligne(s)")
                st.dataframe(dfs, use_container_width=True, height=620)
                if not dfs.empty:
                    export_csv(dfs, "lbwl_sql_result.csv", "Exporter (CSV)")
            except Exception as e:
                st.error(f"Erreur SQL : {e}")
