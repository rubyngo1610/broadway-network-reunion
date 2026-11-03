"""Shared settings for the Broadway creative-team pipeline.

Edit CONTACT_EMAIL (or set the BROADWAY_CONTACT_EMAIL environment variable)
before running the full pipeline: Wikimedia asks every client to identify
itself with a way to reach the operator.
"""
import os
from pathlib import Path

# --- Identity ---------------------------------------------------------------
CONTACT_EMAIL = os.environ.get("BROADWAY_CONTACT_EMAIL", "hn2589@nyu.edu")
USER_AGENT = (
    f"NYU DS-GA 3001 Broadway project ({CONTACT_EMAIL or 'contact email not set'}) "
    "python-requests"
)

# --- Endpoints (the only two hosts this project talks to) -------------------
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"

# --- Politeness -------------------------------------------------------------
SLEEP_MEDIAWIKI = 1.0         # seconds between MediaWiki API requests
SLEEP_SPARQL = 2.0            # seconds between SPARQL requests
MAX_RETRIES = 6               # retries on 429 / 5xx / network errors
BACKOFF_BASE = 5.0            # seconds; doubles each retry
MAX_RETRY_AFTER = 600         # cap (seconds) on a server's Retry-After header
REQUEST_TIMEOUT = 120         # seconds (SPARQL hard limit is 60 s server-side)
MEDIAWIKI_BATCH = 50          # titles per MediaWiki request (API maximum)
SPARQL_BATCH = 200            # QIDs per VALUES block in SPARQL queries

# --- Category crawl ---------------------------------------------------------
ROOT_CATEGORY = "Category:Broadway musicals"
CATEGORY_MAX_DEPTH = 1         # depth-1 subcats are per-show categories (songs, films, ...); pages found there are flagged

# --- Core show set (used by the coverage audit; raw data is never dropped) --
CORE_MIN_YEAR = 1900           # shows with a year before this, or no year at all, are excluded

# --- Network and time windows (step 08; see "Prediction test" in Pipeline Findings) ---
NETWORK_ROLES = ["composer", "lyricist", "book_writer", "director", "choreographer"]
NETWORK_WINDOW_YEARS = 10      # W: training window [T - W, T)
NETWORK_HORIZON_YEARS = 10     # H: reunion window [T, T + H)
NETWORK_CUTOFFS = list(range(1925, 2011, 5))   # cutoff years T, fixed before looking at results
POSTHUMOUS_GRACE_YEARS = 1     # a credit is posthumous if the show opens more than this many years after death

# --- Reproducibility --------------------------------------------------------
RANDOM_SEED = 42
SPOTCHECK_N = 50

# --- Paths ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
# Data can live outside the project folder (recommended if the project sits in a
# synced folder such as Google Drive, where thousands of small cache files are slow).
DATA = Path(os.environ.get("BROADWAY_DATA_DIR", ROOT / "data")).expanduser().resolve()
DATA_RAW = DATA / "raw"
DATA_INTERIM = DATA / "interim"
DATA_PROCESSED = DATA / "processed"
OUTPUT_FIGURES = ROOT / "outputs" / "figures"
OUTPUT_TABLES = ROOT / "outputs" / "tables"

RAW_SPARQL = DATA_RAW / "sparql"
RAW_MEDIAWIKI = DATA_RAW / "mediawiki"
RAW_WIKITEXT = DATA_RAW / "wikitext"

for _p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, OUTPUT_FIGURES, OUTPUT_TABLES,
           RAW_SPARQL, RAW_MEDIAWIKI, RAW_WIKITEXT):
    _p.mkdir(parents=True, exist_ok=True)
