#!/usr/bin/env python3
"""
Build a starter holdings_meta.csv from the latest portfolio export.

Filters out $0 positions, 529 accounts, Cash rows, Watch List, Indexes,
and account-header rows.

Output columns:
  account, holding_name, market_value, current_pct, asset_class,
  sub_class, region, sector, target_pct, notes

Manually fill in asset_class / sub_class / region / sector / target_pct.
current_pct is computed automatically.

Usage:
  python3 py/build_holdings_meta.py --out <path> --quicken-archive <dir>
  python3 py/build_holdings_meta.py --out <path> --quicken <file>
"""

import argparse
import csv
import re
import sys
from pathlib import Path

MIN_MARKET_VALUE = 50.0

SKIP_ACCOUNTS_EXACT = {
    "Danielle 529 NY", "Ryan 529 NY", "RyanDonna529", "DanielleDonna529",
    "Watch List  (add) (edit)", "Indexes", "Bear Profit Sharing old",
}
SKIP_ACCOUNTS_CONTAINS = ["PCFN"]
SKIP_HOLDING_PATTERNS  = [re.compile(r"^cash$", re.IGNORECASE)]


def account_skipped(name):
    if name in SKIP_ACCOUNTS_EXACT:
        return True
    nl = name.lower()
    return any(s.lower() in nl for s in SKIP_ACCOUNTS_CONTAINS)


def parse_money(s):
    if s is None:
        return 0.0
    s = s.strip().strip('"').replace(",", "").rstrip("*")
    if not s or s == "*":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def find_latest_quicken(archive):
    csvs = sorted(Path(archive).glob("portfolio_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    if not csvs:
        sys.exit(f"ERROR: No portfolio_YYYY-MM-DD.csv found in {archive}")
    return csvs[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",             required=True, help="Output path for holdings_meta.csv")
    parser.add_argument("--quicken-archive", help="Directory containing portfolio_YYYY-MM-DD.csv files")
    parser.add_argument("--quicken",         help="Explicit path to Quicken CSV (overrides --quicken-archive)")
    args = parser.parse_args()

    if args.quicken:
        src = Path(args.quicken)
    elif args.quicken_archive:
        src = find_latest_quicken(args.quicken_archive)
    else:
        sys.exit("ERROR: provide --quicken or --quicken-archive")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = list(csv.reader(src.open(encoding="latin-1", newline="")))

    in_holdings = False
    current_account = None
    out_rows = []

    for raw in rows:
        while len(raw) < 6:
            raw.append("")
        col0, col1, col2, col3 = raw[0], raw[1], raw[2], raw[3]

        if col1.strip().strip('"') == "Holdings":
            in_holdings = True
            continue
        if col0.strip().strip('"').startswith("Totals:"):
            break
        if not in_holdings:
            continue

        name = col0.strip().strip('"')
        if not name:
            continue

        is_account_header = (col2.strip() == "" and col1.strip() == "")
        if is_account_header:
            current_account = name
            continue

        if current_account and account_skipped(current_account):
            continue
        if any(p.search(name) for p in SKIP_HOLDING_PATTERNS):
            continue

        mv = parse_money(col3)
        if mv < MIN_MARKET_VALUE:
            continue

        out_rows.append({"account": current_account or "", "holding_name": name, "market_value": f"{mv:.2f}"})

    total = sum(float(r["market_value"]) for r in out_rows)
    for r in out_rows:
        r["current_pct"] = f"{float(r['market_value']) / total * 100:.4f}" if total else "0"

    fields = ["account", "holding_name", "market_value", "current_pct",
              "asset_class", "sub_class", "region", "sector", "target_pct", "notes"]

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in fields})

    print(f"Quicken file : {src.name}")
    print(f"Wrote        : {len(out_rows)} rows → {out}")
    print(f"Total value  : ${total:,.2f}")
    accounts = sorted({r["account"] for r in out_rows})
    for a in accounts:
        n = sum(1 for r in out_rows if r["account"] == a)
        s = sum(float(r["market_value"]) for r in out_rows if r["account"] == a)
        print(f"  {a:50s} {n:3d} holdings  ${s:>14,.2f}")


if __name__ == "__main__":
    main()
