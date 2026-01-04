-- Multi-schémas par ligue : créer schémas + tables identiques dans chacun.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE
  s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['nba','lnh','lbwl','pl','ligue1','bl1','sa','pd']
  LOOP
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I;', s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.league (
        leagueId uuid NOT NULL DEFAULT gen_random_uuid(),
        leagueName varchar NOT NULL,
        CONSTRAINT %I_league_pkey PRIMARY KEY (leagueId)
      );
    $fmt$, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.season (
        seasonId uuid NOT NULL DEFAULT gen_random_uuid(),
        leagueId uuid NOT NULL,
        seasonLabel varchar NOT NULL,
        startDate timestamptz NOT NULL,
        endDate timestamptz NOT NULL,
        CONSTRAINT %I_season_pkey PRIMARY KEY (seasonId),
        CONSTRAINT %I_season_leagueId_fkey FOREIGN KEY (leagueId) REFERENCES %I.league(leagueId)
      );
    $fmt$, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.stadium (
        stadiumId uuid NOT NULL DEFAULT gen_random_uuid(),
        stadiumName varchar NOT NULL,
        stadiumCity varchar NOT NULL,
        CONSTRAINT %I_stadium_pkey PRIMARY KEY (stadiumId)
      );
    $fmt$, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.statName (
        statNameId uuid NOT NULL DEFAULT gen_random_uuid(),
        statNameLib varchar NOT NULL,
        CONSTRAINT %I_statName_pkey PRIMARY KEY (statNameId)
      );
    $fmt$, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.team (
        teamId uuid NOT NULL DEFAULT gen_random_uuid(),
        teamName varchar NOT NULL,
        stadiumId uuid NULL,
        leagueId uuid NULL,
        externalId varchar NULL,
        CONSTRAINT %I_team_pkey PRIMARY KEY (teamId),
        CONSTRAINT %I_team_stadiumId_fkey FOREIGN KEY (stadiumId) REFERENCES %I.stadium(stadiumId),
        CONSTRAINT %I_team_leagueId_fkey FOREIGN KEY (leagueId) REFERENCES %I.league(leagueId)
      );
    $fmt$, s, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.coach (
        coachId uuid NOT NULL DEFAULT gen_random_uuid(),
        coachName varchar NOT NULL,
        externalId varchar NULL,
        CONSTRAINT %I_coach_pkey PRIMARY KEY (coachId)
      );
    $fmt$, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.coachTeam (
        coachId uuid NOT NULL,
        teamId uuid NOT NULL,
        startDate timestamptz NOT NULL,
        endDate timestamptz,
        role varchar NULL,
        CONSTRAINT %I_coachTeam_pkey PRIMARY KEY (coachId, teamId, startDate),
        CONSTRAINT %I_coachTeam_coachId_fkey FOREIGN KEY (coachId) REFERENCES %I.coach(coachId),
        CONSTRAINT %I_coachTeam_teamId_fkey FOREIGN KEY (teamId) REFERENCES %I.team(teamId)
      );
    $fmt$, s, s, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.job (
        jobId bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
        jobName varchar NOT NULL,
        CONSTRAINT %I_job_pkey PRIMARY KEY (jobId)
      );
    $fmt$, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.player (
        playerId uuid NOT NULL DEFAULT gen_random_uuid(),
        playerName varchar NOT NULL,
        playerFirstName varchar,
        playerNumber smallint,
        playerJob bigint,
        isActif boolean,
        externalId varchar NULL,
        teamId uuid NULL,
        CONSTRAINT %I_player_pkey PRIMARY KEY (playerId),
        CONSTRAINT %I_player_teamId_fkey FOREIGN KEY (teamId) REFERENCES %I.team(teamId),
        CONSTRAINT %I_player_job_fkey FOREIGN KEY (playerJob) REFERENCES %I.job(jobId)
      );
    $fmt$, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.playerHistory (
        playerId uuid NOT NULL,
        playerName varchar NOT NULL,
        playerFirstName varchar,
        playerNumber smallint,
        playerJob bigint,
        teamId uuid NULL,
        startDate timestamptz NOT NULL,
        endDate timestamptz,
        CONSTRAINT %I_playerHistory_pkey PRIMARY KEY (playerId, startDate),
        CONSTRAINT %I_playerHistory_teamId_fkey FOREIGN KEY (teamId) REFERENCES %I.team(teamId),
        CONSTRAINT %I_playerHistory_job_fkey FOREIGN KEY (playerJob) REFERENCES %I.job(jobId),
        CONSTRAINT %I_playerHistory_player_fkey FOREIGN KEY (playerId) REFERENCES %I.player(playerId)
      );
    $fmt$, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.match (
        matchId uuid NOT NULL DEFAULT gen_random_uuid(),
        startDateMatch timestamptz NOT NULL,
        endDateMatch timestamptz,
        stadiumId uuid,
        leagueId uuid,
        seasonId uuid,
        homeTeamId uuid,
        awayTeamId uuid,
        externalId varchar NULL,
        CONSTRAINT %I_match_pkey PRIMARY KEY (matchId),
        CONSTRAINT %I_match_leagueId_fkey FOREIGN KEY (leagueId) REFERENCES %I.league(leagueId),
        CONSTRAINT %I_match_stadiumId_fkey FOREIGN KEY (stadiumId) REFERENCES %I.stadium(stadiumId),
        CONSTRAINT %I_match_seasonId_fkey FOREIGN KEY (seasonId) REFERENCES %I.season(seasonId),
        CONSTRAINT %I_match_homeTeamId_fkey FOREIGN KEY (homeTeamId) REFERENCES %I.team(teamId),
        CONSTRAINT %I_match_awayTeamId_fkey FOREIGN KEY (awayTeamId) REFERENCES %I.team(teamId)
      );
    $fmt$, s, s, s, s, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.statPlayerMatch (
        playerId uuid NOT NULL,
        matchId uuid NOT NULL,
        statNameId uuid NOT NULL,
        value double precision,
        CONSTRAINT %I_statPlayerMatch_pkey PRIMARY KEY (playerId, matchId, statNameId),
        CONSTRAINT %I_statPlayerMatch_playerId_fkey FOREIGN KEY (playerId) REFERENCES %I.player(playerId),
        CONSTRAINT %I_statPlayerMatch_matchId_fkey FOREIGN KEY (matchId) REFERENCES %I.match(matchId),
        CONSTRAINT %I_statPlayerMatch_statNameId_fkey FOREIGN KEY (statNameId) REFERENCES %I.statName(statNameId)
      );
    $fmt$, s, s, s, s, s, s);

    EXECUTE format($fmt$
      CREATE TABLE IF NOT EXISTS %I.statTeamMatch (
        teamId uuid NOT NULL,
        matchId uuid NOT NULL,
        statNameId uuid NOT NULL,
        value double precision,
        CONSTRAINT %I_statTeamMatch_pkey PRIMARY KEY (teamId, matchId, statNameId),
        CONSTRAINT %I_statTeamMatch_matchId_fkey FOREIGN KEY (matchId) REFERENCES %I.match(matchId),
        CONSTRAINT %I_statTeamMatch_teamId_fkey FOREIGN KEY (teamId) REFERENCES %I.team(teamId),
        CONSTRAINT %I_statTeamMatch_statNameId_fkey FOREIGN KEY (statNameId) REFERENCES %I.statName(statNameId)
      );
    $fmt$, s, s, s, s, s, s);

  END LOOP;
END$$;
