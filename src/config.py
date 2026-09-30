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
ARCHIVE_END_DATE = "2026-08-14"
