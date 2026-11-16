#!/usr/bin/env python3
"""
Unit tests for STAC Cloud Ingestion and VRT Builder modules
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from osgeo import gdal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from python.stac_client import STACClient
from python.vrt_builder import VRTBuilder


class TestSTACModule(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
        self.geojson_path = self.fixtures_dir / "test_farm_wgs84.geojson"

    def test_extract_wgs84_bbox(self):
        self.assertTrue(self.geojson_path.exists())
        bbox = STACClient.extract_wgs84_bbox(str(self.geojson_path))
        self.assertEqual(len(bbox), 4)
        min_lon, min_lat, max_lon, max_lat = bbox
        self.assertLess(min_lon, max_lon)
        self.assertLess(min_lat, max_lat)
        # Check roughly within reasonable latitude/longitude bounds
        self.assertTrue(-180 <= min_lon <= 180)
        self.assertTrue(-90 <= min_lat <= 90)

    def test_extract_band_urls(self):
        sample_stac_item = {
            "id": "S2A_MSIL2A_20201215T140711_N0214_R110_T21KUB",
            "assets": {
                "red": {"href": "https://example.com/B04.tif"},
                "nir": {"href": "https://example.com/B08.tif"},
                "scl": {"href": "https://example.com/SCL.tif"},
            }
        }
        band_map = STACClient.extract_band_urls(sample_stac_item)
        self.assertIn("red", band_map)
        self.assertIn("nir", band_map)
        self.assertEqual(band_map["red"], "https://example.com/B04.tif")
        self.assertEqual(band_map["nir"], "https://example.com/B08.tif")

    def test_format_gdal_path(self):
        http_url = "https://sentinel-cogs.s3.amazonaws.com/B04.tif"
        self.assertEqual(VRTBuilder.format_gdal_path(http_url), f"/vsicurl/{http_url}")

        s3_url = "s3://sentinel-cogs/B04.tif"
        self.assertEqual(VRTBuilder.format_gdal_path(s3_url), "/vsis3/sentinel-cogs/B04.tif")

        local_path = "/var/data/B04.tif"
        self.assertEqual(VRTBuilder.format_gdal_path(local_path), local_path)

    def test_create_multiband_vrt(self):
        # Create two 1-band temporary rasters
        with tempfile.TemporaryDirectory() as tmpdir:
            red_path = os.path.join(tmpdir, "red.tif")
            nir_path = os.path.join(tmpdir, "nir.tif")
            vrt_path = os.path.join(tmpdir, "composite.vrt")

            driver = gdal.GetDriverByName("GTiff")
            ds1 = driver.Create(red_path, 20, 20, 1, gdal.GDT_Float32)
            ds1.GetRasterBand(1).Fill(0.1)
            ds1 = None

            ds2 = driver.Create(nir_path, 20, 20, 1, gdal.GDT_Float32)
            ds2.GetRasterBand(1).Fill(0.7)
            ds2 = None

            result_vrt = VRTBuilder.create_multiband_vrt(vrt_path, [red_path, nir_path])
            self.assertTrue(os.path.exists(result_vrt))

            vrt_ds = gdal.Open(result_vrt)
            self.assertIsNotNone(vrt_ds)
            self.assertEqual(vrt_ds.RasterCount, 2)
            vrt_ds = None


if __name__ == "__main__":
    unittest.main()
