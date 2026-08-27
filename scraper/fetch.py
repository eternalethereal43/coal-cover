"""Download daily coal reports from NPP and cache them locally."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import requests

from . import config

log = logging.getLogger(__name__)


class ReportNotPublished(Exception):
    """The report for this date is not on the portal."""


def _urls(day: dt.date) -> tuple[str, str]:
    dmy = day.strftime("%d-%m-%Y")
    ymd = day.strftime("%Y-%m-%d")
    return (
        config.XLS_URL.format(dmy=dmy, ymd=ymd),
        config.PDF_URL.format(dmy=dmy, ymd=ymd),
    )


def _get(url: str) -> bytes | None:
    headers = {"User-Agent": config.USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        log.warning("request failed for %s: %s", url, exc)
        return None
    if r.status_code == 404:
        return None
    r.raise_for_status()
    # The portal returns a courtesy HTML page instead of a 404 in some cases.
    if r.content[:15].lstrip().lower().startswith(b"<!doctype html"):
        return None
    if len(r.content) < 1024:
        return None
    return r.content


def download(day: dt.date, *, cache_dir: Path | None = None,
             prefer: str | None = None) -> tuple[Path, str]:
    """Fetch one day's report.

    Returns (path, kind) where kind is "xls" or "pdf". Pass prefer="pdf" to
    skip the XLS, which the CLI uses when an XLS parse has already failed.
    Raises ReportNotPublished if neither format is available.
    """
    cache_dir = cache_dir or config.RAW_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = day.strftime("%Y-%m-%d")

    order = list(zip(("xls", "pdf"), _urls(day)))
    if prefer:
        order = [t for t in order if t[0] == prefer] + [t for t in order if t[0] != prefer]

    for kind, url in order:
        cached = cache_dir / f"dailyCoal1-{stamp}.{kind}"
        if cached.exists() and cached.stat().st_size > 1024:
            log.debug("using cached %s", cached.name)
            return cached, kind
        log.debug("GET %s", url)
        blob = _get(url)
        if blob:
            cached.write_bytes(blob)
            return cached, kind

    raise ReportNotPublished(f"no report published for {stamp}")


def latest_available(today: dt.date | None = None) -> dt.date:
    """Walk back from today to the most recent published report date."""
    today = today or dt.date.today()
    for back in range(config.MAX_LAG_DAYS + 1):
        day = today - dt.timedelta(days=back)
        xls_url, pdf_url = _urls(day)
        for url in (xls_url, pdf_url):
            if _get(url):
                return day
    raise ReportNotPublished(
        f"nothing published in the last {config.MAX_LAG_DAYS} days"
    )


def date_range(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)
