# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Automated sector analysis of an investment portfolio. Joins nightly Quicken portfolio exports with Morningstar sector classification data to produce a daily enriched holdings CSV for analysis by OpenClaw.

**Current status:** Pipeline fully operational end-to-end. All four steps run nightly via `bin/analyze.sh`.

## Running the pipeline

```bash
# Set up venv (one-time)
python3 -m venv pyvenv && source pyvenv/bin/activate && pip install -r requirements.txt
playwright install chromium   # also needed on Pi after pip install

# Full daily pipeline
./bin/analyze.sh <data-root> <quicken-archive>

# Individual steps
python3 py/generate_name_map.py \
    --name-map <data-root>/name_map.csv \
    --quicken-archive <dir>

python3 py/download_profiles.py \
    --name-map <data-root>/name_map.csv \
    --work-dir <data-root>/work_YYYYMMDD
    [--skip-existing] [--dry-run] [--ticker AAPL MSFT ...]

python3 py/parse_fund_profiles.py \
    --work-dir <data-root>/work_YYYYMMDD
    [--force]

python3 py/join_portfolio.py \
    --name-map <data-root>/name_map.csv \
    --fund-sectors <data-root>/work_YYYYMMDD/fund_sectors.csv \
    --out <data-root>/portfolio_with_sectors_YYYYMMDD.csv \
    --quicken-archive <dir>
```

## Four-step daily pipeline

```
Step 1 — Generate name_map (py/generate_name_map.py)
  reads:  <quicken-archive>/portfolio_YYYY-MM-DD.csv  (most recent)
          <data-root>/name_map.csv  (existing — preserves Exchange values)
  writes: <data-root>/name_map.csv
  warns:  new securities with unknown Exchange (need manual entry)

Step 2 — Download profiles (py/download_profiles.py)
  reads:  <data-root>/name_map.csv
  writes: <data-root>/work_YYYYMMDD/{ticker}.html  (one per non-bond holding)
  skips:  holdings with blank Exchange (bonds)

Step 3 — Parse profiles (py/parse_fund_profiles.py)
  reads:  <data-root>/work_YYYYMMDD/*.html
  writes: <data-root>/work_YYYYMMDD/fund_sectors.csv

Step 4 — Join (py/join_portfolio.py)
  reads:  <data-root>/work_YYYYMMDD/fund_sectors.csv
          <data-root>/name_map.csv
          <quicken-archive>/portfolio_YYYY-MM-DD.csv  (most recent)
  writes: <data-root>/portfolio_with_sectors_YYYYMMDD.csv
            columns: Account, Name, Ticker, Price, Shares, Market_Value,
                     Cost_Basis, Gain_Loss, <12 GICS sector %>, Asset_Class, Account_Type
            last row: TOTAL — market-value-weighted sector distribution across
                      all holdings with sector data
```

`bin/analyze.sh` takes both paths as required arguments and passes them explicitly to each script.

## Key reference file: `name_map.csv`

Generated nightly by `generate_name_map.py`. Gitignored — must be manually placed at `<data-root>/name_map.csv` on each deployment. Columns:

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

On a fresh deployment, run `generate_name_map.py` once, fill in `Exchange` for the warned stocks (e.g. GOOGL=xnas, JNJ=xnys), then keep that file as the seed for future runs.

## URL templates (py/download_profiles.py)

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

## Python environment

- **Dev/Deployed:** `pyvenv/` in repo root (gitignored)

All scripts use `#!/usr/bin/env python3` and rely on the active venv. Dependencies: `beautifulsoup4`, `lxml`, `playwright`.

## Quicken export automation (Windows)

The nightly Quicken CSV is produced by a Windows pipeline that runs via two Task Scheduler tasks:

| File | Role |
|------|------|
| `bin/portfolio_export.bat` | Main export: idempotency check, copies QDF, verifies Quicken not running, invokes AHK, archives CSV |
| `ahk/QuickenPortfolioExport.ahk` | UI automation: opens Quicken, navigates to Portfolio view, exports CSV; receives export path as `A_Args[1]` |

