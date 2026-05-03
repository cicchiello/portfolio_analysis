#!/usr/bin/env python3
"""
Tier 2: Parse Morningstar fund/equity profile HTML pages → fund_sectors.csv.

Reads all *.html files in data/raw/profiles/. Handles three page types:

  Private Fund private pages  — table header: ['Sector', 'Fund %', ...]
  Public fund/ETF pages   — table header: ['Sectors', 'Investment%', ...]
  Individual stock pages  — no sector table; sector extracted from page text,
                            producing a 100% row for that one sector

Run when new HTML files are downloaded (not part of daily_run.sh).

Output:
  data/output/fund_sectors.csv   one row per holding, same schema as
                                 morningstar_sectors.csv so join_portfolio.py
                                 can load both interchangeably.
"""

import csv
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

REPO     = Path(__file__).parent.parent
IN_DIR   = REPO / "data/raw/profiles"
OUT_PATH = REPO / "data/output/fund_sectors.csv"

SECTOR_COLS = [
    "Basic_Materials", "Consumer_Cyclical", "Financial_Services", "Real_Estate",
    "Communication_Services", "Energy", "Industrials", "Technology",
    "Consumer_Defensive", "Healthcare", "Utilities", "Not_Classified",
]

SECTOR_NAME_MAP = {
    "Basic Materials":        "Basic_Materials",
    "Consumer Cyclical":      "Consumer_Cyclical",
    "Financial Services":     "Financial_Services",
    "Real Estate":            "Real_Estate",
    "Communication Services": "Communication_Services",
    "Energy":                 "Energy",
    "Industrials":            "Industrials",
    "Technology":             "Technology",
    "Consumer Defensive":     "Consumer_Defensive",
    "Healthcare":             "Healthcare",
    "Utilities":              "Utilities",
}


def _is_bot_page(soup):
    title = (soup.title.string or "") if soup.title else ""
    return "verification" in title.lower() or "not found" in title.lower()


def find_sector_table(soup):
    """
    Return (rows, value_col_index) for the first matching sector table, or (None, None).

    Recognises two layouts:
      Private Fund  — header: ['Sector', 'Fund %', ...]          value in col 1
      Public    — header: ['Sectors', 'Investment%', ...]    value in col 1
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [td.get_text(strip=True) for td in rows[0].find_all(["td", "th"])]
        if len(header) < 2:
            continue

        if header[0] == "Sector" and header[1].startswith("Fund %"):
            val_col = 1
        elif header[0] == "Sectors" and "Investment" in header[1]:
            val_col = 1
        else:
            continue

        if len(rows) > 1:
            first = [td.get_text(strip=True) for td in rows[1].find_all(["td", "th"])]
            if first and first[0] in SECTOR_NAME_MAP:
                return rows, val_col

    return None, None


def extract_stock_sector(soup):
    """
    For individual stock quote pages: find 'Sector <Name> Industry' in page text
    and return a sectors dict with 100% in that one sector.
    """
    text = soup.get_text(" ")
    m = re.search(r'Sector\s+([\w &]+?)\s+Industry', text)
    if not m:
        return None
    col = SECTOR_NAME_MAP.get(m.group(1).strip())
    if not col:
        return None
    return {c: (100.0 if c == col else 0.0) for c in SECTOR_COLS}


def parse_html(path):
    """Return (ms_name, sector_dict) or (ms_name, None) if no sector data found."""
    with open(path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    ms_name = path.stem

    if _is_bot_page(soup):
        return ms_name, None

    rows, val_col = find_sector_table(soup)
    if rows is not None:
        sectors = {}
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) <= val_col:
                continue
            col = SECTOR_NAME_MAP.get(cells[0])
            if col is None:
                continue
            try:
                sectors[col] = float(cells[val_col])
            except ValueError:
                pass
        if len(sectors) >= 11:
            sectors.setdefault("Not_Classified", 0.0)
            return ms_name, sectors

    stock_sectors = extract_stock_sector(soup)
    if stock_sectors is not None:
        return ms_name, stock_sectors

    return ms_name, None


def load_existing():
    if not OUT_PATH.exists():
        return set()
    with open(OUT_PATH, newline="", encoding="utf-8") as f:
        return {row["MS_Name"] for row in csv.DictReader(f)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reprocess already-written entries")
    args = parser.parse_args()

    htmls = sorted(p for p in IN_DIR.glob("*.html") if not p.name.startswith("._"))
    if not htmls:
        sys.exit(f"No HTML files found in {IN_DIR}")

    existing = set() if args.force else load_existing()
    new_rows, skipped, failed = [], [], []

    for html in htmls:
        ms_name, sectors = parse_html(html)

        if ms_name in existing:
            skipped.append(html.name)
            continue

        if sectors is None:
            failed.append(html.name)
            continue

        new_rows.append({"MS_Name": ms_name, **{c: sectors.get(c, 0.0) for c in SECTOR_COLS}})
        dominant = max((c for c in SECTOR_COLS if c != "Not_Classified"), key=lambda c: sectors.get(c, 0.0))
        print(f"  OK  {html.name:40s}  dominant: {dominant} {sectors.get(dominant, 0.0):.1f}%")

    if new_rows:
        mode = "w" if args.force else "a"
        with open(OUT_PATH, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["MS_Name"] + SECTOR_COLS)
            if mode == "w":
                w.writeheader()
            w.writerows(new_rows)
        print(f"\nWrote {len(new_rows)} entries → {OUT_PATH}")
    else:
        print("No new entries to write.")

    if skipped:
        print(f"Skipped {len(skipped)} already-written.")
    if failed:
        print(f"\nNo sector data ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()
