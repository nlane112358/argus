#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "[*] Step 1: Building project..."
make clean
make

echo "[*] Step 2: Generating synthetic geospatial test fixtures..."
python3 tests/create_fixtures.py

echo "[*] Step 3: Running positive audit test (WGS84 vector against UTM raster)..."
./esg_auditor tests/fixtures/test_farm_wgs84.geojson tests/fixtures/test_raster_utm.tif

echo "[*] Step 4: Running negative test (Out-of-bounds polygon)..."
if ./esg_auditor tests/fixtures/test_outside.geojson tests/fixtures/test_raster_utm.tif 2>/dev/null; then
    echo "[!] Error: Negative test was expected to fail but passed!"
    exit 1
else
    echo "[+] Negative test caught out-of-bounds error gracefully as expected."
fi

echo "========================================"
echo "[+] All Phase 1 tests passed successfully!"
echo "========================================"
