"""Write the static data files the dashboard and downstream tools read.

Layout is chosen so that a daily run touches a handful of files rather than
rewriting a year of history:

    data/index.json            available dates, build stamp, manifest pointer
    data/latest.json           copy of the most recent day
    data/daily/YYYY-MM-DD.json one file per report, written once
    data/trend.json            one summary row per day
    data/plants-recent.json    rolling window of per-station series, for charts
    data/history/YYYY-MM.csv   monthly partitions, the full record
    data/manifest.json         partition list, for Power BI / Excel / pandas
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
from collections import defaultdict
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

HISTORY_COLUMNS = [
    "date", "id", "plant", "state", "utility", "ownership", "section",
    "mode_of_transport", "capacity_mw", "plf_pct", "norm_days", "daily_req_kt",
    "norm_stock_kt", "stock_indigenous_kt", "stock_import_kt",
    "stock_total_kt", "pct_of_norm", "receipt_kt", "consumption_kt",
    "net_change_kt", "cover_days_normative", "cover_days_actual",
    "days_to_empty", "is_critical", "is_supercritical", "cover_band",
    "import_share_pct", "remarks",
]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%.0f KB)", path.relative_to(config.ROOT),
             path.stat().st_size / 1024)


# Fields the dashboard recomputes or does not read; dropping them keeps a
# year of daily snapshots to a size git is comfortable with.
_DROP_FROM_DAILY = ("section_name", "sl_no", "norm_days")


def _compact(rec: dict) -> dict:
    """Strip nulls, empty strings and redundant fields from a plant record."""
    out = {}
    for k, v in rec.items():
        if k in _DROP_FROM_DAILY or v is None or v == "" or v is False:
            continue
        out[k] = round(v, 2) if isinstance(v, float) else v
    return out


def write_day(day: dict) -> Path:
    path = config.DAILY_DIR / f"{day['date']}.json"
    slim = dict(day)
    slim["plants"] = [_compact(p) for p in day["plants"]]
    _write_json(path, slim)
    return path


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


# --- monthly CSV partitions ------------------------------------------------

def _months_touched(dates: list[str]) -> set[str]:
    return {d[:7] for d in dates}


def write_history(changed_dates: list[str] | None = None) -> list[str]:
    """Rewrite only the monthly partitions that changed.

    Pass None to rebuild every month (used after a large backfill).
    """
    config.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(config.DAILY_DIR.glob("*.json")):
        by_month[p.stem[:7]].append(p)

    targets = set(by_month) if changed_dates is None else _months_touched(changed_dates)
    written = []
    for month in sorted(targets):
        if month not in by_month:
            continue
        out = config.HISTORY_DIR / f"{month}.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=HISTORY_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for p in by_month[month]:
                for rec in _load(p)["plants"]:
                    w.writerow(rec)
        written.append(month)
        log.info("wrote history/%s.csv (%.0f KB)", month, out.stat().st_size / 1024)
    return written


# --- indexes ---------------------------------------------------------------

def rebuild_indexes(changed_dates: list[str] | None = None) -> None:
    days = sorted(config.DAILY_DIR.glob("*.json"))
    if not days:
        log.warning("no daily files to index")
        return

    dates = [p.stem for p in days]
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    write_history(changed_dates)

    partitions = sorted(p.name for p in config.HISTORY_DIR.glob("*.csv"))
    _write_json(config.DATA_DIR / "manifest.json", {
        "generated": generated,
        "columns": HISTORY_COLUMNS,
        "units": {"*_kt": "thousand tonnes", "capacity_mw": "MW",
                  "*_pct": "percent", "cover_days_*": "days"},
        "partitions": [f"history/{n}" for n in partitions],
        "first_date": dates[0],
        "last_date": dates[-1],
        "rows_per_day_approx": len(_load(days[-1])["plants"]),
    })

    _write_json(config.DATA_DIR / "index.json", {
        "dates": dates,
        "latest": dates[-1],
        "generated": generated,
        "partitions": len(partitions),
    })

    _write_json(config.DATA_DIR / "latest.json", _load(days[-1]))

    trend = []
    for p in days:
        d = _load(p)
        trend.append({"date": d["date"], **d["summary"]})
    _write_json(config.DATA_DIR / "trend.json", trend)

    # Rolling window only. The full per-station record is in the CSVs; keeping
    # this file bounded is what keeps the daily commit small.
    window = days[-config.SERIES_WINDOW_DAYS:]
    series: dict[str, dict] = {}
    for p in window:
        d = _load(p)
        for rec in d["plants"]:
            s = series.setdefault(rec["id"], {
                "plant": rec["plant"], "state": rec.get("state"),
                "utility": rec.get("utility"), "points": [],
            })
            s["points"].append([
                d["date"], rec.get("stock_total_kt"),
                rec.get("cover_days_normative"), rec.get("receipt_kt"),
                rec.get("consumption_kt"),
            ])
    _write_json(config.DATA_DIR / "plants-recent.json", {
        "fields": ["date", "stock_total_kt", "cover_days_normative",
                   "receipt_kt", "consumption_kt"],
        "window_days": len(window),
        "series": series,
    })

    # Retired in favour of monthly partitions; remove so nobody reads a stale copy.
    for stale in ("history.csv", "plants.json"):
        old = config.DATA_DIR / stale
        if old.exists():
            old.unlink()
            log.info("removed superseded data/%s", stale)


# --- known-missing bookkeeping --------------------------------------------

def load_missing() -> set[str]:
    if config.MISSING_FILE.exists():
        try:
            return set(json.loads(config.MISSING_FILE.read_text()).get("dates", []))
        except json.JSONDecodeError:
            return set()
    return set()


def save_missing(dates: set[str]) -> None:
    _write_json(config.MISSING_FILE, {
        "note": "Dates CEA has not published. Skipped on later backfills; "
                "delete this file to force a re-check.",
        "dates": sorted(dates),
    })
