# portfolio-analysis

Automated sector analysis of an investment portfolio. Joins nightly Quicken
portfolio exports with Morningstar sector classification data to produce a
daily enriched holdings CSV for analysis by OpenClaw.

## What this does

1. **Downloads** Morningstar fund/equity profile pages (automated daily)
2. **Parses** those pages and Morningstar X-Ray exports into clean sector CSVs
3. **Joins** sector data with the Quicken nightly export to produce
   `portfolio_with_sectors.csv` — one row per holding, with 12 GICS sector
   percentages attached

## Relationship to other repos

| Repo | Role |
|------|------|
| `quicken_tools` | Windows-side: AHK + batch automation that exports the Quicken portfolio nightly to a CSV in `openclaw/quicken_tools/archive/` |
| **`portfolio-analysis`** (this repo) | Mac/NAS-side: downloads, parses, and joins to produce the sector-enriched output |

The Quicken archive directory (`/Volumes/pi-nas/openclaw/quicken_tools/archive/`)
stays within the OpenClaw hierarchy so OpenClaw can read it directly. This repo
references it by path.

## Quick start

See [PLAN.md](PLAN.md) for the full implementation plan and current status.
See [docs/SETUP.md](docs/SETUP.md) for environment setup once the project is built out.

## Directory layout

```
portfolio-analysis/
├── download/           # scripts that fetch raw HTML from Morningstar
├── parse/              # HTML → CSV translators (run when source changes)
├── analyze/            # daily join: Quicken CSV + sector CSVs → output
├── data/               # gitignored — raw downloads and generated CSVs
│   ├── raw/
│   │   ├── xray/       # manual Morningstar X-Ray HTML downloads
│   │   └── profiles/   # automated fund/equity profile HTML downloads
│   └── output/         # generated CSVs consumed by OpenClaw
├── daily_run.sh        # end-to-end orchestration: download → parse → join
└── requirements.txt
```

## OpenClaw integration

OpenClaw reads from `data/output/` (accessible at `/mnt/portfolio-analysis/data/output/`
within the OpenClaw environment). It does **not** run the download or parse steps —
those run on a schedule. It may run `analyze/join_portfolio.py` on demand to refresh
the join against the latest Quicken archive.

The shared Python environment is deployed at `/Volumes/pi-nas/openclaw/venv/` and
is accessible to OpenClaw. The repo also contains a `.venv/` for local development
(gitignored).
