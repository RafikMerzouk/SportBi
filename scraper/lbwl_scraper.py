import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString

from utils.log_utils import log_info, log_ok, log_warn, log_err

BASE_URL = "https://basketlfb.com"
CALENDAR_ROOT = f"{BASE_URL}/laboulangerewonderligue/calendrier"
LEAGUE_NAME = "La Boulangère Wonderligue"

# Throttle : 3s min entre requêtes
RATE_LIMIT_SECONDS = 3.0
_last_request_ts = None
MAX_RETRIES = 5

# Pattern "LAN 59 LDN 43"
CODE_SCORE_LINE_RE = re.compile(
    r"\b([A-Z]{3})\s+(\d{1,3})\s+([A-Z]{3})\s+(\d{1,3})\b"
)

# Pattern "01/10 19:30"
DATE_TIME_RE = re.compile(
    r"\b(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\b"
)

# Pattern "Journée 7"
JOURNEE_RE = re.compile(
    r"Journée\s+(\d+)",
    re.IGNORECASE
)

# Pattern "Saison 2010-2011"
SAISON_RE = re.compile(
    r"Saison\s+(20\d{2})-(20\d{2})"
)

TEAM_CODE_MAP = {
    # === Ère La Boulangère Wonderligue / LFB récente ===
    # Codes confirmés sur le calendrier / fiches équipes LBWL
    "ANG": "UF Angers Basket 49",
    "LAN": "Basket Landes",
    "BOU": "Bourges Basket",
    "CHM": "Flammes Carolo Basket Ardennes (Charleville-Mézières)",
    "CNY": "Charnay Basket Bourgogne Sud",
    "CHA": "C'Chartres Basket Féminin",
    "LDN": "Landerneau Bretagne Basket",
    "MTP": "Lattes Montpellier (BLMA)",
    "LYO": "LDLC ASVEL Féminin",
    "ROC": "Roche Vendée Basket Club",
    "VIL": "ESBVA-LM Villeneuve d'Ascq",
    "TOU": "Toulouse Métropole Basket",

    # Certains flux / sites externes utilisent "MON" pour Montpellier :
    "MON": "Lattes Montpellier (BLMA)",

    # === Clubs historiques fréquents de l'élite féminine ===
    # (codes utilisés très classiquement en LFB ; utiles pour saisons antérieures)
    "TGB": "Tarbes Gespe Bigorre",
    "NAN": "Nantes Rezé Basket",
    "ARR": "Arras Pays d'Artois Basket Féminin",
    "NIS": "Cavigal Nice Basket",
    "USO": "USO Mondeville Basket",
    "USM": "USO Mondeville Basket",  # variante possible
    "SAH": "Saint-Amand Hainaut Basket",

    # === Sécurité / documentation ===
    # Si un code inconnu apparaît :
    # - le scraper loggue un warning via resolve_team(...)
    # - le code brut est inséré tel quel (mieux que planter).
}



# =========================
# HTTP helper (rate limit + retry)
# =========================

def fetch_html(url: str) -> str:
    """GET avec 3s min entre requêtes + retry simple (incluant 429)."""
    global _last_request_ts

    # Respect du délai global
    if _last_request_ts is not None:
        elapsed = time.time() - _last_request_ts
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log_info(f"[HTTP] GET {url} (try {attempt})")
            resp = requests.get(
                url,
                headers={"User-Agent": "lbwl-scraper/1.0 (contact: you@example.com)"},
                timeout=20,
            )

            if resp.status_code == 429:
                if attempt == MAX_RETRIES:
                    log_err(f"[HTTP] 429 Too Many Requests sur {url}, abandon.")
                    resp.raise_for_status()
                wait = RATE_LIMIT_SECONDS * attempt
                log_warn(f"[HTTP] 429 sur {url}, pause {wait:.1f}s avant retry.")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            _last_request_ts = time.time()
            log_ok(f"[HTTP] {url} -> {resp.status_code}")
            return resp.text

        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                log_err(f"[HTTP] Échec {url} après {attempt} essais : {e}")
                raise
            wait = RATE_LIMIT_SECONDS * attempt
            log_warn(f"[HTTP] Erreur sur {url}: {e} -> pause {wait:.1f}s puis retry.")
            time.sleep(wait)

    raise RuntimeError(f"Impossible de récupérer {url}")


# =========================
# Découverte des URLs calendrier
# =========================

def get_calendar_urls() -> list:
    """
    Depuis la page racine, récupère :
      - la page calendrier courante
      - toutes les /calendrier/saison/20xx exposées.
    """
    html = fetch_html(CALENDAR_ROOT)
    soup = BeautifulSoup(html, "html.parser")

    urls = {CALENDAR_ROOT}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/laboulangerewonderligue/calendrier/saison/" in href:
            urls.add(urljoin(BASE_URL, href))

    urls = sorted(urls)
    log_ok(f"[CAL] {len(urls)} page(s) calendrier détectées.")
    for u in urls:
        log_info(f"[CAL] -> {u}")
    return urls


