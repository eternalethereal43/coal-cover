"""Central configuration for the CEA daily coal stock pipeline."""
from __future__ import annotations

import os
from pathlib import Path

# --- Source ----------------------------------------------------------------
# The NPP "Daily Fuel Report" page (https://npp.gov.in/dailyCoalReports) is a
# date picker that resolves to a static file under /public-reports/. Both a PDF
# and an XLS are published for every date. We prefer the XLS: the PDF puts the
# remarks column mid-row for critical plants, which scrambles cell order.
BASE = "https://npp.gov.in/public-reports/cea/daily/fuel"
XLS_URL = BASE + "/{dmy}/dailyCoal1-{ymd}.xls"
PDF_URL = BASE + "/{dmy}/dailyCoal1-{ymd}.pdf"

PUBLISHED_REPORTS = "https://npp.gov.in/publishedReports"

# CEA normally publishes with a 1-3 day lag. When asked for "latest", walk back
# from today until a file exists.
MAX_LAG_DAYS = int(os.getenv("COAL_MAX_LAG_DAYS", "10"))
REQUEST_TIMEOUT = 60
USER_AGENT = (
    "coal-stock-dashboard/1.0 (+https://github.com/) "
    "python-requests; public CEA data mirror"
)

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"                 # cached source files, git-ignored
SITE_DIR = ROOT / "docs"               # GitHub Pages root
DATA_DIR = SITE_DIR / "data"
DAILY_DIR = DATA_DIR / "daily"
HISTORY_DIR = DATA_DIR / "history"     # one CSV per calendar month
MISSING_FILE = DATA_DIR / "missing.json"

# Recent window kept in a single file for the station drill-down chart. Full
# history lives in the monthly CSVs; keeping the chart file bounded is what
# stops a daily commit from rewriting megabytes.
SERIES_WINDOW_DAYS = int(os.getenv("COAL_SERIES_WINDOW", "180"))

# Courtesy pause between requests when backfilling months of reports.
POLITE_DELAY_SEC = float(os.getenv("COAL_POLITE_DELAY", "1.5"))

# --- Report structure ------------------------------------------------------
# Section headings that appear as full-width rows in the report.
SECTIONS = {
    "A": "Domestic coal (linkage, no linkage, coal block)",
    "B": "Designed on imported coal",
    "C": "Not in operation",
    "D": "Based on washery rejects",
}

# Canonical field order. The XLS parser resolves these by matching header text;
# POSITIONAL_FALLBACK is used only when header matching fails. If CEA reorders
# the sheet, this list is the single place to fix it.
FIELDS = [
    "sl_no",
    "mode_of_transport",
    "plant",
    "plf_pct",
    "capacity_mw",
    "norm_days",
    "daily_req_kt",
    "norm_stock_kt",
    "stock_indigenous_kt",
    "stock_import_kt",
    "stock_total_kt",
    "pct_of_norm",
    "critical_flag",
    "receipt_kt",
    "consumption_kt",
    "remarks",
]

POSITIONAL_FALLBACK = {name: i for i, name in enumerate(FIELDS)}

# Substrings used to locate each column in the sheet header block. Matching is
# case-insensitive on the concatenation of all header rows for that column.
HEADER_HINTS = {
    "sl_no": ["sl. no", "sl no", "sl.no"],
    "mode_of_transport": ["mode of transport"],
    "plant": ["name of thermal power station", "thermal power station"],
    "plf_pct": ["current month plf", "plf (tentative)"],
    "capacity_mw": ["capacity (mw)", "capacity(mw)"],
    "norm_days": ["normative stock reqd.(days)", "stock reqd.(days)", "reqd.(days)"],
    "daily_req_kt": ["daily requirement"],
    "norm_stock_kt": ["normative stock reqd.(in", "normative stock reqd.(in '000"],
    "stock_indigenous_kt": ["indigenous"],
    "stock_import_kt": ["import"],
    "stock_total_kt": ["total"],
    "pct_of_norm": ["% of actual stock"],
    "critical_flag": ["critical"],
    "receipt_kt": ["receipt of the day", "receipt"],
    "consumption_kt": ["consumption of the day", "consumption"],
    "remarks": ["reasons for critical", "remarks"],
}

# --- Thresholds ------------------------------------------------------------
# CEA flags a plant critical when actual stock falls below 25% of normative
# stock, and supercritical below 10%. The report's own asterisk is carried
# through as `critical_flag`; these bands are computed independently so the
# dashboard can band plants even on days the asterisk is missing.
CRITICAL_PCT = 25.0
SUPERCRITICAL_PCT = 10.0

# Days-of-cover bands used by the dashboard colour ramp.
COVER_BANDS = [
    ("supercritical", 0, 3),
    ("critical", 3, 7),
    ("low", 7, 12),
    ("adequate", 12, 20),
    ("comfortable", 20, 10_000),
]

# Utility groups that are central-sector, for ownership roll-ups.
CENTRAL_UTILITIES = {
    "NTPC", "NTPC JV", "DVC", "NTPL", "NUPPL", "THDC", "SJVNL", "NLC",
}
