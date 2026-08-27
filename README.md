# Coal Cover

A dashboard over the Central Electricity Authority's **Daily Coal Stock Report**, the
one published at [npp.gov.in/dailyCoalReports](https://npp.gov.in/dailyCoalReports).
A scheduled job pulls each day's report, parses it, and commits the result as JSON.
GitHub Pages serves a static dashboard on top of that data — no server, no database,
nothing to pay for.

Filter by station, state, utility, sector, transport mode, and above all by **days of
coal cover remaining**.

---

## How it works

```
  npp.gov.in  ──►  scraper/fetch.py      download .xls (or .pdf)
                   scraper/parse_xls.py  header-matched column extraction
                   scraper/normalize.py  derived KPIs
                   scraper/build_site.py daily JSON + monthly CSV partitions
                          │
                          ▼
   GitHub Actions commits docs/data  ──►  GitHub Pages serves docs/
                                              index.html + app.js (vanilla JS + Chart.js)
```

The browser never talks to npp.gov.in. That is deliberate: the portal sends no CORS
headers, so a client-side fetch would be blocked. Running the download in Actions also
means the data is versioned — every commit is a dated snapshot, and history builds up
even though CEA only publishes today's file.

### Why the XLS and not the PDF

Both formats are published at predictable URLs:

```
https://npp.gov.in/public-reports/cea/daily/fuel/24-08-2026/dailyCoal1-2026-08-24.xls
https://npp.gov.in/public-reports/cea/daily/fuel/24-08-2026/dailyCoal1-2026-08-24.pdf
```

In the PDF, stations flagged critical have their remarks text typeset *between* the
numeric columns, so text extraction returns cells out of order. The XLS keeps one
value per cell. `parse_pdf.py` exists as a fallback and bands words by x-coordinate
rather than reading order, which survives that layout, but the XLS is the primary path.

---

## Setup

1. Create a repo from these files and push to `main`.
2. **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`.**
3. **Settings → Actions → General → Workflow permissions → Read and write.**
   The job commits the parsed data back to the repo.
4. **Actions → Update coal data → Run workflow.** Leave the date blank for the latest
   published report.
5. **Actions → Backfill history → Run workflow** with a `from` date to build up the
   archive. See *Building history* below.

The site is live at `https://<user>.github.io/<repo>/`.

### Locally

```bash
pip install -r requirements.txt

python -m scraper.cli update                            # latest published report
python -m scraper.cli update --date 2026-08-24          # a specific date
python -m scraper.cli backfill --from 2025-09-01        # a range
python -m scraper.cli backfill --days 180               # relative window
python -m scraper.cli reindex                           # rebuild derived files

cd docs && python -m http.server 8000                   # open http://localhost:8000
```

`docs/data` ships with a sample dataset so the dashboard renders before your first
pull. It is labelled in the interface and overwritten on the first successful run.

---

## What the dashboard shows

**Fleet cover strip.** Every station as one bar, ordered by days of cover, width
scaled to capacity. The shape of the left-hand edge is the national fuel position at
a glance. Hover for detail, click to open a station.

**Headline figures**, each with a day-on-day change: total stock, all-India days of
cover, stock as a percentage of normative, critical station count, stations under
seven days, capacity at risk, and net movement (receipts less burn).

**Filters.**

| Filter | Notes |
|---|---|
| Days of cover | Range, plus presets for under 3 / 7 / 15 and over 20 |
| Cover basis | Against the normative 85% PLF requirement, or yesterday's actual burn |
| Station search | Matches name, state and utility |
| State, utility, sector, transport mode | Multi-select |
| Coal source | A domestic · B imported · C idle · D washery rejects |
| Critical only | Below 25% of normative stock |
| No coal received | Zero receipt that day |
| Drawing down | Burn exceeded receipt |
| Holding imported coal | Any imported tonnage on site |

Stations not in operation are hidden by default — they report zero stock and zero
burn, which would otherwise pin them to the head of every cover ranking.

**Table.** Sortable on any column, including Δ cover against the previous day.
Exports the filtered rows to CSV.

**Comparison baseline.** Every delta — the headline figures and the table's Δ cover
column — is measured against a baseline you choose: the previous report, a week, a
month or three months earlier, or the earliest report on file. If CEA skipped the exact
date, it falls back to the latest report before it rather than blanking the column.

**Charts.** All-India cover and critical count over time; days of cover by state,
capacity-weighted, tightest first. Opening a station shows its own stock, receipt and
burn history.

**On a phone** the filters open as a bottom sheet and the table sheds its secondary
columns; the station drawer still carries every field.

Filter state lives in the URL, so a view can be shared or bookmarked.

### Derived measures

| Measure | Definition |
|---|---|
| `cover_days_normative` | stock ÷ daily requirement at 85% PLF — the report's own yardstick |
| `cover_days_actual` | stock ÷ the previous day's actual burn — closer to operations |
| `net_change_kt` | receipt − consumption |
| `days_to_empty` | stock ÷ net draw, when drawing down |
| `pct_of_norm` | stock as a percentage of normative stock |
| `is_critical` | CEA's asterisk, or below 25% of normative |
| `is_supercritical` | below 10% of normative |
| `ownership` | Central / State / Private-IPP, from the utility group |

All tonnages are thousand tonnes (`'000 t`), as published.

---

## Building history

CEA publishes today's file and nothing else — there is no archive endpoint. The only
way to get a long series is to walk the dates and keep what you find, which is what
the backfill does.

```bash
python -m scraper.cli backfill --from 2025-09-01 --to 2026-08-24
```

It is **resumable by design**. Days already on disk are skipped, and dates CEA never
published are recorded in `docs/data/missing.json` so a re-run does not request them
again. Interrupt it, re-run it, run it in chunks — you will not lose or duplicate
work. There is a 1.5&nbsp;second pause between requests; a year takes roughly fifteen
minutes. Use `--limit` to cap a single run and `--checkpoint 30` to write indexes as
it goes.

`--recheck` forces a retry of dates in `missing.json`, for the occasional report that
gets published late.

### How far back can you go

Reports have been available at the current URL pattern for several years, but coverage
thins out and the sheet layout has changed over time. Start with a year, check the
run summary for the number of unavailable dates, then push further back if it looks
clean. The alignment guard will fail loudly on an older layout rather than write bad
rows.

### Repository size

A year of data is roughly 50&nbsp;MB: about 100&nbsp;KB per daily snapshot plus the
monthly CSVs. That is comfortable for git and for Pages. The layout is deliberately
append-mostly — a daily run rewrites about seven files, not the whole archive, so the
repository does not accumulate a fresh copy of history in every commit.

---

## Using the data outside the browser

The dashboard's **Download CSV** button exports whatever is currently filtered. For
analysis, go to the monthly partitions instead:

```
docs/data/history/2026-07.csv
docs/data/manifest.json     ← lists every partition, with column names and units
```

**pandas**

```python
import json, pandas as pd, urllib.request

BASE = "https://<user>.github.io/<repo>/data/"
man  = json.load(urllib.request.urlopen(BASE + "manifest.json"))
df   = pd.concat([pd.read_csv(BASE + p, parse_dates=["date"]) for p in man["partitions"]])

# Days of cover for one station, over the whole record
df[df.plant.str.contains("SAGARDIGHI")].set_index("date").cover_days_normative.plot()
```

**Power BI or Excel (Power Query).** Paste into *Get data → Blank query → Advanced
editor*. It reads the manifest and appends every partition, so new months appear on
refresh without touching the query:

```m
let
    Base      = "https://<user>.github.io/<repo>/data/",
    Manifest  = Json.Document(Web.Contents(Base & "manifest.json")),
    Files     = Manifest[partitions],
    Load      = List.Transform(Files, each Csv.Document(
                    Web.Contents(Base & _), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv])),
    Headed    = List.Transform(Load, each Table.PromoteHeaders(_, [PromoteAllScalars=true])),
    Combined  = Table.Combine(Headed),
    Typed     = Table.TransformColumnTypes(Combined, {
                    {"date", type date}, {"capacity_mw", Int64.Type},
                    {"stock_total_kt", type number}, {"cover_days_normative", type number},
                    {"receipt_kt", type number}, {"consumption_kt", type number},
                    {"pct_of_norm", type number}})
in
    Typed
```

For a one-off in Excel, *Data → From Web* on a single month's CSV is enough.

---

## Data files

| File | Contents |
|---|---|
| `docs/data/daily/YYYY-MM-DD.json` | One report: every station plus a summary block |
| `docs/data/latest.json` | Copy of the most recent day |
| `docs/data/index.json` | Available dates and build timestamp |
| `docs/data/trend.json` | One summary row per day |
| `docs/data/history/YYYY-MM.csv` | Monthly partitions — the full record |
| `docs/data/manifest.json` | Partition list, column names, units |
| `docs/data/plants-recent.json` | Rolling 180-day per-station series, for the drill-down chart |
| `docs/data/missing.json` | Dates CEA did not publish |

Daily snapshots drop nulls and fields the dashboard recomputes, so they are lighter
than the CSVs. If you want every column, use the CSVs.

---

## When CEA changes the sheet

Column positions are resolved by matching header text, not by hard-coded indices, so a
reordered export usually still parses. Two safety nets:

- **Alignment check.** After every parse the pipeline asserts that
  `normative stock = daily requirement × normative days` for at least 80% of rows.
  If the columns have shifted, the run fails loudly instead of publishing wrong
  numbers.
- **Inspect command.** `python -m scraper.cli inspect --date 2026-08-24` dumps the
  resolved column mapping and the first rows of the raw grid.

If matching genuinely breaks, fix it in one place: `HEADER_HINTS` and `FIELDS` in
`scraper/config.py`.

## Tests

```bash
python -m pytest tests -q
```

These cover the derived measures and the alignment guard. They do not hit the network.

---

## Caveats

- CEA publishes one to three days behind. "Latest" means the most recent published
  report, not today.
- Some stations report late; a missing figure stays missing rather than being
  interpolated.
- The 85% PLF requirement is a planning norm, not a forecast. A station running at 40%
  PLF has more real cover than the normative figure suggests — that is what the
  "actual burn" basis is for.
- This project mirrors and reformats public data. The CEA report is the record.
