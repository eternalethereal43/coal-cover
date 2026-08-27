"""Parse the CEA Daily Coal Stock Report XLS into flat plant records.

The sheet is a JasperReports export: merged multi-row headers, section banner
rows ("A. PLANT HAVING COAL LINKAGES..."), group label rows (a state name or a
utility code on its own), plant rows, and "<GROUP>-Total" subtotal rows.

Column positions are resolved by matching header text rather than hard-coded
indices, so a reordered export still parses. If matching fails the parser falls
back to config.POSITIONAL_FALLBACK and flags low confidence.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import xlrd

from . import config

log = logging.getLogger(__name__)

NUM_RE = re.compile(r"^-?[\d,]*\.?\d+$")
SECTION_RE = re.compile(r"^([A-D])\.\s*(.+)", re.I)
TOTAL_RE = re.compile(r"(-total|^total\b|grand total|sub-?total)", re.I)

INDIAN_STATES = {
    "andhra pradesh", "assam", "bihar", "chhatisgarh", "chhattisgarh", "delhi",
    "gujarat", "haryana", "himachal pradesh", "jammu & kashmir", "jharkhand",
    "karnataka", "kerala", "madhya pradesh", "maharashtra", "odisha", "orissa",
    "punjab", "rajasthan", "tamil nadu", "telangana", "uttar pradesh",
    "uttarakhand", "west bengal", "goa", "puducherry",
}


class ParseError(Exception):
    pass


# --- low level -------------------------------------------------------------

def read_grid(path: Path) -> list[list[str]]:
    """Return the first sheet as a rectangular grid of trimmed strings."""
    book = xlrd.open_workbook(str(path), formatting_info=False)
    sheet = book.sheet_by_index(0)
    grid: list[list[str]] = []
    for r in range(sheet.nrows):
        row = []
        for c in range(sheet.ncols):
            cell = sheet.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_NUMBER:
                val = cell.value
                row.append(str(int(val)) if float(val).is_integer() else str(val))
            else:
                row.append(str(cell.value).strip())
        grid.append(row)
    return grid


def to_num(text: str) -> float | None:
    if text is None:
        return None
    t = str(text).strip().replace(",", "").replace("%", "").replace("\u2013", "-")
    if t in ("", "-", "null", "NA", "N/A", "nan"):
        return None
    if not NUM_RE.match(t):
        return None
    try:
        return float(t)
    except ValueError:
        return None


# --- header resolution -----------------------------------------------------

def find_header_block(grid: list[list[str]]) -> tuple[int, int]:
    """Locate the rows spanned by the column header. Returns (start, end_excl)."""
    for i, row in enumerate(grid):
        joined = " ".join(row).lower()
        if "thermal power station" in joined:
            start = max(0, i - 3)
            # Header block ends at the first row that looks like data or a
            # section banner.
            for j in range(i, min(i + 6, len(grid))):
                joined_j = " ".join(grid[j]).lower()
                if SECTION_RE.match(grid[j][0].strip() if grid[j] else ""):
                    return start, j
                if "consumption" in joined_j or "receipt" in joined_j:
                    continue
            return start, i + 3
    raise ParseError("could not find the column header row in the sheet")


def resolve_columns(grid: list[list[str]], hstart: int, hend: int) -> tuple[dict, float]:
    """Map field name -> column index. Returns (mapping, confidence 0-1)."""
    ncols = max(len(r) for r in grid[hstart:hend]) if hend > hstart else 0
    stacks = []
    for c in range(ncols):
        parts = [grid[r][c] for r in range(hstart, hend) if c < len(grid[r])]
        stacks.append(" ".join(p for p in parts if p).lower())

    mapping: dict[str, int] = {}
    used: set[int] = set()
    # Longest, most specific hints first so "total" doesn't steal a column from
    # "normative stock reqd.(in '000 tonnes)".
    ordered = sorted(
        config.HEADER_HINTS.items(),
        key=lambda kv: -max(len(h) for h in kv[1]),
    )
    for field, hints in ordered:
        for c, stack in enumerate(stacks):
            if c in used or not stack:
                continue
            if any(h in stack for h in hints):
                mapping[field] = c
                used.add(c)
                break

    confidence = len(mapping) / len(config.FIELDS)
    if confidence < 0.6:
        log.warning(
            "header matching resolved only %d/%d columns; falling back to "
            "positional mapping. Run `python -m scraper.cli inspect <date>` to "
            "dump the grid and correct config.POSITIONAL_FALLBACK.",
            len(mapping), len(config.FIELDS),
        )
        return dict(config.POSITIONAL_FALLBACK), confidence
    # Fill any gaps positionally without clobbering resolved columns.
    for field, idx in config.POSITIONAL_FALLBACK.items():
        mapping.setdefault(field, idx)
    return mapping, confidence


# --- row classification ----------------------------------------------------

def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def classify(row: list[str], cols: dict) -> str:
    cells = [c.strip() for c in row]
    nonempty = [c for c in cells if c]
    if not nonempty:
        return "blank"
    first = nonempty[0]
    if SECTION_RE.match(first) and len(first) < 90:
        return "section"
    joined = " ".join(nonempty)
    if TOTAL_RE.search(joined):
        return "total"
    sl = to_num(_cell(cells, cols.get("sl_no")))
    plant = _cell(cells, cols.get("plant"))
    if sl is not None and plant:
        return "plant"
    # A lone text cell is a group label: a state name, or a utility code such
    # as NTPC / IPP / DVC.
    if len(nonempty) == 1 and len(first) < 60 and not to_num(first):
        return "group"
    return "other"


def _group_kind(label: str) -> str:
    return "state" if label.strip().lower() in INDIAN_STATES else "utility"


# --- main ------------------------------------------------------------------

def parse(path: Path, report_date: str) -> dict:
    grid = read_grid(path)
    hstart, hend = find_header_block(grid)
    cols, confidence = resolve_columns(grid, hstart, hend)
    log.info("column mapping confidence %.0f%%", confidence * 100)

    records: list[dict] = []
    totals: list[dict] = []
    section_code, section_name = "A", config.SECTIONS["A"]
    state = ""
    utility = ""

    for row in grid[hend:]:
        kind = classify(row, cols)
        if kind in ("blank", "other"):
            continue
        cells = [c.strip() for c in row]

        if kind == "section":
            first = next(c for c in cells if c)
            m = SECTION_RE.match(first)
            code = m.group(1).upper()
            section_code = code
            section_name = config.SECTIONS.get(code, m.group(2).title())
            state, utility = "", ""
            continue

        if kind == "group":
            label = next(c for c in cells if c)
            if _group_kind(label) == "state":
                state, utility = label, ""
            else:
                utility = label
            continue

        if kind == "total":
            label = " ".join(c for c in cells if c)[:60]
            totals.append({
                "label": label,
                "section": section_code,
                "capacity_mw": to_num(_cell(cells, cols.get("capacity_mw"))),
                "stock_total_kt": to_num(_cell(cells, cols.get("stock_total_kt"))),
                "daily_req_kt": to_num(_cell(cells, cols.get("daily_req_kt"))),
            })
            continue

        # kind == "plant"
        rec = {"date": report_date, "section": section_code,
               "section_name": section_name}
        for field in config.FIELDS:
            raw = _cell(cells, cols.get(field))
            if field in ("plant", "mode_of_transport", "remarks"):
                rec[field] = raw
            elif field == "critical_flag":
                rec[field] = "*" in raw
            else:
                rec[field] = to_num(raw)

        # Some exports glue "<state><sl_no>" into the first cell of the first
        # plant row of each state block (a PDF/XLS layout artefact).
        sl_cell = _cell(cells, cols.get("sl_no"))
        m = re.match(r"^([A-Za-z .&]+?)(\d+)$", sl_cell)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() in INDIAN_STATES:
                state = candidate
                rec["sl_no"] = float(m.group(2))

        if not rec.get("plant"):
            continue
        rec["state"] = state
        rec["utility"] = utility or state
        # The report's asterisk sometimes lands in the remarks cell instead of
        # its own column.
        if rec.get("remarks", "").lstrip().startswith("*"):
            rec["critical_flag"] = True
            rec["remarks"] = rec["remarks"].lstrip("* ").strip()
        records.append(rec)

    if not records:
        raise ParseError("parsed zero plant rows; the sheet layout has changed")

    validate(records)
    return {
        "date": report_date,
        "source": path.name,
        "column_confidence": round(confidence, 3),
        "plants": records,
        "reported_totals": totals,
    }


def validate(records: list[dict]) -> None:
    """Sanity-check the parse using arithmetic the report must satisfy.

    normative stock ('000 t) == daily requirement ('000 t) x normative days.
    If most rows fail this, the columns are misaligned and the run should stop
    rather than publish wrong numbers.
    """
    checked = ok = 0
    for r in records:
        req, days, norm = r.get("daily_req_kt"), r.get("norm_days"), r.get("norm_stock_kt")
        if not req or not days or not norm:
            continue
        checked += 1
        if abs(req * days - norm) <= max(1.0, 0.05 * norm):
            ok += 1
    if checked >= 20 and ok / checked < 0.8:
        raise ParseError(
            f"column alignment check failed: only {ok}/{checked} rows satisfy "
            "normative_stock = daily_requirement x normative_days"
        )
    log.info("validation: %d/%d rows consistent", ok, checked)
