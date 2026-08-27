"""Turn parsed rows into the analytic record the dashboard consumes."""
from __future__ import annotations

import re

from . import config


def _band(days: float | None) -> str:
    if days is None:
        return "unknown"
    for name, lo, hi in config.COVER_BANDS:
        if lo <= days < hi:
            return name
    return "comfortable"


def _ownership(utility: str, section: str, state: str) -> str:
    u = (utility or "").upper().strip()
    if u in {x.upper() for x in config.CENTRAL_UTILITIES}:
        return "Central"
    if u in ("IPP", "PRIVATE"):
        return "Private / IPP"
    if state and utility == state:
        return "State"
    if re.search(r"(GENCO|GCL|SEB|PDC|VNL|PCL|POWER CORP)", u):
        return "State"
    return "State" if state else "Other"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def enrich(rec: dict) -> dict:
    """Add derived measures to one plant record."""
    out = dict(rec)
    stock = rec.get("stock_total_kt")
    req = rec.get("daily_req_kt")
    burn = rec.get("consumption_kt")
    recv = rec.get("receipt_kt")
    norm = rec.get("norm_stock_kt")

    # Days of cover at the normative 85% PLF burn — the report's own yardstick.
    out["cover_days_normative"] = round(stock / req, 2) if stock is not None and req else None
    # Days of cover at yesterday's actual burn — closer to operational reality.
    out["cover_days_actual"] = round(stock / burn, 2) if stock is not None and burn else None

    # Net stock movement and, when drawing down, days until empty at that rate.
    if recv is not None and burn is not None:
        net = round(recv - burn, 2)
        out["net_change_kt"] = net
        out["days_to_empty"] = (
            round(stock / abs(net), 1) if net < 0 and stock is not None else None
        )
    else:
        out["net_change_kt"] = None
        out["days_to_empty"] = None

    pct = rec.get("pct_of_norm")
    if pct is None and stock is not None and norm:
        pct = round(100 * stock / norm, 1)
    out["pct_of_norm"] = pct

    out["is_critical"] = bool(rec.get("critical_flag")) or (
        pct is not None and pct < config.CRITICAL_PCT
    )
    out["is_supercritical"] = pct is not None and pct < config.SUPERCRITICAL_PCT
    out["cover_band"] = _band(out["cover_days_normative"])

    out["import_share_pct"] = (
        round(100 * (rec.get("stock_import_kt") or 0) / stock, 1)
        if stock else None
    )
    out["no_receipt"] = recv is not None and recv == 0
    out["pithead"] = (rec.get("mode_of_transport") or "").upper() == "PITHEAD"
    out["ownership"] = _ownership(rec.get("utility", ""), rec.get("section", ""),
                                  rec.get("state", ""))
    out["id"] = _slug(rec.get("plant", ""))
    return out


def summarise(plants: list[dict]) -> dict:
    """All-India roll-up for the KPI header."""
    live = [p for p in plants if (p.get("capacity_mw") or 0) > 0
            and p.get("section") != "C"]

    def total(key):
        return round(sum(p.get(key) or 0 for p in live), 1)

    stock = total("stock_total_kt")
    req = total("daily_req_kt")
    burn = total("consumption_kt")
    recv = total("receipt_kt")
    norm = total("norm_stock_kt")

    return {
        "plants": len(live),
        "capacity_mw": total("capacity_mw"),
        "stock_total_kt": stock,
        "stock_indigenous_kt": total("stock_indigenous_kt"),
        "stock_import_kt": total("stock_import_kt"),
        "norm_stock_kt": norm,
        "daily_req_kt": req,
        "receipt_kt": recv,
        "consumption_kt": burn,
        "net_change_kt": round(recv - burn, 1),
        "cover_days_normative": round(stock / req, 2) if req else None,
        "cover_days_actual": round(stock / burn, 2) if burn else None,
        "pct_of_norm": round(100 * stock / norm, 1) if norm else None,
        "critical": sum(1 for p in live if p["is_critical"]),
        "supercritical": sum(1 for p in live if p["is_supercritical"]),
        "under_7_days": sum(1 for p in live
                            if (p.get("cover_days_normative") or 999) < 7),
        "no_receipt": sum(1 for p in live if p["no_receipt"]),
        "capacity_at_risk_mw": round(sum(
            p.get("capacity_mw") or 0 for p in live
            if (p.get("cover_days_normative") or 999) < 7), 1),
    }


def normalise_day(parsed: dict) -> dict:
    plants = [enrich(p) for p in parsed["plants"]]
    return {
        "date": parsed["date"],
        "source": parsed.get("source"),
        "column_confidence": parsed.get("column_confidence"),
        "summary": summarise(plants),
        "plants": plants,
    }
