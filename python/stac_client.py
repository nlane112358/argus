#!/usr/bin/env python3
"""
STAC (SpatioTemporal Asset Catalog) Client for Argus
Queries Sentinel-2 L2A Cloud-Optimized GeoTIFFs (COGs) for bi-temporal EUDR audits.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from osgeo import ogr, osr


DEFAULT_STAC_ENDPOINT = "https://earth-search.aws.element84.com/v1"
COLLECTION_SENTINEL2 = "sentinel-2-l2a"


class STACClient:
    def __init__(self, endpoint: str = DEFAULT_STAC_ENDPOINT, timeout: int = 15):
        self.endpoint = endpoint.rstrip("/")
        self.search_url = f"{self.endpoint}/search"
        self.timeout = timeout

    @staticmethod
    def extract_wgs84_bbox(vector_path: str) -> Tuple[float, float, float, float]:
        """
        Reads any vector file (GeoJSON, Shapefile, etc.) and returns its bounding box
        in WGS84 (EPSG:4326) coordinates: (min_lon, min_lat, max_lon, max_lat).
        """
        ds = ogr.Open(vector_path)
        if not ds:
            raise FileNotFoundError(f"Could not open vector file: {vector_path}")

        layer = ds.GetLayer(0)
        layer_srs = layer.GetSpatialRef()

        wgs84_srs = osr.SpatialReference()
        wgs84_srs.ImportFromEPSG(4326)
        wgs84_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        transform = None
        if layer_srs and not layer_srs.IsSame(wgs84_srs):
            transform = osr.CoordinateTransformation(layer_srs, wgs84_srs)

        layer.ResetReading()
        min_x, max_x = float("inf"), float("-inf")
        min_y, max_y = float("inf"), float("-inf")
        feature_count = 0

        for feature in layer:
            geom = feature.GetGeometryRef()
            if geom:
                feature_count += 1
                g_clone = geom.Clone()
                if transform:
                    g_clone.Transform(transform)
                env = g_clone.GetEnvelope()  # (minX, maxX, minY, maxY)
                min_x = min(min_x, env[0])
                max_x = max(max_x, env[1])
                min_y = min(min_y, env[2])
                max_y = max(max_y, env[3])

        ds = None
        if feature_count == 0:
            raise ValueError(f"No valid features found in vector file: {vector_path}")

        return (min_x, min_y, max_x, max_y)

    def search_scenes(
        self,
        bbox: Tuple[float, float, float, float],
        datetime_range: str,
        max_cloud_cover: float = 20.0,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Queries the STAC API for Sentinel-2 scenes overlapping bbox within datetime_range,
        sorted by cloud cover ascending.
        """
        payload = {
            "collections": [COLLECTION_SENTINEL2],
            "bbox": list(bbox),
            "datetime": datetime_range,
            "query": {
                "eo:cloud_cover": {"lt": max_cloud_cover}
            },
            "sortby": [
                {"field": "properties.eo:cloud_cover", "direction": "asc"}
            ],
            "limit": limit
        }

        req = urllib.request.Request(
            self.search_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Argus-ESG-Auditor/2.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("features", [])
        except urllib.error.URLError as e:
            raise ConnectionError(f"STAC search request failed to {self.search_url}: {e}")

    @staticmethod
    def extract_band_urls(stac_item: Dict) -> Dict[str, str]:
        """
        Extracts Red (B04) and NIR (B08) Cloud-Optimized GeoTIFF URLs from a STAC Item.
        """
        assets = stac_item.get("assets", {})
        band_map = {}

        # Look for Red band (B04 / red)
        for key in ["red", "B04", "b04"]:
            if key in assets and "href" in assets[key]:
                band_map["red"] = assets[key]["href"]
                break

        # Look for NIR band (B08 / nir)
        for key in ["nir", "B08", "b08", "nir08"]:
            if key in assets and "href" in assets[key]:
                band_map["nir"] = assets[key]["href"]
                break

        # Optional Scene Classification Layer (SCL)
        for key in ["scl", "SCL", "visual"]:
            if key in assets and "href" in assets[key]:
                band_map[key.lower()] = assets[key]["href"]
                break

        if "red" not in band_map or "nir" not in band_map:
            raise KeyError(
                f"STAC item '{stac_item.get('id', 'unknown')}' is missing required Red or NIR band assets."
            )

        return band_map
