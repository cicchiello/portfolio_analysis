#!/usr/bin/env python3
"""
Stage 3 (daily): Join Quicken portfolio positions with Morningstar sector data.

Inputs:
  data/output/fund_sectors.csv      - from parse/parse_fund_profiles.py
  data/output/morningstar_sectors.csv - from parse/parse_xray_sectors.py (optional)
  analyze/name_map.csv              - maps Quicken names → sector keys + tickers
  $QUICKEN_ARCHIVE/portfolio_YYYY-MM-DD.csv  (most recent)

Usage:
  python3 analyze/join_portfolio.py
  python3 analyze/join_portfolio.py --quicken path/to/portfolio_2026-04-30.csv
"""

import csv
import os
import sys
import argparse
from pathlib import Path

REPO    = Path(__file__).parent.parent
ARCHIVE = Path(os.environ.get("QUICKEN_ARCHIVE", "/Volumes/pi-nas/openclaw/quicken_tools/archive"))

SECTOR_COLS = [
    "Basic_Materials", "Consumer_Cyclical", "Financial_Services", "Real_Estate",
    "Communication_Services", "Energy", "Industrials", "Technology",
    "Consumer_Defensive", "Healthcare", "Utilities", "Not_Classified",
]

SKIP_NAMES = {"Cash"}


def find_latest_quicken():
    csvs = sorted(ARCHIVE.glob("portfolio_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    if not csvs:
        sys.exit(f"ERROR: No portfolio_YYYY-MM-DD.csv found in {ARCHIVE}")
    return csvs[-1]


def load_sectors(*paths):
    """Merge one or more sector CSVs keyed by MS_Name; first occurrence wins."""
    sectors = {}
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = row["MS_Name"]
                if key not in sectors:
                    sectors[key] = {c: row.get(c, "") for c in SECTOR_COLS}
    return sectors


def load_name_map(path):
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result[row["Quicken_Name"]] = {"Ticker": row["Ticker"]}
    return result


def parse_num(s):
    if not s:
        return None
    s = s.strip().strip('"').replace(",", "").replace("*", "").replace(" A", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_quicken(path):
    holdings = []
    current_account = None
    stop_markers = {"Watch List  (add) (edit)", "Indexes", "Totals:", "PCFN"}

    with open(path, newline="", encoding="latin-1") as f:
        rows = list(csv.reader(f))

    data_start = next(
        (i + 1 for i, r in enumerate(rows) if r and r[0] == "Name"), 0
    )

    for row in rows[data_start:]:
        if not row or all(c.strip() == "" for c in row):
            continue
        name = row[0].strip().strip('"')
        if not name:
            continue
        if name in stop_markers or name.startswith("Watch List"):
            break

        ticker = (row[1].strip() if len(row) > 1 else "").upper()
        price  = parse_num(row[2] if len(row) > 2 else "")
        shares = parse_num((row[3] if len(row) > 3 else "").replace(" A", ""))
        mktval = parse_num(row[4] if len(row) > 4 else "")
        costb  = parse_num(row[5] if len(row) > 5 else "")
        gainls = parse_num(row[6] if len(row) > 6 else "")

        if price is None and shares is None:
            current_account = name
            continue

        if name in SKIP_NAMES or name == "Cash":
            continue

        holdings.append({
            "Account":      current_account or "",
            "Name":         name,
            "Ticker":       ticker,
            "Price":        price,
            "Shares":       shares,
            "Market_Value": mktval,
            "Cost_Basis":   costb,
            "Gain_Loss":    gainls,
        })

    return holdings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quicken", help="Path to Quicken archive CSV")
    args = parser.parse_args()

    quicken_path = Path(args.quicken) if args.quicken else find_latest_quicken()
    name_map_csv = Path(__file__).parent / "name_map.csv"

    if not name_map_csv.exists():
        sys.exit(f"ERROR: {name_map_csv} not found")

    sectors = load_sectors(
        REPO / "data/output/fund_sectors.csv",
        REPO / "data/output/morningstar_sectors.csv",
    )
    name_map = load_name_map(name_map_csv)

    print(f"Quicken file : {quicken_path.name}")
    print(f"Sector keys  : {len(sectors)}")
    positions = parse_quicken(quicken_path)
    print(f"Positions    : {len(positions)}")

    out_rows  = []
    unmatched = []

    for pos in positions:
        qname   = pos["Name"]
        mapping = name_map.get(qname)

        ticker      = mapping["Ticker"] if mapping else pos.get("Ticker", "")
        sector_data = sectors.get(ticker) if ticker else None

        row = {**pos, "Ticker": ticker}
        if sector_data:
            row.update(sector_data)
        else:
            row.update({c: "" for c in SECTOR_COLS})
            if qname not in SKIP_NAMES:
                unmatched.append(qname)

        out_rows.append(row)

    out_path   = REPO / "data/output/portfolio_with_sectors.csv"
    fieldnames = [
        "Account", "Name", "Ticker", "Price", "Shares",
        "Market_Value", "Cost_Basis", "Gain_Loss",
    ] + SECTOR_COLS

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    matched = len(out_rows) - len(unmatched)
    print(f"Matched      : {matched}/{len(out_rows)} positions have sector data")
    print(f"Written      : {out_path}")

    if unmatched:
        print(f"\nNo sector data ({len(set(unmatched))} unique) — profile not yet downloaded or no sector data on Morningstar page:")
        for n in sorted(set(unmatched)):
            print(f"  {n}")


if __name__ == "__main__":
    main()
