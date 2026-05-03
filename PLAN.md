# Implementation Plan

## Current state

Working prototype code exists in `/Volumes/pi-nas/openclaw/morningstar/` (not yet a
proper repo). A related script lives in `/Volumes/pi-nas/openclaw/portfolio/`. Neither
is under source control. The plan is to migrate and restructure everything into this
repo cleanly.

---

## Architecture decisions

### Data pipeline — three tiers

```
Tier 1 — Download (daily, automated, no LLM)
  download/investment_profile_downloads.bsh   → data/raw/profiles/*.html
  download/morningstar_equity_downloads.bsh   → data/raw/profiles/*.html  [future]
  [manual]  Morningstar X-Ray HTML save       → data/raw/xray/*.html

Tier 2 — Parse / translate (run when source HTML changes)
  parse/parse_xray_sectors.py          reads data/raw/xray/
  parse/parse_xray_intersection.py     reads data/raw/xray/
  parse/parse_fund_profiles.py         reads data/raw/profiles/
     all write to → data/output/

Tier 3 — Join / analyze (daily, lightweight, suitable for small LLM)
  analyze/join_portfolio.py
     reads: data/output/morningstar_sectors.csv
            data/output/fund_sectors.csv
            analyze/name_map.csv
            /Volumes/pi-nas/openclaw/quicken_tools/archive/portfolio_YYYY-MM-DD.csv
     writes: data/output/portfolio_with_sectors.csv
```

`daily_run.sh` chains Tier 1 and Tier 3. Tier 2 is triggered manually (or by file
modification date check) only when new HTML is downloaded.

### Morningstar URL patterns

Three distinct sources, each parsed the same way (same `mds-data-table` HTML structure):

| Source | URL pattern | Trigger |
|--------|-------------|---------|
| Private Fund funds (12) | `https://00440.mps30ebd.eas.morningstar.com/Empower%20%5bUS%5d/HTML%20Reports/Private%20Funds/{id}.html` | Daily automated |
| Public mutual funds | `https://www.morningstar.com/funds/XNAS/{TICKER}/portfolio` | Daily automated [Phase 2] |
| Public equities | `https://www.morningstar.com/stocks/XNAS/{TICKER}/quote` | Daily automated [Phase 2] |

**Exchange code gap:** Public URLs require an exchange prefix (e.g., `XNAS` for Nasdaq,
`XNYS` for NYSE). `name_map.csv` has tickers but not exchange codes. Phase 2 will add
an `Exchange` column to `name_map.csv` or derive it from a lookup. Until then, the
manually-downloaded Morningstar X-Ray HTML covers public holdings.

### Key reference file: `analyze/name_map.csv`

Maps each Quicken holding name to:
- `Sector_Key` — the exact key used in the sector CSV (fund profile HTML fund name,
  or the ≤20-char truncated name from the X-Ray HTML)
- `Ticker` — instrument ticker
- `Exchange` — exchange code for URL construction [to be added in Phase 2]

### OpenClaw vs. scripted separation

| What | Who runs it | LLM model |
|------|-------------|-----------|
| Download + parse (Tier 1+2) | Cron / scheduler | None |
| join_portfolio.py (Tier 3) | Cron, or OpenClaw on demand | Haiku |
| Portfolio analysis questions | OpenClaw, reads CSVs | Any |
| Parsing new/unknown HTML format | OpenClaw, one-time | Opus |

### Python environment

- **Dev:** `.venv/` inside repo root — gitignored, used for local development
- **Deployed:** `/Volumes/pi-nas/openclaw/venv/` — accessible to OpenClaw at
  `/mnt/openclaw/venv/`; populated during deployment by `pip install -r requirements.txt`
- Scripts reference `#!/usr/bin/env python3` and rely on the active venv

---

## Phased implementation

### Phase 0 — Repo setup and migration *(next session)*

- [ ] `git init` in `/Volumes/pi-nas/portfolio-analysis/`
- [ ] Create `.gitignore` (venv, data/, `*.pyc`, `.DS_Store`)
- [ ] Create `requirements.txt` (beautifulsoup4, lxml, pdfplumber)
- [ ] Create directory skeleton (`download/`, `parse/`, `analyze/`, `data/raw/xray/`,
      `data/raw/profiles/`, `data/output/`)
- [ ] Move `openclaw/morningstar/investment_profile_downloads.bsh` → `download/`
- [ ] Move and rename parse scripts from `openclaw/morningstar/`:
  - `parse_sectors.py` → `parse/parse_xray_sectors.py`
  - `parse_intersection.py` → `parse/parse_xray_intersection.py`
  - `parse_fund_pdfs.py` → retire (replaced by `parse_fund_profiles.py`)
