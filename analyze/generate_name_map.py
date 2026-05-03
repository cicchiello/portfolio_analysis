#!/usr/bin/env python3
"""
Generate analyze/name_map.csv from the latest Quicken export.

Exchange is derived from 5 rules applied to the uppercase ticker:
  1. 5 chars ending X                     → fund,   xnas
  2. Starts with SPU                      → pfund,  pfund
  3. Starts with a digit                  → bond,   (blank — no Morningstar download)
  4. Ends with ZF                         → equity, pinx
  5. Otherwise                            → equity, exchange from existing name_map or blank

Prints warnings for:
  - New securities with unknown exchange (manual entry required in name_map.csv)
  - New securities entering the portfolio
  - Securities no longer in the portfolio (removed from name_map.csv)

Usage:
  python3 analyze/generate_name_map.py
  python3 analyze/generate_name_map.py --quicken path/to/portfolio_YYYY-MM-DD.csv
"""

import argparse
import csv
import os
import sys
from pathlib import Path

REPO    = Path(__file__).parent.parent
ARCHIVE = Path(os.environ.get("QUICKEN_ARCHIVE", "/Volumes/pi-nas/openclaw/quicken_tools/archive"))


def classify(ticker):
    """Return (asset_type, exchange) from ticker using the 5 rules."""
    t = ticker.upper()
    if len(t) == 5 and t.endswith("X"):
        return "fund", "xnas"
    if t.startswith("SPU"):
        return "pfund", "pfund"
    if t and t[0].isdigit():
        return "bond", ""
    if t.endswith("ZF"):
        return "stock", "pinx"
    return "stock", ""


def find_latest_quicken():
    csvs = sorted(ARCHIVE.glob("portfolio_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    if not csvs:
        sys.exit(f"ERROR: No portfolio_YYYY-MM-DD.csv found in {ARCHIVE}")
    return csvs[-1]


def parse_num(s):
    try:
        return float(s.strip().replace(",", "").replace("*", "").replace(" A", ""))
    except (ValueError, AttributeError):
        return None


def parse_quicken(path):
    """Return ordered list of (quicken_name, ticker) unique by name, preserving first occurrence."""
    stop = {"Watch List  (add) (edit)", "Indexes", "Totals:", "PCFN"}
    holdings = []
    seen_names = set()
    current_account = None

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
        if name in stop or name.startswith("Watch List"):
            break

        ticker = (row[1].strip() if len(row) > 1 else "").upper()
        price  = parse_num(row[2] if len(row) > 2 else "")
        shares = parse_num((row[3] if len(row) > 3 else "").replace(" A", ""))

        if price is None and shares is None:
            current_account = name
            continue

        if name == "Cash":
            continue

        if name not in seen_names:
            seen_names.add(name)
            holdings.append((name, ticker))

    return holdings


def load_existing(path):
    """Return dict of Quicken_Name → {Ticker, Asset_Type, Exchange}."""
    result = {}
    if not path.exists():
        return result
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            result[row["Quicken_Name"]] = {
                "Ticker":     row.get("Ticker", ""),
                "Asset_Type": row.get("Asset_Type", ""),
                "Exchange":   row.get("Exchange", ""),
            }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quicken", help="Path to Quicken archive CSV")
    args = parser.parse_args()

    quicken_path = Path(args.quicken) if args.quicken else find_latest_quicken()
    name_map_path = Path(__file__).parent / "name_map.csv"

    existing = load_existing(name_map_path)
    holdings = parse_quicken(quicken_path)

    new_names     = []
    removed_names = []
    needs_exchange = []
    out_rows = []

    current_names = {name for name, _ in holdings}
    for name in existing:
        if name not in current_names:
            removed_names.append(name)

    for name, ticker in holdings:
        auto_type, auto_exchange = classify(ticker)

        if name in existing:
            entry = existing[name]
            # Preserve "etf" (can't be auto-detected); always apply rule-derived type otherwise
            asset_type = "etf" if entry["Asset_Type"] == "etf" else auto_type
            exchange   = entry["Exchange"] or auto_exchange
        else:
            new_names.append(name)
            asset_type = auto_type
            exchange   = auto_exchange
            if not exchange and auto_type != "bond":
                needs_exchange.append((name, ticker))

        out_rows.append({
            "Quicken_Name": name,
            "Ticker":       ticker,
            "Asset_Type":   asset_type.lower(),
            "Exchange":     exchange.lower(),
        })

    with open(name_map_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Quicken_Name", "Ticker", "Asset_Type", "Exchange"])
        w.writeheader()
        w.writerows(out_rows)

    print(f"Quicken file : {quicken_path.name}")
    print(f"Securities   : {len(out_rows)} written to {name_map_path.name}")

    if removed_names:
        print(f"\nRemoved ({len(removed_names)}) — no longer in portfolio:")
        for n in sorted(removed_names):
            print(f"  {n}")

    if new_names:
        print(f"\nNew ({len(new_names)}) — added to portfolio:")
        for n in sorted(new_names):
            print(f"  {n}")

    if needs_exchange:
        print(f"\nWARNING — {len(needs_exchange)} new security/securities need Exchange set manually in name_map.csv:")
        for name, ticker in needs_exchange:
            print(f"  {name} ({ticker})")


if __name__ == "__main__":
    main()
