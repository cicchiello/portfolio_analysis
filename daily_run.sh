#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO/.venv/bin/python3"

echo "=== portfolio-analysis daily run ==="
echo "$(date)"
echo

# Step 1: generate name_map.csv from latest Quicken export
echo "--- Step 1: generate name_map ---"
"$VENV" "$REPO/analyze/generate_name_map.py"
echo

# Step 2: download all Morningstar profiles
echo "--- Step 2: download profiles ---"
"$VENV" "$REPO/download/download_profiles.py"
echo

# Step 3: parse downloaded HTML → fund_sectors.csv
echo "--- Step 3: parse profiles ---"
"$VENV" "$REPO/parse/parse_fund_profiles.py" --force
echo

# Step 4: join Quicken positions with sector data → portfolio_with_sectors.csv
echo "--- Step 4: join ---"
"$VENV" "$REPO/analyze/join_portfolio.py"
echo

echo "Done. $(date)"
