from utils.db_utils import (
    get_or_create_league,
    get_or_create_team,
    get_or_create_match,
    get_or_create_season,
    upsert_team_score_for_match,
)
from utils.log_utils import log_ok, log_info


DEFAULT_LEAGUE_NAME = "La Boulangère Wonderligue"


def _to_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_team(value):
    """
    Retourne (nom, external_id_str) à partir d'un dict ou string.
    """
    if isinstance(value, dict):
        ext = value.get("external_id")
        ext_str = str(ext) if ext is not None else None
        return value.get("name"), ext_str
    return value, None


def ingest_matches(matches, league_name=None):
    """
    Ingestion générique : scores + stats équipes.
    """
    if not matches:
        log_info("Aucun match à ingérer.")
        return

    # Evite de créer une ligue agrégée "football-data.org (...)" :
    # si un libellé agrégé est passé, on bascule sur le league_name du match.
    if league_name and "football-data.org" in league_name and matches[0].get("league_name"):
        resolved_league = matches[0]["league_name"]
    else:
        resolved_league = league_name or matches[0].get("league_name") or DEFAULT_LEAGUE_NAME

    # Ligue par défaut
    default_league_id = get_or_create_league(resolved_league)
    log_ok(f"Ligue prête : {resolved_league} ({default_league_id})")

    for m in matches:
        current_league = m.get("league_name") or resolved_league
        if current_league != resolved_league:
            current_league_id = get_or_create_league(current_league)
        else:
            current_league_id = default_league_id

        home_name, home_ext = _extract_team(m["home_team"])
        away_name, away_ext = _extract_team(m["away_team"])

        home_team_id = get_or_create_team(home_name, current_league_id, home_ext, league_name=current_league)
        away_team_id = get_or_create_team(away_name, current_league_id, away_ext, league_name=current_league)

        season_id = m.get("season_id")
        if not season_id and m.get("season_label"):
            start_dt = m.get("season_start") or (m["date"].replace(month=7, day=1) if m.get("date") else None)
            end_dt = m.get("season_end") or (start_dt.replace(year=start_dt.year + 1) if start_dt else None)
            if start_dt and end_dt:
                season_id = get_or_create_season(current_league_id, m["season_label"], start_dt, end_dt, league_name=current_league)

        match_id = get_or_create_match(
            start_dt=m["date"],
            league_id=current_league_id,
            stadium_id=None,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            external_id=m.get("game_id") or m.get("external_id"),
            league_name=current_league,
        )

        hs = _to_number(m.get("home_score"))
        if hs is not None:
            upsert_team_score_for_match(home_team_id, match_id, hs, league_name=current_league)

        as_ = _to_number(m.get("away_score"))
        if as_ is not None:
            upsert_team_score_for_match(away_team_id, match_id, as_, league_name=current_league)

        team_stats = m.get("team_stats") or {}
        for label, value in (team_stats.get("home") or {}).items():
            num = _to_number(value)
            if num is None:
                continue
            upsert_team_score_for_match(home_team_id, match_id, num, stat_label=label, league_name=current_league)
        for label, value in (team_stats.get("away") or {}).items():
            num = _to_number(value)
            if num is None:
                continue
            upsert_team_score_for_match(away_team_id, match_id, num, stat_label=label, league_name=current_league)

        log_ok(
            f"Ingestion/MàJ : {home_name} {m.get('home_score')} - "
            f"{m.get('away_score')} {away_name} ({m['date']})"
        )
