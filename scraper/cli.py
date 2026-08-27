"""Command line interface.

    python -m scraper.cli update                          # latest published
    python -m scraper.cli update --date 2026-08-24
    python -m scraper.cli backfill --from 2025-09-01 --to 2026-08-24
    python -m scraper.cli backfill --days 180             # relative window
    python -m scraper.cli reindex                         # rebuild all outputs
    python -m scraper.cli inspect --date 2026-08-24       # dump the raw grid
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time

from . import build_site, config, fetch, normalize, parse_pdf, parse_xls

log = logging.getLogger("coal")


def _parse_one(day: dt.date, *, quiet: bool = False) -> dict | None:
    stamp = day.strftime("%Y-%m-%d")
    try:
        path, kind = fetch.download(day)
    except fetch.ReportNotPublished:
        if not quiet:
            log.info("%s not published", stamp)
        return None

    parser = parse_xls if kind == "xls" else parse_pdf
    try:
        parsed = parser.parse(path, stamp)
    except Exception as exc:
        log.error("%s parse failed for %s: %s", kind, stamp, exc)
        if kind == "xls":
            try:
                pdf_path, pdf_kind = fetch.download(day, prefer="pdf")
                if pdf_kind != "pdf":
                    return None
                log.info("retrying %s via the PDF", stamp)
                parsed = parse_pdf.parse(pdf_path, stamp)
            except Exception as exc2:
                log.error("PDF fallback also failed for %s: %s", stamp, exc2)
                return None
        else:
            return None

    day_data = normalize.normalise_day(parsed)
    build_site.write_day(day_data)
    s = day_data["summary"]
    log.info("%s  %3d plants  %8.0f kt  %4.1f days cover  %2d critical",
             stamp, s["plants"], s["stock_total_kt"],
             s["cover_days_normative"] or 0, s["critical"])
    return day_data


def cmd_update(args) -> int:
    day = dt.date.fromisoformat(args.date) if args.date else fetch.latest_available()
    stamp = day.isoformat()
    if not args.force and (config.DAILY_DIR / f"{stamp}.json").exists():
        log.info("%s already saved; use --force to re-parse", stamp)
        build_site.rebuild_indexes([stamp])
        return 0
    if _parse_one(day) is None:
        return 1
    build_site.rebuild_indexes([stamp])
    return 0


def cmd_backfill(args) -> int:
    """Walk a date range, skipping days already saved or known unpublished.

    Safe to interrupt and re-run: progress is on disk, and dates CEA never
    published are recorded so later runs do not re-request them.
    """
    end = dt.date.fromisoformat(args.to) if args.to else dt.date.today()
    if args.since:
        start = dt.date.fromisoformat(args.since)
    else:
        start = end - dt.timedelta(days=args.days)
    if start > end:
        log.error("--from is after --to")
        return 2

    missing = set() if args.recheck else build_site.load_missing()
    added: list[str] = []
    skipped = failed = 0
    budget = args.limit or 10**6

    for day in fetch.date_range(start, end):
        stamp = day.isoformat()
        if (config.DAILY_DIR / f"{stamp}.json").exists() and not args.force:
            skipped += 1
            continue
        if stamp in missing:
            skipped += 1
            continue
        if len(added) + failed >= budget:
            log.info("hit --limit of %d requests; re-run to continue", budget)
            break

        if _parse_one(day, quiet=True):
            added.append(stamp)
        else:
            missing.add(stamp)
            failed += 1
        time.sleep(config.POLITE_DELAY_SEC)

        if args.checkpoint and len(added) and len(added) % args.checkpoint == 0:
            log.info("checkpoint at %d days", len(added))
            build_site.rebuild_indexes(added)

    log.info("backfill: %d added, %d skipped, %d unavailable",
             len(added), skipped, failed)
    build_site.save_missing(missing)
    build_site.rebuild_indexes(None if added else [])
    return 0


def cmd_reindex(args) -> int:
    """Rebuild every derived file from the daily snapshots already on disk."""
    build_site.rebuild_indexes(None)
    return 0


def cmd_inspect(args) -> int:
    day = dt.date.fromisoformat(args.date)
    path, kind = fetch.download(day)
    if kind != "xls":
        print(f"only a PDF is available for {day}")
        return 1
    grid = parse_xls.read_grid(path)
    hstart, hend = parse_xls.find_header_block(grid)
    cols, conf = parse_xls.resolve_columns(grid, hstart, hend)
    print(f"header rows {hstart}-{hend}, confidence {conf:.0%}")
    print("resolved columns:")
    for field, idx in sorted(cols.items(), key=lambda kv: kv[1]):
        print(f"  {idx:>3}  {field}")
    print("\nfirst 25 rows after the header:")
    for row in grid[hend:hend + 25]:
        print("  | ".join(c[:22] for c in row))
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="scraper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("update", help="fetch and parse one day")
    u.add_argument("--date", help="YYYY-MM-DD; defaults to latest published")
    u.add_argument("--force", action="store_true")
    u.set_defaults(fn=cmd_update)

    b = sub.add_parser("backfill", help="fetch a range of past reports")
    b.add_argument("--from", dest="since", help="YYYY-MM-DD")
    b.add_argument("--to", help="YYYY-MM-DD; defaults to today")
    b.add_argument("--days", type=int, default=90,
                   help="window length when --from is omitted")
    b.add_argument("--limit", type=int, default=0,
                   help="stop after this many download attempts")
    b.add_argument("--checkpoint", type=int, default=0,
                   help="rebuild indexes every N successful days")
    b.add_argument("--recheck", action="store_true",
                   help="retry dates previously recorded as unpublished")
    b.add_argument("--force", action="store_true")
    b.set_defaults(fn=cmd_backfill)

    r = sub.add_parser("reindex", help="rebuild derived files from local snapshots")
    r.set_defaults(fn=cmd_reindex)

    i = sub.add_parser("inspect", help="dump the raw grid for one day")
    i.add_argument("--date", required=True)
    i.set_defaults(fn=cmd_inspect)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
