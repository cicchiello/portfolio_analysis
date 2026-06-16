#!/usr/bin/env python3
"""
Generate name_map.csv from the latest Quicken export.

This script treats name_map.csv as the current portfolio map and also maintains
an append/update history map so manually learned ticker metadata is not lost when
Quicken display names change.

Exchange/asset metadata is resolved in this order:
  1. Existing name_map.csv exact Quicken_Name match
  2. Existing name_map.csv Ticker match
  3. History map Ticker match
  4. Ticker classification rules
  5. Optional Nasdaq Trader symbol-directory lookup for ordinary stocks

Exchange codes are Morningstar URL path codes used by download_profiles.py:
  xnas  Nasdaq
  xnys  NYSE
  arcx  NYSE Arca
  xase  NYSE American
  bats  Cboe BZX
  pinx  OTC / Pink Sheets

Usage:
  python3 py/generate_name_map.py --name-map <path> --quicken-archive <dir>
  python3 py/generate_name_map.py --name-map <path> --quicken <file>

Optional:
  --history-map <path>       default: sibling file named name_map_history.csv
  --no-symbol-lookup         disable Nasdaq Trader lookup for new stock tickers
"""

import argparse
import csv
import io
import sys
import urllib.request
from pathlib import Path


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

# Nasdaq Trader "Exchange" code -> Morningstar URL exchange code.
OTHER_LISTED_EXCHANGE_MAP = {
    "A": "xase",  # NYSE American
    "N": "xnys",  # New York Stock Exchange
    "P": "arcx",  # NYSE Arca
    "Z": "bats",  # Cboe BZX
    "V": "iarcx", # Investors Exchange; uncommon, may need manual correction
}

FIELDNAMES = ["Quicken_Name", "Ticker", "Asset_Type", "Exchange"]


def norm_ticker(ticker):
    return (ticker or "").strip().upper()


def norm_exchange(exchange):
    return (exchange or "").strip().lower()


def norm_asset_type(asset_type):
    return (asset_type or "").strip().lower()


def classify(ticker):
    """Return (asset_type, exchange) using local deterministic rules only."""
    t = norm_ticker(ticker)
    if len(t) == 5 and t.endswith("X"):
        return "fund", "xnas"
    if t.startswith("SPU"):
        return "pfund", "pfund"
    if t and t[0].isdigit():
        return "bond", ""
    if t.endswith("ZF"):
        return "stock", "pinx"
    return "stock", ""