**Two-task setup required** — Quicken cannot be killed by a process without elevated privileges, and Quicken must not run elevated itself. Task Scheduler therefore uses two tasks:
1. **Kill task** (elevated, runs first): `taskkill /IM qw.exe /F`
2. **Export task** (normal user, runs after): `portfolio_export.bat`

### Configuration

`portfolio_export.bat` loads all deployment-specific paths from `bin/config.bat` (gitignored). Copy `bin/config.bat.example` → `bin/config.bat` and set:
- `NAS_HOST` / `NAS_SHARE` — NAS address and share name
- `SRC` — source QDF path
- `DST` — local working QDF path
- `AHKEXE` — path to AutoHotkey v2 executable

All other paths (`AHK`, `EXPORT_CSV`, `FINAL_DIR`) are derived automatically from `NAS_HOST`/`NAS_SHARE`.

### Data flow

```
Source QDF (G: drive / Google Drive)
  → batch copies → C:\tmp\HOME_nightly.QDF
    → AHK opens in Quicken → exports CSV
      → \\%NAS_HOST%\%NAS_SHARE%\openclaw\quicken_exports\portfolio_nightly.csv
        → batch copies → quicken_exports\portfolio_YYYY-MM-DD.csv
```

### Exit codes

**AHK script:** `0` success, `11` QDF missing, `12` Quicken window never appeared, `13` window couldn't be activated

**Batch wrapper:** `0` success (including idempotent skip), `2`–`6` pre-launch failures, `7`–`9` post-export failures, `10` Quicken still running at startup (elevated kill task must run first); AHK nonzero codes propagate directly

### Key fragility points

UI automation breaks when Quicken changes keyboard shortcuts, the number of items in the **Show** or **Group By** dropdowns (the AHK script uses a fixed count of `{Down}` keypresses), or export dialog layout. After any Quicken update, run a manual test before relying on the scheduler.

### Task Scheduler setup

**Task 1 — Kill Quicken** (run first, elevated):
- Run with highest privileges: yes
- Program: `taskkill`, Arguments: `/IM qw.exe /F`

**Task 2 — Export** (run after Task 1, normal user):
- Program: `C:\Windows\System32\cmd.exe`
- Arguments: `/c "\\%NAS_HOST%\%NAS_SHARE%\portfolio-analysis\bin\portfolio_export.bat"`
- Start in: `\\%NAS_HOST%\%NAS_SHARE%\portfolio-analysis\bin`

See `QUICKEN_EXPORT.md` for full detail.

## Output CSV columns (`portfolio_with_sectors_YYYYMMDD.csv`)

| Column | Notes |
|--------|-------|
| Account | Quicken account name |
| Name | Quicken holding name |
| Ticker | Uppercase ticker |
| Price, Shares, Market_Value, Cost_Basis, Gain_Loss | From Quicken export |
| Basic_Materials … Not_Classified | 12 GICS sector percentages (empty for bond/income holdings) |
| Asset_Class | `EQ`, `FI`, `EQ-Fund`, `FI-Fund` — derived from Asset_Type + sector data presence |
| Account_Type | `IRA`, `Roth`, `I-IRA`, `Taxable` — derived from account name |

Last row is `TOTAL`: summed market/cost/gain values; market-value-weighted sector percentages across holdings that have sector data.

`Asset_Class` derivation: `stock`→EQ, `bond`→FI, fund/etf/pfund with sector data→EQ-Fund, without→FI-Fund.

`Account_Type` derivation: "Roth" in name→Roth; "Inherited IRA"→I-IRA; "IRA", "401K", or "Health Equity" in name→IRA; else→Taxable. `_KNOWN_IRA_ACCOUNTS` in `join_portfolio.py` lists accounts whose names don't yet reflect their IRA status (remove entries once renamed in Quicken).

## Open questions

1. `build_holdings_meta.py` (human-curated asset class/region/target_pct) — decide whether to integrate with or keep separate from the automated pipeline.
2. Deploy to Pi: set up cron for `bin/analyze.sh <data-root> <quicken-archive>`.
