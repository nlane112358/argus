#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "[*] Step 1: Building project with make..."
make clean
make

echo "[*] Step 2: Generating synthetic geospatial test fixtures..."
python3 tests/create_fixtures.py

echo "[*] Step 3: Running bi-temporal EUDR COMPLIANT test..."
./esg_auditor tests/fixtures/test_farm_wgs84.geojson tests/fixtures/baseline_2020.tif tests/fixtures/current_compliant_2026.tif

echo "[*] Step 4: Running bi-temporal EUDR VIOLATION test..."
set +e
./esg_auditor tests/fixtures/test_farm_wgs84.geojson tests/fixtures/baseline_2020.tif tests/fixtures/current_violation_2026.tif
VIOLATION_EXIT=$?
set -e
if [ "$VIOLATION_EXIT" -ne 2 ]; then
    echo "[!] Expected exit code 2 (Violation), got $VIOLATION_EXIT"
    exit 1
fi
echo "[+] Violation successfully flagged with exit code 2."

echo "[*] Step 5: Testing JSON output mode..."
./esg_auditor tests/fixtures/test_farm_wgs84.geojson tests/fixtures/baseline_2020.tif tests/fixtures/current_compliant_2026.tif --json | python3 -m json.tool > /dev/null
echo "[+] JSON output successfully validated."

echo "[*] Step 6: Testing single-epoch legacy fallback..."
set +e
./esg_auditor tests/fixtures/test_farm_wgs84.geojson tests/fixtures/baseline_2020.tif > /dev/null
LEGACY_EXIT=$?
set -e
if [ "$LEGACY_EXIT" -ne 0 ] && [ "$LEGACY_EXIT" -ne 2 ]; then
    echo "[!] Unexpected legacy exit code: $LEGACY_EXIT"
    exit 1
fi
echo "[+] Single-epoch legacy mode validated."

echo "[*] Step 7: Testing out-of-bounds negative test..."
set +e
./esg_auditor tests/fixtures/test_outside.geojson tests/fixtures/baseline_2020.tif tests/fixtures/current_compliant_2026.tif 2>/dev/null
OUTSIDE_EXIT=$?
set -e
if [ "$OUTSIDE_EXIT" -eq 0 ]; then
    echo "[!] Error: Negative test was expected to fail but passed!"
    exit 1
fi
echo "[+] Negative test caught out-of-bounds error gracefully."

echo "================================================="
echo "[+] ALL PHASE 2 TESTS PASSED SUCCESSFULLY! (6/6)"
echo "================================================="
