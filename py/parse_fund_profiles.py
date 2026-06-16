#!/usr/bin/env python3
"""
Parse Morningstar fund/equity profile HTML pages → fund_sectors.csv.

Reads all *.html files in the work directory. Handles three page types:

  Private Fund pages  — table header: ['Sector', 'Fund %', ...]
  Public fund/ETF     — table header: ['Sectors', 'Investment%', ...]
  Individual stocks   — no sector table; sector extracted from page text,
                        producing a 100% row for that one sector

Usage:
  python3 py/parse_fund_profiles.py --work-dir <dir>
  python3 py/parse_fund_profiles.py --work-dir <dir> --force
"""

import csv
import json
import re
import sys
import argparse
from pathlib import Path
from bs4 import BeautifulSoup

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


def extract_ms_price(soup):
    """Extract closing/NAV price from a Morningstar page. Returns float or None."""
    for script in soup.find_all("script"):
        s = script.string or ""
        if "PriceSpecification" in s:
            try:
                data = json.loads(s)
                p = data.get("price")
                if p is not None:
                    return float(p)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    text = soup.get_text(" ")

    m = re.search(r"Previous Close Price\s+\$([0-9,]+\.[0-9]+)", text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    m = re.search(r"\bPrice\s+([0-9]+\.[0-9]+)\s", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    return None


def _is_bot_page(soup):
    title = (soup.title.string or "") if soup.title else ""
    return "verification" in title.lower() or "not found" in title.lower()


def find_sector_table(soup):
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
    text = soup.get_text(" ")
    m = re.search(r'Sector\s+([\w &]+?)\s+Industry', text)
    if not m:
        return None
    col = SECTOR_NAME_MAP.get(m.group(1).strip())
    if not col:
        return None
    return {c: (100.0 if c == col else 0.0) for c in SECTOR_COLS}


def parse_html(path):
    """Return (ms_name, sector_dict_or_None, price_or_None)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    ms_name = path.stem

    if _is_bot_page(soup):
        return ms_name, None, None

    price = extract_ms_price(soup)

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
            return ms_name, sectors, price

    stock_sectors = extract_stock_sector(soup)
    if stock_sectors is not None:
        return ms_name, stock_sectors, price

    return ms_name, None, price


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, help="Directory containing HTML files; fund_sectors.csv written here")
    parser.add_argument("--force",    action="store_true", help="Reprocess already-written entries")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    out_path = work_dir / "fund_sectors.csv"
    out_prices_path = work_dir / "fund_prices.csv"

    htmls = sorted(p for p in work_dir.glob("*.html") if not p.name.startswith("._"))
    if not htmls:
        sys.exit(f"No HTML files found in {work_dir}")

    existing = set()
    if not args.force and out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            existing = {row["MS_Name"] for row in csv.DictReader(f)}

    existing_prices = set()
    if not args.force and out_prices_path.exists():
        with open(out_prices_path, newline="", encoding="utf-8") as f:
            existing_prices = {row["MS_Name"] for row in csv.DictReader(f)}

    new_rows, new_prices, skipped, failed = [], [], [], []

    for html in htmls:
        ms_name, sectors, price = parse_html(html)

        if ms_name in existing:
            skipped.append(html.name)
            continue

        if sectors is None:
            failed.append(html.name)
        else:
            new_rows.append({"MS_Name": ms_name, **{c: sectors.get(c, 0.0) for c in SECTOR_COLS}})
            dominant = max((c for c in SECTOR_COLS if c != "Not_Classified"), key=lambda c: sectors.get(c, 0.0))
            print(f"  OK  {html.name:40s}  dominant: {dominant} {sectors.get(dominant, 0.0):.1f}%")

        if price is not None and ms_name not in existing_prices:
            new_prices.append({"MS_Name": ms_name, "MS_Price": price})

    if new_rows:
        mode = "w" if args.force or not out_path.exists() else "a"
        with open(out_path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["MS_Name"] + SECTOR_COLS)
            if mode == "w":
                w.writeheader()
            w.writerows(new_rows)
        print(f"\nWrote {len(new_rows)} entries → {out_path}")
    else:
        print("No new entries to write.")

    if new_prices:
        mode = "w" if args.force or not out_prices_path.exists() else "a"
        with open(out_prices_path, mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["MS_Name", "MS_Price"])
            if mode == "w":
                w.writeheader()
            w.writerows(new_prices)
        print(f"Wrote {len(new_prices)} prices → {out_prices_path}")

    if skipped:
        print(f"Skipped {len(skipped)} already-written.")
    if failed:
        print(f"\nNo sector data ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()