def find_latest_quicken(archive):
    csvs = sorted(Path(archive).glob("portfolio_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    if not csvs:
        sys.exit(f"ERROR: No portfolio_YYYY-MM-DD.csv found in {archive}")
    return csvs[-1]


def parse_num(s):
    try:
        return float(str(s).strip().replace(",", "").replace("*", "").replace(" A", ""))
    except (ValueError, AttributeError):
        return None


def parse_quicken(path):
    """Return ordered list of (quicken_name, ticker), unique by name."""
    stop = {"Watch List  (add) (edit)", "Indexes", "Totals:", "PCFN"}
    holdings = []
    seen_names = set()

    with open(path, newline="", encoding="latin-1") as f:
        rows = list(csv.reader(f))

    data_start = next((i + 1 for i, r in enumerate(rows) if r and r[0] == "Name"), 0)

    for row in rows[data_start:]:
        if not row or all(c.strip() == "" for c in row):
            continue
        name = row[0].strip().strip('"')
        if not name:
            continue
        if name in stop or name.startswith("Watch List"):
            break

        ticker = norm_ticker(row[1] if len(row) > 1 else "")
        price = parse_num(row[2] if len(row) > 2 else "")
        shares = parse_num((row[3] if len(row) > 3 else "").replace(" A", ""))

        if price is None and shares is None:
            continue  # account header row
        if name == "Cash":
            continue
        if name not in seen_names:
            seen_names.add(name)
            holdings.append((name, ticker))

    return holdings


def load_rows(path):
    """Load mapping rows from a CSV path. Missing file returns []."""
    p = Path(path)
    if not p.exists():
        return []

    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("Quicken_Name") or "").strip()
            ticker = norm_ticker(row.get("Ticker"))
            asset_type = norm_asset_type(row.get("Asset_Type"))
            exchange = norm_exchange(row.get("Exchange"))
            if not name and not ticker:
                continue
            rows.append({
                "Quicken_Name": name,
                "Ticker": ticker,
                "Asset_Type": asset_type,
                "Exchange": exchange,
            })
    return rows


def index_by_name(rows):
    return {r["Quicken_Name"]: r for r in rows if r.get("Quicken_Name")}


def index_by_ticker(rows):
    """Return ticker -> best row, preferring rows that have an exchange."""
    result = {}
    for r in rows:
        t = norm_ticker(r.get("Ticker"))
        if not t:
            continue
        old = result.get(t)
        if old is None or (not old.get("Exchange") and r.get("Exchange")):
            result[t] = r
    return result


def fetch_text(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 openclaw-symbol-lookup/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_symbol_directory(enabled=True):
    """Return ticker -> Morningstar exchange code from Nasdaq Trader files."""
    if not enabled:
        return {}

    mapping = {}
    errors = []

    try:
        text = fetch_text(NASDAQ_LISTED_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        for row in reader:
            symbol = norm_ticker(row.get("Symbol"))
            if not symbol or symbol == "FILE CREATION TIME":
                continue
            if (row.get("Test Issue") or "").upper() == "Y":
                continue
            mapping[symbol] = "xnas"
    except Exception as e:  # network is nice-to-have; do not fail the pipeline
        errors.append(f"nasdaqlisted lookup failed: {e}")

    try:
        text = fetch_text(OTHER_LISTED_URL)
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        for row in reader:
            symbol = norm_ticker(row.get("ACT Symbol"))
            if not symbol or symbol == "FILE CREATION TIME":
                continue
            if (row.get("Test Issue") or "").upper() == "Y":
                continue
            exchange_code = (row.get("Exchange") or "").strip().upper()
            ms_exchange = OTHER_LISTED_EXCHANGE_MAP.get(exchange_code)
            if ms_exchange:
                mapping[symbol] = ms_exchange
    except Exception as e:
        errors.append(f"otherlisted lookup failed: {e}")

    for err in errors:
        print(f"WARNING — {err}")

    return mapping


def choose_metadata(name, ticker, existing_by_name, existing_by_ticker, history_by_ticker, symbol_dir):
    """Return (asset_type, exchange, source)."""
    auto_type, auto_exchange = classify(ticker)
    t = norm_ticker(ticker)

    candidates = []
    if name in existing_by_name:
        candidates.append(("existing-name", existing_by_name[name]))
    if t in existing_by_ticker:
        candidates.append(("existing-ticker", existing_by_ticker[t]))
    if t in history_by_ticker:
        candidates.append(("history-ticker", history_by_ticker[t]))

    for source, entry in candidates:
        # Preserve manual ETF classification. Otherwise let ticker rules identify funds/bonds.
        existing_type = norm_asset_type(entry.get("Asset_Type"))
        asset_type = "etf" if existing_type == "etf" else (auto_type or existing_type)
        exchange = norm_exchange(entry.get("Exchange")) or auto_exchange
        if exchange or asset_type == "bond":
            return asset_type, exchange, source

    if auto_exchange or auto_type != "stock":
        return auto_type, auto_exchange, "rule"

    if t in symbol_dir:
        return "stock", symbol_dir[t], "symbol-dir"

    return auto_type, "", "unresolved"


def write_rows(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def merge_history(existing_history_rows, current_rows):
    """Return history rows keyed by ticker, updated with current non-blank metadata."""
    merged = index_by_ticker(existing_history_rows)
    for row in current_rows:
        t = norm_ticker(row.get("Ticker"))
        if not t:
            continue
        old = merged.get(t, {})
        # Use the newest name, but do not replace good metadata with blanks.
        merged[t] = {
            "Quicken_Name": row.get("Quicken_Name") or old.get("Quicken_Name", ""),
            "Ticker": t,
            "Asset_Type": norm_asset_type(row.get("Asset_Type")) or norm_asset_type(old.get("Asset_Type")),
            "Exchange": norm_exchange(row.get("Exchange")) or norm_exchange(old.get("Exchange")),
        }
    return [merged[t] for t in sorted(merged)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name-map", required=True, help="Path to name_map.csv (read existing, write new)")
    parser.add_argument("--history-map", help="Path to persistent ticker history CSV; default: name_map_history.csv beside name_map")
    parser.add_argument("--quicken-archive", help="Directory containing portfolio_YYYY-MM-DD.csv files")
    parser.add_argument("--quicken", help="Explicit path to Quicken CSV (overrides --quicken-archive)")
    parser.add_argument("--no-symbol-lookup", action="store_true", help="Do not query Nasdaq Trader symbol directories")
    args = parser.parse_args()

    if args.quicken:
        quicken_path = Path(args.quicken)
    elif args.quicken_archive:
        quicken_path = find_latest_quicken(args.quicken_archive)
    else:
        sys.exit("ERROR: provide --quicken or --quicken-archive")

    name_map_path = Path(args.name_map)
    history_map_path = Path(args.history_map) if args.history_map else name_map_path.with_name("name_map_history.csv")

    existing_rows = load_rows(name_map_path)
    history_rows = load_rows(history_map_path)
    holdings = parse_quicken(quicken_path)

    existing_by_name = index_by_name(existing_rows)
    existing_by_ticker = index_by_ticker(existing_rows)
    history_by_ticker = index_by_ticker(history_rows)
    symbol_dir = load_symbol_directory(enabled=not args.no_symbol_lookup)

    new_names = []
    removed_names = []
    needs_exchange = []
    recovered_by_ticker = []
    resolved_by_symbol_dir = []
    out_rows = []

    current_names = {name for name, _ in holdings}
    for name in existing_by_name:
        if name not in current_names:
            removed_names.append(name)

    for name, ticker in holdings:
        asset_type, exchange, source = choose_metadata(
            name,
            ticker,
            existing_by_name,
            existing_by_ticker,
            history_by_ticker,
            symbol_dir,
        )

        if name not in existing_by_name:
            new_names.append(name)
        if source in {"existing-ticker", "history-ticker"} and name not in existing_by_name:
            recovered_by_ticker.append((name, ticker, exchange, source))
        if source == "symbol-dir":
            resolved_by_symbol_dir.append((name, ticker, exchange))
        if not exchange and asset_type not in {"bond"}:
            needs_exchange.append((name, ticker, asset_type))

        out_rows.append({
            "Quicken_Name": name,
            "Ticker": ticker,
            "Asset_Type": asset_type.lower(),
            "Exchange": exchange.lower(),
        })

    write_rows(name_map_path, out_rows)
    write_rows(history_map_path, merge_history(history_rows + existing_rows, out_rows))

    print(f"Quicken file : {quicken_path.name}")
    print(f"Securities   : {len(out_rows)} written to {name_map_path}")
    print(f"History map  : {history_map_path}")

    if removed_names:
        print(f"\nRemoved ({len(removed_names)}) — no longer in portfolio:")
        for n in sorted(removed_names):
            print(f"  {n}")

    if new_names:
        print(f"\nNew ({len(new_names)}) — added to portfolio:")
        for n in sorted(new_names):
            print(f"  {n}")

    if recovered_by_ticker:
        print(f"\nRecovered by ticker/history ({len(recovered_by_ticker)}):")
        for name, ticker, exchange, source in sorted(recovered_by_ticker):
            print(f"  {name} ({ticker}) -> {exchange} [{source}]")

    if resolved_by_symbol_dir:
        print(f"\nResolved from Nasdaq Trader symbol directory ({len(resolved_by_symbol_dir)}):")
        for name, ticker, exchange in sorted(resolved_by_symbol_dir):
            print(f"  {name} ({ticker}) -> {exchange}")

    if needs_exchange:
        print(f"\nWARNING — {len(needs_exchange)} security/securities still need Exchange set manually in name_map.csv:")
        for name, ticker, asset_type in needs_exchange:
            print(f"  {name} ({ticker}) [{asset_type}]")


if __name__ == "__main__":
    main()
