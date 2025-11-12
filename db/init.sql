-- Script d'init Postgres : on y mettra ton schema (sportStatsTronkCreate.sql).-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE public.coach (
  coachId uuid NOT NULL DEFAULT gen_random_uuid(),
  coachName character varying NOT NULL,
  CONSTRAINT coach_pkey PRIMARY KEY (coachId)
);
CREATE TABLE public.job (
  jobId bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  jobName character varying NOT NULL,
  CONSTRAINT job_pkey PRIMARY KEY (jobId)
);
CREATE TABLE public.league (
  leagueId uuid NOT NULL DEFAULT gen_random_uuid(),
  leagueName character varying NOT NULL,
  CONSTRAINT league_pkey PRIMARY KEY (leagueId)
);
CREATE TABLE public.stadium (
  stadiumId uuid NOT NULL DEFAULT gen_random_uuid(),
  stadiumName character varying NOT NULL,
  stadiumCity character varying NOT NULL,
  CONSTRAINT stadium_pkey PRIMARY KEY (stadiumId)
);
CREATE TABLE public.statName (
  statNameId uuid NOT NULL DEFAULT gen_random_uuid(),
  statNameLib character varying NOT NULL,
  CONSTRAINT statName_pkey PRIMARY KEY (statNameId)
);
CREATE TABLE public.team (
  teamId uuid NOT NULL DEFAULT gen_random_uuid(),
  teamName character varying NOT NULL,
  stadiumId uuid NULL,
  leagueId uuid NULL,
  CONSTRAINT team_pkey PRIMARY KEY (teamId),
  CONSTRAINT team_stadiumId_fkey FOREIGN KEY (stadiumId) REFERENCES public.stadium(stadiumId),
  CONSTRAINT team_leagueId_fkey FOREIGN KEY (leagueId) REFERENCES public.league(leagueId)
);
CREATE TABLE public.coachTeam (
  coachId uuid NOT NULL,
  teamId uuid NOT NULL,
  startDate timestamp with time zone NOT NULL,
  endDate timestamp with time zone,
  CONSTRAINT coachTeam_pkey PRIMARY KEY (coachId, teamId, startDate),
  CONSTRAINT coachTeam_coachId_fkey FOREIGN KEY (coachId) REFERENCES public.coach(coachId),
  CONSTRAINT coachTeam_teamId_fkey FOREIGN KEY (teamId) REFERENCES public.team(teamId)
);
CREATE TABLE public.player (
  playerId uuid NOT NULL DEFAULT gen_random_uuid(),
  playerName character varying NOT NULL,
  playerFirstName character varying,
  playerNumber smallint,
  playerJob bigint,
  isActif boolean,
  teamId uuid NULL,
  CONSTRAINT player_pkey PRIMARY KEY (playerId),
  CONSTRAINT player_teamId_fkey FOREIGN KEY (teamId) REFERENCES public.team(teamId),
  CONSTRAINT player_playerJob_fkey FOREIGN KEY (playerJob) REFERENCES public.job(jobId)
);
CREATE TABLE public.playerHistory (
  playerId uuid NOT NULL DEFAULT gen_random_uuid(),
  playerName character varying NOT NULL,
  playerFirstName character varying,
  playerNumber smallint,
  playerJob bigint,
  teamId uuid NULL,
  startDate timestamp with time zone NOT NULL,
  endDate timestamp with time zone,
  CONSTRAINT playerHistory_pkey PRIMARY KEY (playerId, startDate),
  CONSTRAINT playerHistory_teamId_fkey FOREIGN KEY (teamId) REFERENCES public.team(teamId),
  CONSTRAINT playerHistory_playerJob_fkey FOREIGN KEY (playerJob) REFERENCES public.job(jobId),
  CONSTRAINT playerHistory_playerId_fkey FOREIGN KEY (playerId) REFERENCES public.player(playerId)
);
CREATE TABLE public.match (
  matchId uuid NOT NULL DEFAULT gen_random_uuid(),
  startDateMatch timestamp with time zone NOT NULL,
  endDateMatch timestamp with time zone,
  stadiumId uuid,
  leagueId uuid,
  CONSTRAINT match_pkey PRIMARY KEY (matchId),
  CONSTRAINT match_leagueId_fkey FOREIGN KEY (leagueId) REFERENCES public.league(leagueId),
  CONSTRAINT match_stadiumId_fkey FOREIGN KEY (stadiumId) REFERENCES public.stadium(stadiumId)
);
CREATE TABLE public.statPlayerMatch (
  playerId uuid NOT NULL,
  matchId uuid NOT NULL,
  statNameId uuid NOT NULL,
  value double precision,
  CONSTRAINT statPlayerMatch_pkey PRIMARY KEY (playerId, matchId, statNameId),
  CONSTRAINT statPlayerMatch_playerId_fkey FOREIGN KEY (playerId) REFERENCES public.player(playerId),
  CONSTRAINT statPlayerMatch_matchId_fkey FOREIGN KEY (matchId) REFERENCES public.match(matchId),
  CONSTRAINT statPlayerMatch_statNameId_fkey FOREIGN KEY (statNameId) REFERENCES public.statName(statNameId)
);
CREATE TABLE public.statTeamMatch (
  teamId uuid NOT NULL,
  matchId uuid NOT NULL,
  statNameId uuid NOT NULL,
  value double precision,
  CONSTRAINT statTeamMatch_pkey PRIMARY KEY (teamId, matchId, statNameId),
  CONSTRAINT statTeamMatch_matchId_fkey FOREIGN KEY (matchId) REFERENCES public.match(matchId),
  CONSTRAINT statTeamMatch_teamId_fkey FOREIGN KEY (teamId) REFERENCES public.team(teamId),
  CONSTRAINT statTeamMatch_statNameId_fkey FOREIGN KEY (statNameId) REFERENCES public.statName(statNameId)
);
