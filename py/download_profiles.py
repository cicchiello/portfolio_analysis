#!/usr/bin/env python3
"""
Download Morningstar fund/equity profile pages.

Reads name_map.csv and downloads one HTML page per holding that has
Asset_Type and Exchange populated. Uses Playwright (headless Chromium) so that
JavaScript-rendered content is fully loaded before saving.

Supported exchanges:
  pfund     — private fund URLs; ticker is the provider's fund ID
  xnas      — Morningstar public pages, Nasdaq-listed
  xnys      — Morningstar public pages, NYSE-listed
  arcx      — Morningstar public pages, NYSE Arca (ETFs)
  pinx      — Morningstar public pages, OTC/Pink Sheets

Asset_Type determines the URL path for public exchanges (stock/fund/etf).

Setup (one-time, per environment):
  pip install -r requirements.txt
  playwright install chromium

Usage:
  python3 py/download_profiles.py --name-map <path> --work-dir <dir>
  python3 py/download_profiles.py --name-map <path> --work-dir <dir> --skip-existing
  python3 py/download_profiles.py --name-map <path> --work-dir <dir> --dry-run
  python3 py/download_profiles.py --name-map <path> --work-dir <dir> --ticker AAPL MSFT
"""

import csv
import sys
import time
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

_MS_BASE = "https://www.morningstar.com"

_URL_TEMPLATES = {
    "pfund":  "https://00440.mps30ebd.eas.morningstar.com/Empower%20%5bUS%5d/HTML%20Reports/Private%20Funds/{ticker}.html",
    "stock":  f"{_MS_BASE}/stocks/{{exchange}}/{{ticker}}/quote",
    "fund":   f"{_MS_BASE}/funds/{{exchange}}/{{ticker}}/portfolio",
    "etf":    f"{_MS_BASE}/etfs/{{exchange}}/{{ticker}}/portfolio",
}


def load_targets(name_map_path):
    """Read name_map.csv; return one target dict per downloadable row."""
    p = Path(name_map_path)
    if not p.exists():
        sys.exit(f"ERROR: {p} not found")

    targets = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            exchange   = row.get("Exchange", "").strip()
            ticker     = row.get("Ticker", "").strip()
            asset_type = row.get("Asset_Type", "").strip().lower()
            name       = row.get("Quicken_Name", "").strip()

            if not exchange or not ticker:
                continue

            template_key = exchange if exchange == "pfund" else asset_type
            template = _URL_TEMPLATES.get(template_key)
            if template is None:
                continue

            ticker_in_url = ticker if exchange == "pfund" else ticker.lower()
            url = template.format(exchange=exchange.lower(), ticker=ticker_in_url)
            targets.append({"name": name, "ticker": ticker, "url": url})

    return targets


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name-map",      required=True, help="Path to name_map.csv")
    parser.add_argument("--work-dir",      required=True, help="Directory for downloaded HTML files")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist on disk")
    parser.add_argument("--dry-run",       action="store_true", help="Print URLs without downloading")
    parser.add_argument("--delay",         type=float, default=2.0, help="Seconds between requests (default: 2)")
    parser.add_argument("--ticker",        nargs="+", metavar="TICKER", help="Download only these ticker(s)")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    targets = load_targets(args.name_map)
    if args.ticker:
        want = {t.upper() for t in args.ticker}
        targets = [t for t in targets if t["ticker"].upper() in want]
    print(f"Targets: {len(targets)}")

    if args.dry_run:
        for t in targets:
            out = work_dir / f"{t['ticker']}.html"
            status = "skip" if (out.exists() and args.skip_existing) else "download"
            print(f"  [{status}] {t['url']}")
        return

    ok = skipped = errors = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux aarch64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = context.new_page()

        for t in targets:
            out = work_dir / f"{t['ticker']}.html"
            if out.exists() and args.skip_existing:
                print(f"  skip (exists): {t['ticker']}  ({t['name']})")
                skipped += 1
                continue

            try:
                page.goto(t["url"], wait_until="networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass

            title = page.title()
            if "verification" in title.lower() or "challenge" in title.lower():
                print(f"  BLOCKED (bot challenge): {t['ticker']}  ({t['name']})")
                errors += 1
                continue

            html = page.content()
            out.write_text(html, encoding="utf-8")
            print(f"  downloaded: {t['ticker']}  ({t['name']})")
            ok += 1

            if args.delay > 0:
                time.sleep(args.delay)

        browser.close()

    print(f"\nResult: {ok} downloaded, {skipped} skipped, {errors} errors")
    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
