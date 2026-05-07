#!/usr/bin/env python3
"""
Join Quicken portfolio positions with Morningstar sector data.

Usage:
  python3 py/join_portfolio.py --name-map <path> --fund-sectors <path> --out <path> --quicken-archive <dir>
  python3 py/join_portfolio.py --name-map <path> --fund-sectors <path> --out <path> --quicken <file>
"""

import csv
import sys
import argparse
from pathlib import Path

SECTOR_COLS = [
    "Basic_Materials", "Consumer_Cyclical", "Financial_Services", "Real_Estate",
    "Communication_Services", "Energy", "Industrials", "Technology",
    "Consumer_Defensive", "Healthcare", "Utilities", "Not_Classified",
]

SKIP_NAMES = {"Cash"}


def find_latest_quicken(archive):
    csvs = sorted(Path(archive).glob("portfolio_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    if not csvs:
        sys.exit(f"ERROR: No portfolio_YYYY-MM-DD.csv found in {archive}")
    return csvs[-1]


def load_sectors(path):
    sectors = {}
    p = Path(path)
    if not p.exists():
        return sectors
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
            result[row["Quicken_Name"]] = {
                "Ticker":     row["Ticker"],
                "Asset_Type": row.get("Asset_Type", ""),
            }
    return result


_KNOWN_IRA_ACCOUNTS = {
    # Accounts whose names don't yet reflect their IRA status — remove once renamed in Quicken
    "American Funds",
    "Primerica",
}

def derive_account_type(account):
    a = account or ""
    if a in _KNOWN_IRA_ACCOUNTS:
        return "IRA"
    if "Roth" in a:
        return "Roth"
    if "Inherited IRA" in a:
        return "I-IRA"
    if "HSA" in a.upper():
        return "HSA"
    if "IRA" in a or "401K" in a.upper():
        return "IRA"
    return "Taxable"


def derive_asset_class(asset_type, has_sectors):
    if asset_type == "stock":
        return "EQ"
    if asset_type == "bond":
        return "FI"
    return "EQ-Fund" if has_sectors else "FI-Fund"


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

        if gainls is None and mktval is not None and costb is not None:
            gainls = round(mktval - costb, 2)

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
    parser.add_argument("--name-map",        required=True, help="Path to name_map.csv")
    parser.add_argument("--fund-sectors",    required=True, help="Path to fund_sectors.csv")
    parser.add_argument("--out",             required=True, help="Output path for portfolio_with_sectors CSV")
    parser.add_argument("--quicken-archive", help="Directory containing portfolio_YYYY-MM-DD.csv files")
    parser.add_argument("--quicken",         help="Explicit path to Quicken CSV (overrides --quicken-archive)")
    args = parser.parse_args()

    if args.quicken:
        quicken_path = Path(args.quicken)
    elif args.quicken_archive:
        quicken_path = find_latest_quicken(args.quicken_archive)
    else:
        sys.exit("ERROR: provide --quicken or --quicken-archive")

    name_map_path = Path(args.name_map)
    if not name_map_path.exists():
        sys.exit(f"ERROR: {name_map_path} not found")

    sectors  = load_sectors(args.fund_sectors)
    name_map = load_name_map(name_map_path)

    print(f"Quicken file : {quicken_path.name}")
    print(f"Sector keys  : {len(sectors)}")
    positions = parse_quicken(quicken_path)
    print(f"Positions    : {len(positions)}")

    out_rows  = []
    unmatched = []

    for pos in positions:
        qname   = pos["Name"]
        mapping = name_map.get(qname)

        ticker      = mapping["Ticker"]     if mapping else pos.get("Ticker", "")
        asset_type  = mapping["Asset_Type"] if mapping else ""
        sector_data = sectors.get(ticker) if ticker else None

        row = {**pos, "Ticker": ticker,
               "Asset_Class":   derive_asset_class(asset_type, bool(sector_data)),
               "Account_Type":  derive_account_type(pos["Account"])}
        if sector_data:
            row.update(sector_data)
        else:
            row.update({c: "" for c in SECTOR_COLS})
            if qname not in SKIP_NAMES:
                unmatched.append(qname)

        out_rows.append(row)

    # Build market-value-weighted total sector row (only rows with sector data contribute)
    sector_weighted = {c: 0.0 for c in SECTOR_COLS}
    total_mv        = 0.0
    total_cb        = 0.0
    total_gl        = 0.0
    sector_mv       = 0.0  # market value of holdings with sector data

    for row in out_rows:
        mv = row.get("Market_Value") or 0.0
        total_mv += mv
        total_cb += row.get("Cost_Basis") or 0.0
        total_gl += row.get("Gain_Loss")  or 0.0
        if row.get(SECTOR_COLS[0], "") != "":
            sector_mv += mv
            for c in SECTOR_COLS:
                sector_weighted[c] += mv * float(row.get(c) or 0.0)

    total_row = {
        "Account":      "",
        "Name":         "TOTAL",
        "Ticker":       "",
        "Asset_Class":  "",
        "Account_Type": "",
        "Price":        "",
        "Shares":       "",
        "Market_Value": round(total_mv, 2),
        "Cost_Basis":   round(total_cb, 2),
        "Gain_Loss":    round(total_gl, 2),
    }
    for c in SECTOR_COLS:
        total_row[c] = round(sector_weighted[c] / sector_mv, 4) if sector_mv else ""

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Account", "Name", "Ticker", "Price", "Shares",
        "Market_Value", "Cost_Basis", "Gain_Loss",
    ] + SECTOR_COLS + ["Asset_Class", "Account_Type"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
        w.writerow(total_row)

    matched = len(out_rows) - len(unmatched)
    print(f"Matched      : {matched}/{len(out_rows)} positions have sector data")
    print(f"Written      : {out_path}")

    if unmatched:
        print(f"\nNo sector data ({len(set(unmatched))} unique) — profile not yet downloaded or no sector data on Morningstar page:")
        for n in sorted(set(unmatched)):
            print(f"  {n}")


if __name__ == "__main__":
    main()
