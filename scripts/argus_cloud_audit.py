#!/usr/bin/env python3
"""
Argus Cloud Audit CLI
End-to-end autonomous EUDR auditor:
Ingests a single farm polygon, queries Sentinel-2 STAC catalogs for baseline (2020) and
current scenes, constructs zero-copy Cloud-Optimized GeoTIFF VRT streams, and runs the
high-performance C++ audit engine.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from python.stac_client import STACClient, DEFAULT_STAC_ENDPOINT
from python.vrt_builder import VRTBuilder


DEFAULT_BASELINE_WINDOW = "2020-09-01T00:00:00Z/2020-12-31T23:59:59Z"


def get_default_current_window() -> str:
    now = datetime.now(timezone.utc)
    # Default to past 180 days up to current day
    start_year = now.year if now.month > 6 else now.year - 1
    return f"{start_year}-01-01T00:00:00Z/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Argus Autonomous Cloud EUDR Satellite Auditor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("polygon", help="Path to input farm/asset polygon (GeoJSON, Shapefile, etc.)")
    parser.add_argument(
        "--baseline-window",
        default=DEFAULT_BASELINE_WINDOW,
        help="STAC ISO8601 datetime search range for the 2020 EUDR cutoff baseline",
    )
    parser.add_argument(
        "--current-window",
        default=get_default_current_window(),
        help="STAC ISO8601 datetime search range for current epoch imagery",
    )
    parser.add_argument(
        "--max-cloud-cover",
        type=float,
        default=20.0,
        help="Maximum allowable cloud cover percentage when selecting scenes",
    )
    parser.add_argument(
        "--stac-endpoint",
        default=DEFAULT_STAC_ENDPOINT,
        help="SpatioTemporal Asset Catalog (STAC) API search endpoint",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=2.0,
        help="Maximum allowable post-2020 canopy loss percentage before violation is flagged",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON for automated ERP integration",
    )
    parser.add_argument(
        "--output-vrt-dir",
        default=None,
        help="Directory to save generated VRT descriptor files (defaults to temporary directory)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in offline mock mode using synthetic local test fixtures",
    )
    parser.add_argument(
        "--mock-violation",
        action="store_true",
        help="In mock mode, select the violation raster for testing failure detection",
    )
    return parser.parse_args()


def run_mock_audit(args, polygon_path: str, vrt_dir: str):
    """
    Mock cloud ingestion for offline environments and CI test suites.
    """
    fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
    base_tif = fixtures_dir / "baseline_2020.tif"
    curr_tif = fixtures_dir / ("current_violation_2026.tif" if args.mock_violation else "current_compliant_2026.tif")

    if not base_tif.exists() or not curr_tif.exists():
        subprocess.run([sys.executable, str(PROJECT_ROOT / "tests" / "create_fixtures.py")], check=True)

    # Build local multi-band VRTs demonstrating the VRT builder pipeline
    baseline_vrt = os.path.join(vrt_dir, "baseline_2020_mock.vrt")
    current_vrt = os.path.join(vrt_dir, "current_mock.vrt")

    # In synthetic fixtures, Band 3 is Red and Band 4 is NIR
    # We pass the full 4-band TIFF directly to the VRT builder or auditor
    return execute_auditor(args, polygon_path, str(base_tif), str(curr_tif), red_band=3, nir_band=4)


def execute_auditor(args, polygon_path: str, baseline_path: str, current_path: str, red_band: int = 1, nir_band: int = 2):
    binary_path = PROJECT_ROOT / "esg_auditor"
    if not binary_path.exists():
        # Build binary if not built
        subprocess.run(["make", "-C", str(PROJECT_ROOT)], check=True)

    cmd = [
        str(binary_path),
        polygon_path,
        baseline_path,
        current_path,
        "--red", str(red_band),
        "--nir", str(nir_band),
        "--tolerance", str(args.tolerance),
    ]
    if args.json:
        cmd.append("--json")

    result = subprocess.run(cmd)
    return result.returncode


def main():
    args = parse_args()
    polygon_path = os.path.abspath(args.polygon)
    if not os.path.exists(polygon_path):
        print(f"[!] Error: Vector polygon file not found: {polygon_path}", file=sys.stderr)
        sys.exit(1)

    vrt_dir = args.output_vrt_dir or tempfile.mkdtemp(prefix="argus_vrt_")

    if args.mock:
        ret = run_mock_audit(args, polygon_path, vrt_dir)
        sys.exit(ret)

    # Live Cloud Ingestion Mode
    try:
        client = STACClient(endpoint=args.stac_endpoint)
        if not args.json:
            print(f"[*] Extracting polygon envelope for: {polygon_path}")
        bbox = client.extract_wgs84_bbox(polygon_path)
        if not args.json:
            print(f"[+] Bounding Box (WGS84): [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]")

        # 1. Query Baseline (2020 Cutoff)
        if not args.json:
            print(f"[*] Querying STAC for baseline epoch: {args.baseline_window} ...")
        base_scenes = client.search_scenes(bbox, args.baseline_window, max_cloud_cover=args.max_cloud_cover)
        if not base_scenes:
            raise RuntimeError(
                f"No Sentinel-2 scenes with cloud cover < {args.max_cloud_cover}% found for baseline window: {args.baseline_window}"
            )
        best_base_scene = base_scenes[0]
        base_urls = client.extract_band_urls(best_base_scene)
        base_id = best_base_scene.get("id", "baseline_scene")
        base_date = best_base_scene.get("properties", {}).get("datetime", "2020")
        if not args.json:
            print(f"[+] Selected Baseline Scene: {base_id} ({base_date})")

        # 2. Query Current Epoch
        if not args.json:
            print(f"[*] Querying STAC for current epoch: {args.current_window} ...")
        curr_scenes = client.search_scenes(bbox, args.current_window, max_cloud_cover=args.max_cloud_cover)
        if not curr_scenes:
            raise RuntimeError(
                f"No Sentinel-2 scenes with cloud cover < {args.max_cloud_cover}% found for current window: {args.current_window}"
            )
        best_curr_scene = curr_scenes[0]
        curr_urls = client.extract_band_urls(best_curr_scene)
        curr_id = best_curr_scene.get("id", "current_scene")
        curr_date = best_curr_scene.get("properties", {}).get("datetime", "recent")
        if not args.json:
            print(f"[+] Selected Current Scene: {curr_id} ({curr_date})")

        # 3. Build VRTs for zero-copy streaming
        baseline_vrt = os.path.join(vrt_dir, f"{base_id}_bands.vrt")
        current_vrt = os.path.join(vrt_dir, f"{curr_id}_bands.vrt")

        if not args.json:
            print("[*] Building zero-copy Cloud-Optimized GeoTIFF VRT streams...")
        VRTBuilder.create_multiband_vrt(baseline_vrt, [base_urls["red"], base_urls["nir"]])
        VRTBuilder.create_multiband_vrt(current_vrt, [curr_urls["red"], curr_urls["nir"]])

        # 4. Execute C++ core audit
        ret = execute_auditor(args, polygon_path, baseline_vrt, current_vrt, red_band=1, nir_band=2)
        sys.exit(ret)

    except ConnectionError as ce:
        print(f"[!] Network / STAC Connection Error: {ce}", file=sys.stderr)
        print("[*] Tip: Use --mock to test offline with synthetic fixtures.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
