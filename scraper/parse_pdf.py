"""Fallback parser for days where only the PDF is published.

Plain text extraction scrambles this report: for plants flagged critical, the
remarks column is typeset between the numeric columns, so reading order does
not match column order. This parser instead bands words by their x coordinate,
which reflects the printed column regardless of reading order.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

from . import config
from .parse_xls import (
    INDIAN_STATES, ParseError, SECTION_RE, TOTAL_RE, classify, to_num, validate,
)

log = logging.getLogger(__name__)

# Column bands are anchored on header text found on page 1. Each entry is
# (field, header substring to locate).
ANCHORS = [
    ("sl_no", "Sl. No"),
    ("mode_of_transport", "Mode of"),
    ("plant", "Name of Thermal"),
    ("plf_pct", "Current"),
    ("capacity_mw", "Capacity"),
    ("norm_days", "Reqd.(Days)"),
    ("daily_req_kt", "Daily"),
    ("norm_stock_kt", "Normative"),
    ("stock_indigenous_kt", "Indigenous"),
    ("stock_import_kt", "Import"),
    ("stock_total_kt", "Total"),
    ("pct_of_norm", "% of Actual"),
    ("critical_flag", "Critical"),
    ("receipt_kt", "Receipt"),
    ("consumption_kt", "Consumption"),
    ("remarks", "Reasons for"),
]


def _column_bounds(page) -> list[tuple[str, float, float]]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    text = " ".join(w["text"] for w in words)
    if "Thermal" not in text:
        return []
    starts: list[tuple[str, float]] = []
    for field, needle in ANCHORS:
        head = needle.split()[0]
        hit = next((w for w in words if w["text"].startswith(head)), None)
        if hit:
            starts.append((field, hit["x0"]))
    if len(starts) < 8:
        return []
    starts.sort(key=lambda t: t[1])
    bounds = []
    for i, (field, x0) in enumerate(starts):
        x1 = starts[i + 1][1] if i + 1 < len(starts) else page.width
        bounds.append((field, x0 - 2, x1 - 2))
    return bounds


def _rows_from_page(page, bounds) -> list[dict]:
    words = page.extract_words(use_text_flow=False)
    lines: dict[int, list] = {}
    for w in words:
        key = round(w["top"] / 3.0)
        lines.setdefault(key, []).append(w)

    rows = []
    for key in sorted(lines):
        cells = {field: [] for field, _, _ in bounds}
        for w in sorted(lines[key], key=lambda w: w["x0"]):
            centre = (w["x0"] + w["x1"]) / 2
            for field, lo, hi in bounds:
                if lo <= centre < hi:
                    cells[field].append(w["text"])
                    break
        rows.append({f: " ".join(v).strip() for f, v in cells.items()})
    return rows


def parse(path: Path, report_date: str) -> dict:
    records: list[dict] = []
    section_code, section_name = "A", config.SECTIONS["A"]
    state = utility = ""
    bounds: list = []

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_bounds = _column_bounds(page)
            if page_bounds:
                bounds = page_bounds
            if not bounds:
                continue
            for row in _rows_from_page(page, bounds):
                joined = " ".join(v for v in row.values() if v).strip()
                if not joined or "Sl. No" in joined or "https://npp.gov.in" in joined:
                    continue

                m = SECTION_RE.match(joined)
                if m and len(joined) < 90:
                    section_code = m.group(1).upper()
                    section_name = config.SECTIONS.get(section_code, m.group(2).title())
                    state = utility = ""
                    continue
                if TOTAL_RE.search(joined):
                    continue

                sl_raw = row.get("sl_no", "")
                name = row.get("plant", "").strip()
                sm = re.match(r"^([A-Za-z .&]+?)\s*(\d+)$", sl_raw)
                if sm and sm.group(1).strip().lower() in INDIAN_STATES:
                    state = sm.group(1).strip()
                    sl_raw = sm.group(2)
                if to_num(sl_raw) is None or not name:
                    if len(joined) < 60 and not any(ch.isdigit() for ch in joined):
                        if joined.lower() in INDIAN_STATES:
                            state, utility = joined, ""
                        else:
                            utility = joined
                    continue

                rec = {"date": report_date, "section": section_code,
                       "section_name": section_name, "state": state,
                       "utility": utility or state}
                for field in config.FIELDS:
                    raw = row.get(field, "")
                    if field in ("plant", "mode_of_transport", "remarks"):
                        rec[field] = raw
                    elif field == "critical_flag":
                        rec[field] = "*" in raw
                    elif field == "sl_no":
                        rec[field] = to_num(sl_raw)
                    else:
                        rec[field] = to_num(raw)
                if rec["remarks"].lstrip().startswith("*"):
                    rec["critical_flag"] = True
                    rec["remarks"] = rec["remarks"].lstrip("* ").strip()
                records.append(rec)

    if not records:
        raise ParseError("PDF fallback extracted zero plant rows")
    validate(records)
    return {
        "date": report_date,
        "source": path.name,
        "column_confidence": 0.7,
        "plants": records,
        "reported_totals": [],
    }
