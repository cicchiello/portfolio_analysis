#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/pyvenv/bin/python3"

DATA_ROOT="${1:?Usage: analyze.sh <data-root> <quicken-archive>}"
QUICKEN_ARCHIVE="${2:?Usage: analyze.sh <data-root> <quicken-archive>}"

DATE="$(date +%Y%m%d)"
WORK_DIR="$DATA_ROOT/work_$DATE"
NAME_MAP="$DATA_ROOT/name_map.csv"
OUT="$DATA_ROOT/portfolio_with_sectors_$DATE.csv"

mkdir -p "$WORK_DIR"

echo "=== portfolio-analysis ==="
echo "$(date)"
echo "Data root : $DATA_ROOT"
echo "Work dir  : $WORK_DIR"
echo

echo "--- Step 1: generate name_map ---"
"$VENV" "$REPO/py/generate_name_map.py" \
    --name-map "$NAME_MAP" \
    --quicken-archive "$QUICKEN_ARCHIVE"
echo

echo "--- Step 2: download profiles ---"
"$VENV" "$REPO/py/download_profiles.py" \
    --name-map "$NAME_MAP" \
    --work-dir "$WORK_DIR"
echo

echo "--- Step 3: parse profiles ---"
"$VENV" "$REPO/py/parse_fund_profiles.py" \
    --work-dir "$WORK_DIR"
echo

echo "--- Step 4: join ---"
"$VENV" "$REPO/py/join_portfolio.py" \
    --name-map "$NAME_MAP" \
    --fund-sectors "$WORK_DIR/fund_sectors.csv" \
    --fund-prices "$WORK_DIR/fund_prices.csv" \
    --quicken-archive "$QUICKEN_ARCHIVE" \
    --out "$OUT"
echo

echo "Done. $(date)"
echo "Output: $OUT"