- [ ] Move `openclaw/portfolio/build_holdings_meta.py` → `analyze/`
- [ ] Move `analyze/join_portfolio.py` and `analyze/name_map.csv` from
      `openclaw/morningstar/`
- [ ] Move existing HTML files → `data/raw/xray/` and `data/raw/profiles/`
- [ ] Move generated CSVs → `data/output/`
- [ ] Update all hardcoded paths in scripts to use config or relative paths
- [ ] Write `daily_run.sh`
- [ ] Initial commit

### Phase 1 — Private Fund fund profiles *(next session)*

- [ ] Write `parse/parse_fund_profiles.py` (HTML → sector CSV, covers Private Fund
      pages and future public Morningstar pages — same HTML structure)
- [ ] Update `analyze/name_map.csv` with correct Quicken→sector-key mappings for
      all 12 Private Fund funds (bond funds marked as no-sector-data)
- [ ] Verify `join_portfolio.py` match rate improves from 92/105 to ~100/105
- [ ] Wire `parse_fund_profiles.py` into `daily_run.sh`

### Phase 2 — Automated public holdings downloads *(future)*

Goal: eliminate the manual Morningstar X-Ray download by fetching sector data
for all public holdings directly.

- [ ] Add `Exchange` column to `name_map.csv`
- [ ] Write `download/morningstar_equity_downloads.bsh` (or Python equivalent)
      using URL patterns from the table above
- [ ] Verify HTML structure matches Private Fund pages (likely same `mds-data-table`
      classes — needs confirmation against a real download)
- [ ] Retire manual X-Ray workflow once coverage is equivalent

### Phase 3 — OpenClaw deployment and permissions

- [ ] Decide which scripts OpenClaw is permitted to run (join only? or parse too?)
- [ ] Document permitted script paths in OpenClaw config
- [ ] Deploy venv to `/Volumes/pi-nas/openclaw/venv/`
- [ ] Smoke-test full pipeline end-to-end from OpenClaw session

---

## Cleanup tasks (openclaw area)

The following will be removed from `/Volumes/pi-nas/openclaw/` once the corresponding
code is migrated and verified in this repo:

| Path | Action |
|------|--------|
| `openclaw/morningstar/parse_sectors.py` | Migrate → `parse/parse_xray_sectors.py` |
| `openclaw/morningstar/parse_intersection.py` | Migrate → `parse/parse_xray_intersection.py` |
| `openclaw/morningstar/parse_fund_pdfs.py` | Retire — replaced by `parse_fund_profiles.py` |
| `openclaw/morningstar/join_portfolio.py` | Migrate → `analyze/join_portfolio.py` |
| `openclaw/morningstar/name_map.csv` | Migrate → `analyze/name_map.csv` |
| `openclaw/morningstar/*.html` | Move → `data/raw/` |
| `openclaw/morningstar/*.csv` | Move → `data/output/` |
| `openclaw/morningstar/investment_profile_downloads.bsh` | Migrate → `download/` |
| `openclaw/morningstar/` | Remove directory once empty |
| `openclaw/portfolio/build_holdings_meta.py` | Migrate → `analyze/` |
| `openclaw/portfolio/holdings_meta.csv` | Move → `data/output/` |
| `openclaw/portfolio/` | Remove directory once empty |

**Note:** `openclaw/quicken_tools/archive/` is **not** moved — it must remain in the
openclaw hierarchy for OpenClaw to access the nightly Quicken exports.

---

## Open questions

1. **`openclaw/portfolio/holdings_meta.csv`** — what columns has the user filled in?
   Review before migrating to understand if there's manual data to preserve.

2. **X-Ray HTML replacement (Phase 2)** — the public Morningstar pages (`/portfolio`,
   `/quote`) may be behind rate limiting or bot detection. Need to test a real
   automated curl before committing to this approach.

3. **Quicken archive path** — scripts currently hardcode
   `/Volumes/pi-nas/openclaw/quicken_tools/archive/`. This should become a config
   variable so the same scripts work from both the Mac path and OpenClaw's
   `/mnt/openclaw/...` path.

4. **`build_holdings_meta.py` scope** — this script generates a holdings list with
   manually-filled `asset_class`, `region`, `sector`, `target_pct` columns. It
   overlaps partially with `join_portfolio.py`. Decide whether to merge them or
   keep them separate (they serve different purposes: meta is human-curated
   classification; join is automated sector data from Morningstar).
