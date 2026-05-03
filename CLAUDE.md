# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Automated sector analysis of an investment portfolio. Joins nightly Quicken portfolio exports with Morningstar sector classification data to produce a daily enriched holdings CSV for analysis by OpenClaw.

**Current status:** Pipeline fully operational end-to-end. All four steps run nightly via `daily_run.sh`.

## Running the pipeline

```bash
# Set up dev venv (one-time)
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
playwright install chromium   # also needed on Pi after pip install

# Full daily pipeline
./daily_run.sh

# Individual steps
python3 analyze/generate_name_map.py             # Step 1: Quicken export → name_map.csv
python3 download/download_profiles.py            # Step 2: download all Morningstar profiles
python3 download/download_profiles.py --skip-existing  # Step 2: only download missing files
python3 download/download_profiles.py --dry-run  # Step 2: print URLs without downloading
python3 parse/parse_fund_profiles.py --force     # Step 3: HTML → fund_sectors.csv
python3 analyze/join_portfolio.py                # Step 4: join Quicken + sector data
python3 analyze/join_portfolio.py --quicken path/to/portfolio_YYYY-MM-DD.csv
```

## Four-step daily pipeline

```
Step 1 — Generate name_map (analyze/generate_name_map.py)
  reads:  $QUICKEN_ARCHIVE/portfolio_YYYY-MM-DD.csv  (most recent)
  writes: analyze/name_map.csv
  warns:  new securities with unknown Exchange (need manual entry)

Step 2 — Download profiles (download/download_profiles.py)
  reads:  analyze/name_map.csv
  writes: data/raw/profiles/{ticker}.html  (one file per non-bond holding)
  skips:  holdings with blank Exchange (bonds)

Step 3 — Parse profiles (parse/parse_fund_profiles.py)
  reads:  data/raw/profiles/*.html
  writes: data/output/fund_sectors.csv

Step 4 — Join (analyze/join_portfolio.py)
  reads:  data/output/fund_sectors.csv
          analyze/name_map.csv
          $QUICKEN_ARCHIVE/portfolio_YYYY-MM-DD.csv  (most recent)
  writes: data/output/portfolio_with_sectors.csv
```

## Key reference file: `analyze/name_map.csv`

Generated nightly by `generate_name_map.py`. Do not edit by hand — re-run the generator instead. Columns:

- `Quicken_Name` — exact string from the Quicken CSV export
- `Ticker` — instrument ticker (uppercase for pfund; lowercase used in Morningstar URLs)
- `Asset_Type` — `stock`, `fund`, `etf`, `pfund`, or `bond`
- `Exchange` — Morningstar exchange code used to construct download URLs; blank for bonds (no download)

**Classification rules** (applied to uppercase ticker by `generate_name_map.py`):
1. 5 chars ending in `X` → `fund`, exchange `xnas`
2. Starts with `SPU` → `pfund`, exchange `pfund`
3. Starts with a digit → `bond`, exchange blank (no download URL)
4. Ends with `ZF` → `stock`, exchange `pinx`
5. Otherwise → `stock`, exchange from existing name_map or blank (warns if blank)

Exchange is preserved from existing name_map for known holdings. `etf` Asset_Type is also preserved (can't be auto-detected from ticker). All other Asset_Type values are always rule-derived.

When `join_portfolio.py` reports positions with no sector data, the cause is either: (a) profile not yet downloaded, or (b) no GICS sector breakdown on the Morningstar page (expected for bond/income funds).

## URL templates (download_profiles.py)

| Asset_Type | Exchange | URL pattern |
|------------|----------|-------------|
| `fund`     | `xnas`   | `morningstar.com/funds/{exchange}/{ticker}/portfolio` |
| `etf`      | `xnas`/`arcx` | `morningstar.com/etfs/{exchange}/{ticker}/portfolio` |
| `stock`    | `xnas`/`xnys`/`pinx` | `morningstar.com/stocks/{exchange}/{ticker}/quote` |
| `pfund`    | `pfund`  | `00440.mps30ebd.eas.morningstar.com/Empower.../Private%20Funds/{ticker}.html` |

Tickers are lowercased in URLs for all types **except** `pfund` (Empower server is case-sensitive).

## Quicken CSV format

Latin-1 encoded. Header row (`Name`, `Ticker Symbol`, `Quote/Price`, ...) is found by scanning — not at line 1. Column layout:

| col | field |
|-----|-------|
| 0 | Name |
| 1 | Ticker Symbol |
| 2 | Quote/Price |
| 3 | Shares |
| 4 | Market Value |
| 5 | Cost Basis |
| 6 | Gain/Loss |

Account section headers have no price or shares (cols 2 and 3 blank). `SKIP_NAMES = {"Cash"}` — all other exclusions are data-driven.

## HTML parsing conventions

`parse_fund_profiles.py` handles three page types:
- **pfund private pages** — table header: `['Sector', 'Fund %', ...]`
- **Public fund/ETF pages** — table header: `['Sectors', 'Investment%', ...]`
- **Stock quote pages** — no sector table; sector extracted from `Sector X Industry Y` text → 100% row

Pages with no sector data (bond funds, some international funds) produce no row in `fund_sectors.csv`; the join outputs empty sector columns for those positions.

## Python environments

- **Dev:** `.venv/` in repo root (gitignored)
- **Deployed:** `/Volumes/pi-nas/openclaw/venv/` — shared with OpenClaw, populated by `pip install -r requirements.txt`

All scripts use `#!/usr/bin/env python3` and rely on the active venv. Dependencies: `beautifulsoup4`, `lxml`, `playwright`.

## External paths

| Path | Role |
|------|------|
| `/Volumes/pi-nas/openclaw/quicken_tools/archive/` | Nightly Quicken CSV exports |
| `data/output/` | Generated CSVs consumed by OpenClaw (accessible at `/mnt/portfolio-analysis/data/output/` within OpenClaw) |

`QUICKEN_ARCHIVE` env var overrides the default archive path (needed on Pi where mount paths differ).

## Deployment notes

`analyze/name_map.csv` is gitignored — it must be manually placed on each deployment. On a fresh clone, run `generate_name_map.py` once, then fill in `Exchange` for any securities it warns about (rule-5 stocks like GOOGL, JNJ, etc. that can't be auto-classified), then copy the file to the deployment target.

`QUICKEN_ARCHIVE` env var overrides the default archive path — needed on Pi where the mount path differs from Mac.

## Open questions

1. `build_holdings_meta.py` (human-curated asset class/region/target_pct) — decide whether to integrate with or keep separate from the automated pipeline.
2. Deploy to Pi: set `QUICKEN_ARCHIVE`, set up cron for `daily_run.sh`.
