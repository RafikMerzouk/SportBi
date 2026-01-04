# scraper/main.py

from utils.log_utils import log_start, log_done, log_warn, log_err
from lbwl_scraper import scrape_wonderligue_calendar, LEAGUE_NAME as LBWL_LEAGUE_NAME
from lnh_scraper import scrape_lnh_calendar, LEAGUE_NAME as LNH_LEAGUE_NAME
from nba_scraper import scrape_nba_games, LEAGUE_NAME as NBA_LEAGUE_NAME
from football_data_scraper import scrape_football_data_matches
from openfootball_scraper import scrape_openfootball_matches
from ingest import ingest_matches
from nba_ingest import ingest_nba_games
from lbwl_ingest import ingest_lbwl_games


if __name__ == "__main__":
    # log_start("Lancement des scrapers SportBi...")
    # log_done("Ingestion skip (commente pour activer les scrapers multi-ligues).")
    # exit(0)

    scrapers = [
        #(LBWL_LEAGUE_NAME, scrape_wonderligue_calendar, ingest_lbwl_games),
        #(LNH_LEAGUE_NAME, scrape_lnh_calendar, ingest_matches),
        (NBA_LEAGUE_NAME, scrape_nba_games, ingest_nba_games),
        # Chaque match football-data porte son propre league_name (PL, Ligue 1, etc.).
        # On laisse ingest_matches utiliser match["league_name"] pour créer 5 ligues distinctes.
        #("openfootball (PL/L1/BL1/SA/PD)", scrape_openfootball_matches, ingest_matches),
    ]

    for league_name, scraper, ingestor in scrapers:
        log_start(f"Scraping {league_name}...")
        try:
            if scraper is scrape_nba_games:
                def _ingest_season(games, season_label):
                    if not games:
                        log_warn(f"[NBA] Saison {season_label}: aucun match parsé.")
                        return
                    ingest_nba_games(games, league_name=league_name)
                    log_done(f"[NBA] Saison {season_label}: ingestion OK ({len(games)} matchs).")

                matches = scraper(on_season_done=_ingest_season)
                log_done(f"{league_name}: scraping terminé ({len(matches)} matchs cumulés).")
            else:
                if scraper is scrape_football_data_matches:
                    def _ingest_competition(matches_chunk, comp_label):
                        if not matches_chunk:
                            log_warn(f"[{comp_label}] aucun match parsé.")
                            return
                        ingestor(matches_chunk, league_name=matches_chunk[0].get("league_name"))
                        log_done(f"[{comp_label}] ingestion OK ({len(matches_chunk)} matchs).")

                    matches = scraper(on_competition_done=_ingest_competition)
                    log_done(f"{league_name}: scraping terminé ({len(matches)} matchs cumulés).")
                else:
                    matches = scraper()
                    if not matches:
                        log_warn(f"{league_name}: aucun match parsé, vérifier la structure HTML.")
                        continue
                    ingestor(matches, league_name=league_name)
                    log_done(f"{league_name}: ingestion OK ({len(matches)} éléments).")
        except Exception as e:
            log_err(f"{league_name}: exception fatale : {e}")
            raise
