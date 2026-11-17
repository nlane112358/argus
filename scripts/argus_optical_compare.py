#!/usr/bin/env python3
"""Collect and render a parcel-clipped Sentinel-2 optical scene pair."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("VSI_CACHE", "YES")
os.environ.setdefault("VSI_CACHE_SIZE", "67108864")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.vrt,.json")

from python.stac_client import DEFAULT_STAC_ENDPOINT, STACClient
from python.visualizer import generate_optical_products
from python.vrt_builder import VRTBuilder


BASELINE_WINDOW = "2020-09-01T00:00:00Z/2020-12-31T23:59:59Z"


def current_window():
    now = datetime.now(timezone.utc)
    start_year = now.year if now.month > 6 else now.year - 1
    return f"{start_year}-01-01T00:00:00Z/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def scene_metadata(item):
    properties = item.get("properties", {})
    return {
        "id": item.get("id", "unknown"),
        "acquired": properties.get("datetime", ""),
        "platform": properties.get("platform") or properties.get("constellation") or "Sentinel-2",
        "cloud_cover": properties.get("eo:cloud_cover"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geojson", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stac-endpoint", default=DEFAULT_STAC_ENDPOINT)
    args = parser.parse_args()

    try:
        os.makedirs(args.output_dir, exist_ok=True)
        client = STACClient(endpoint=args.stac_endpoint)
        bbox = client.extract_wgs84_bbox(args.geojson)
        baseline_scenes, current_scenes = client.search_bi_temporal(
            bbox,
            BASELINE_WINDOW,
            current_window(),
            max_cloud_cover=20.0,
        )
        if not baseline_scenes:
            raise RuntimeError("No Sentinel-2 scene found for the 2020 baseline window with cloud cover below 20%.")
        if not current_scenes:
            raise RuntimeError("No recent Sentinel-2 scene found with cloud cover below 20%.")

        baseline = baseline_scenes[0]
        current = current_scenes[0]
        base_assets = client.extract_band_urls(baseline)
        current_assets = client.extract_band_urls(current)
        required = ("red", "green", "blue", "nir")
        if any(key not in base_assets or key not in current_assets for key in required):
            raise RuntimeError("Selected Sentinel-2 scenes do not include all four 10m optical bands.")

        baseline_vrt = os.path.join(args.output_dir, "baseline.vrt")
        current_vrt = os.path.join(args.output_dir, "current.vrt")
        VRTBuilder.create_multiband_vrt(
            baseline_vrt,
            [base_assets["red"], base_assets["green"], base_assets["blue"], base_assets["nir"]],
        )
        VRTBuilder.create_multiband_vrt(
            current_vrt,
            [current_assets["red"], current_assets["green"], current_assets["blue"], current_assets["nir"]],
        )
        products = generate_optical_products(
            args.geojson,
            baseline_vrt,
            current_vrt,
            args.output_dir,
            red_band=1,
            green_band=2,
            blue_band=3,
            nir_band=4,
        )

        metadata = {
            "sensor": "Sentinel-2 L2A",
            "baseline": scene_metadata(baseline),
            "current": scene_metadata(current),
            "image_coordinates": products["image_coordinates"],
            "difference_note": "Current true-color image with a red/orange overlay where NDVI fell by at least 0.10.",
            "spatial_resolution_m": 10,
        }
        with open(os.path.join(args.output_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f)
        print(json.dumps({"ok": True}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