# =========================
# Helpers parsing
# =========================

def _clean_text(node) -> str:
    if isinstance(node, NavigableString):
        return " ".join(str(node).strip().split())
    return " ".join(node.get_text(" ", strip=True).split())


def _resolve_team(code: str) -> str:
    return TEAM_CODE_MAP.get(code, code)


def detect_season_years(soup: BeautifulSoup, url: str) -> tuple[int, int]:
    """
    Détermine (start_year, end_year) pour la page :
      - via "Saison YYYY-YYYY" si présent
      - sinon via /saison/YYYY dans l'URL
      - sinon heuristique sur la date courante
    """
    text = soup.get_text(" ", strip=True)

    m = SAISON_RE.search(text)
    if m:
        start = int(m.group(1))
        end = int(m.group(2))
        return start, end

    m2 = re.search(r"/saison/(20\d{2})", url)
    if m2:
        start = int(m2.group(1))
        return start, start + 1

    # fallback : saison courante
    now = datetime.now()
    if now.month >= 7:
        return now.year, now.year + 1
    else:
        return now.year - 1, now.year


def find_context_date_and_journee(a_tag, season_start: int, season_end: int):
    """
    Pour un lien contenant 'XXX 59 YYY 43', remonte dans le flux
    pour trouver une date 'dd/mm hh:mm' + éventuellement 'Journée X'.
    Utilise les années de saison pour fixer l'année.
    """
    date_str = None
    journee = None
    steps = 0
    max_steps = 80

    for el in a_tag.previous_elements:
        if steps > max_steps:
            break
        steps += 1

        txt = _clean_text(el)
        if not txt:
            continue

        if not date_str:
            m = DATE_TIME_RE.search(txt)
            if m:
                date_str = m.group(0)

        if not journee:
            m2 = JOURNEE_RE.search(txt)
            if m2:
                journee = m2.group(1)

        if date_str and journee:
            break

    if not date_str:
        return None, journee

    m = DATE_TIME_RE.match(date_str)
    if not m:
        return None, journee

    day, month, hour, minute = map(int, m.groups())

    # Choix de l'année en fonction de la saison
    year = season_start if month >= 7 else season_end

    try:
        dt = datetime(year, month, day, hour, minute)
    except ValueError:
        return None, journee

    return dt, journee


def parse_matches_from_page(html: str, url: str) -> list[dict]:
    """
    Extrait les matchs d'une page calendrier :
      - détecte les "XXX 59 YYY 43"
      - remonte date + journée
      - applique la bonne année en fonction de la saison
    """
    soup = BeautifulSoup(html, "html.parser")
    season_start, season_end = detect_season_years(soup, url)

    matches: list[dict] = []
    found = 0

    for a in soup.find_all("a"):
        text = _clean_text(a)
        if not text:
            continue

        m = CODE_SCORE_LINE_RE.search(text)
        if not m:
            continue

        home_code, home_score, away_code, away_score = m.groups()

        dt, journee = find_context_date_and_journee(a, season_start, season_end)
        if not dt:
            continue

        match = {
            "date": dt,
            "home_team": _resolve_team(home_code),
            "away_team": _resolve_team(away_code),
            "home_score": int(home_score),
            "away_score": int(away_score),
            "journee": journee,
            "source_url": url,
        }

        matches.append(match)
        found += 1

    log_info(f"[PAGE] {url} -> {found} match(s) parsé(s).")
    return matches


# =========================
# Public API
# =========================

def scrape_wonderligue_calendar():
    """
    Scrape :
      - la page calendrier courante
      - toutes les pages /calendrier/saison/20xx
    et renvoie la liste dédupliquée de tous les matchs.
    """
    all_matches: list[dict] = []
    seen = set()

    urls = get_calendar_urls()
    log_info("[CAL] Début scraping multi-saisons.")

    for url in urls:
        html = fetch_html(url)
        page_matches = parse_matches_from_page(html, url)

        for m in page_matches:
            key = (
                m["date"],
                m["home_team"],
                m["away_team"],
                m["home_score"],
                m["away_score"],
                m["source_url"],
            )
            if key in seen:
                continue
            seen.add(key)
            all_matches.append(m)

    log_ok(f"[CAL] TOTAL : {len(all_matches)} matchs collectés toutes saisons.")
    return all_matches


__all__ = ["scrape_wonderligue_calendar", "LEAGUE_NAME"]
