# portfolio-analysis

Automated sector analysis of an investment portfolio. Joins nightly Quicken
portfolio exports with Morningstar sector classification data to produce a
daily enriched holdings CSV for analysis by OpenClaw.

## What this does

1. **Exports** the Quicken portfolio nightly to a CSV (Windows, via AHK automation)
2. **Generates** `name_map.csv` — maps every holding to its Morningstar ticker and exchange
3. **Downloads** Morningstar fund/equity/stock profile pages (one per holding)
4. **Parses** those pages into a sector breakdown CSV
5. **Joins** sector data with the Quicken export to produce
   `portfolio_with_sectors_YYYYMMDD.csv` — one row per holding with 12 GICS sector
   percentages, asset class, and account type; plus a market-value-weighted TOTAL row

## Directory layout

```
portfolio-analysis/
├── ahk/                      # AutoHotkey script for Quicken export (Windows)
├── bin/
│   ├── analyze.sh            # end-to-end orchestration (Linux/Mac)
│   ├── portfolio_export.bat  # Quicken export wrapper (Windows)
│   └── config.bat.example    # deployment config template (copy → config.bat, gitignored)
├── py/
│   ├── generate_name_map.py  # Step 1: Quicken CSV → name_map.csv
│   ├── download_profiles.py  # Step 2: download Morningstar HTML profiles
│   ├── parse_fund_profiles.py  # Step 3: HTML → fund_sectors.csv
│   ├── join_portfolio.py     # Step 4: join Quicken + sectors → output CSV
│   └── build_holdings_meta.py  # (standalone) generate holdings metadata scaffold
├── QUICKEN_EXPORT.md         # detailed docs for the Windows export automation
└── requirements.txt
```

## Running

```bash
# One-time setup
python3 -m venv pyvenv && source pyvenv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Daily analysis (Linux/Mac)
./bin/analyze.sh <data-root> <quicken-archive>
```

All output goes under `<data-root>`:
- `<data-root>/name_map.csv` — holding → ticker/exchange mapping (gitignored, manually seeded)
- `<data-root>/work_YYYYMMDD/` — downloaded HTML and `fund_sectors.csv`
- `<data-root>/portfolio_with_sectors_YYYYMMDD.csv` — final output

## Deployment

`name_map.csv` is not in the repo — it must be manually placed at `<data-root>/name_map.csv`
on first deployment. Run `generate_name_map.py` once, fill in the `Exchange` column for any
stocks it warns about, then use that file as the seed for future runs.

For Windows Task Scheduler setup, copy `bin/config.bat.example` to `bin/config.bat` and
fill in your NAS host, share name, and file paths.

See [CLAUDE.md](CLAUDE.md) for full developer guidance and [QUICKEN_EXPORT.md](QUICKEN_EXPORT.md)
for the Windows export automation.
