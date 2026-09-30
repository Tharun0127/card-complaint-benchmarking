"""Project configuration: paths, data sources, issuers, event dates."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REFERENCE_DIR = ROOT / "data" / "reference"
LLM_CACHE_DIR = ROOT / "data" / "llm_cache"
OUTPUT_DIR = ROOT / "outputs"
SQL_DIR = ROOT / "sql"
DOCS_DIR = ROOT / "docs"
VALIDATION_DIR = ROOT / "validation"

COMPLAINTS_PARQUET = PROCESSED_DIR / "complaints.parquet"
CARDS_ALL_PARQUET = PROCESSED_DIR / "cards_all.parquet"
SAMPLE_PARQUET = PROCESSED_DIR / "sample.parquet"
SAMPLE_IDS_CSV = OUTPUT_DIR / "sample_ids.csv"
MODEL_LABELS_PARQUET = PROCESSED_DIR / "model_labels.parquet"
# LLM results cache. Committed to git (labels and token usage only, no narrative text)
# so that a fresh clone can rebuild every output without calling the API.
LABELS_JSONL = OUTPUT_DIR / "llm_labels.jsonl"

# --- CFPB sources -----------------------------------------------------------------------
ARCHIVE_PAGE = (
    "https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/"
    "cfpb-consumer-complaint-database-narratives-archive/"
)
ARCHIVE_BASE_URL = "https://files.consumerfinance.gov/f/documents"
LIVE_API_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"

# Archive exports that contain complaints received in 2023 or later. File 4 starts in
# Nov 2022 and is trimmed to 2023-01-01 at ingest.
ARCHIVE_FILES = [
    "CCDB_Export_4_November_2022_through_August_2023.zip",
    "CCDB_Export_5_September_2023_through_March_2024.zip",
    "CCDB_Export_6_April_2024_through_July_2024.zip",
    "CCDB_Export_7_August_2024_through_October_2024.zip",
    "CCDB_Export_8_November_2024_through_December_2024.zip",
    "CCDB_Export_9_January_2025_through_February_2025.zip",
    "CCDB_Export_10_March_2025_through_April_2025.zip",
    "CCDB_Export_11_May_2025_through_June_2025.zip",
    "CCDB_Export_12_July_2025_through_August_2025.zip",
    "CCDB_Export_13_September_2025_through_October_2025.zip",
    "CCDB_Export_14_November_2025_through_December_2025.zip",
    "CCDB_Export_15_January_2026_through_February_2026.zip",
    "CCDB_Export_16_March_2026.zip",
    "CCDB_Export_17_April_2026.zip",
    "CCDB_Export_18_May_2026.zip",
    "CCDB_Export_19_June_2026.zip",
    "CCDB_Export_20_July_2026.zip",
    "CCDB_Export_21_August_2026.zip",
]

START_DATE = "2023-01-01"

# --- Event study ------------------------------------------------------------------------
# Dates are from the issuers' press releases (see data/reference/denominator_research.md).
# Both refreshes raised the annual fee for new applicants at launch and for existing
# cardholders later, at each account's renewal, so the effect is expected to be gradual.
EVENTS = [
    {
        "key": "chase_sapphire_reserve",
        "label": "Chase Sapphire Reserve refresh",
        "issuer": "Chase",
        "event_date": "2025-06-23",
        "event_month": "2025-06-01",
        "product_mention_col": "mentions_sapphire_reserve",
        "product_name": "Sapphire Reserve",
        "detail": "Annual fee USD 550 to USD 795. New applicants from 23 Jun 2025, existing "
                  "cardholders at renewal on or after 26 Oct 2025.",
    },
    {
        "key": "amex_platinum",
        "label": "Amex Platinum refresh",
        "issuer": "American Express",
        "event_date": "2025-09-18",
        "event_month": "2025-09-01",
        "product_mention_col": "mentions_platinum",
        "product_name": "Platinum",
        "detail": "Annual fee USD 695 to USD 895. New applicants from 18 Sep 2025, existing "
                  "consumer members at renewal on or after 2 Jan 2026.",
    },
]
# Issuers with no premium card refresh in the window. Chase and Amex are left out of the
# comparison group for both events because each is treated in one of them.
CONTROL_ISSUERS = ["Capital One", "Citi", "Bank of America", "Discover", "Synchrony"]
EVENT_WINDOWS_MONTHS = [6, 12]
