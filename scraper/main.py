# scraper/main.py

from utils.log_utils import log_start, log_done, log_warn, log_err
from lbwl_scraper import scrape_wonderligue_calendar
from ingest import ingest_matches


if __name__ == "__main__":
    log_start("Lancement du scraper La Boulangère Wonderligue...")

    try:
        matches = scrape_wonderligue_calendar()
        if not matches:
            log_warn("Aucun match parsé. Vérifie la structure HTML ou les sélecteurs.")
        else:
            ingest_matches(matches)
            log_done(f"Ingestion terminée avec succès. {len(matches)} matchs traités.")
    except Exception as e:
        log_err(f"Exception fatale : {e}")
        raise
