#!/usr/bin/env python3
import json
import os
import numpy as np
from osgeo import gdal, ogr, osr

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def create_raster(filename, ndvi_pattern="forest"):
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    filepath = os.path.join(FIXTURES_DIR, filename)
    width = 100
    height = 100
    bands = 4 # 1: Blue, 2: Green, 3: Red, 4: NIR
    
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(filepath, width, height, bands, gdal.GDT_Float32)
    
    # Origin in UTM Zone 21S (South America / Amazon basin): 650000 E, 8800000 N, 10m x 10m pixels
    geo_transform = [650000.0, 10.0, 0.0, 8800000.0, 0.0, -10.0]
    ds.SetGeoTransform(geo_transform)
    
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32721) # WGS 84 / UTM zone 21S
    ds.SetProjection(srs.ExportToWkt())
    
    np.random.seed(42)
    # Band 1 (Blue) and Band 2 (Green)
    blue = np.random.uniform(0.05, 0.15, (height, width)).astype(np.float32)
    green = np.random.uniform(0.10, 0.25, (height, width)).astype(np.float32)
    
    # Healthy forest: Low Red (~0.08), High NIR (~0.65) -> NDVI = (0.65 - 0.08)/(0.65 + 0.08) ≈ 0.78
    red = np.random.uniform(0.06, 0.10, (height, width)).astype(np.float32)
    nir = np.random.uniform(0.60, 0.70, (height, width)).astype(np.float32)
    
    if ndvi_pattern == "violation":
        # Simulate a deforested/cleared logging area in rows 40:60, cols 40:60
        # Cleared soil: High Red (~0.35), Low NIR (~0.20) -> NDVI = (0.20 - 0.35)/(0.20 + 0.35) ≈ -0.27
        red[40:60, 40:60] = np.random.uniform(0.30, 0.40, (20, 20)).astype(np.float32)
        nir[40:60, 40:60] = np.random.uniform(0.15, 0.25, (20, 20)).astype(np.float32)
    elif ndvi_pattern == "compliant":
        # Slight seasonal variation, but still preserved canopy
        red = red + np.random.uniform(-0.01, 0.01, (height, width)).astype(np.float32)
        nir = nir + np.random.uniform(-0.02, 0.01, (height, width)).astype(np.float32)

    for b_idx, array in enumerate([blue, green, red, nir], start=1):
        band = ds.GetRasterBand(b_idx)
        band.WriteArray(array)
        band.FlushCache()
        
    ds = None
    print(f"[+] Created synthetic raster ({ndvi_pattern}): {filepath}")

def create_geojson_in_wgs84(filename):
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    filepath = os.path.join(FIXTURES_DIR, filename)
    srs_utm = osr.SpatialReference()
    srs_utm.ImportFromEPSG(32721)
    
    srs_wgs84 = osr.SpatialReference()
    srs_wgs84.ImportFromEPSG(4326)
    srs_wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    transform = osr.CoordinateTransformation(srs_utm, srs_wgs84)
    
    # Polygon covering UTM [650300, 8799400] to [650700, 8799700] (approx 400m x 300m = 12 Hectares)
    pts = [
        (650300.0, 8799400.0),
        (650700.0, 8799400.0),
        (650700.0, 8799700.0),
        (650300.0, 8799700.0),
        (650300.0, 8799400.0)
    ]
    
    wgs_pts = []
    for x, y in pts:
        lon, lat, _ = transform.TransformPoint(x, y)
        wgs_pts.append([lon, lat])
        
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "asset_id": "PARCEL-BRAZIL-SOYA-992",
                    "commodity": "Soya"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [wgs_pts]
                }
            }
        ]
    }
    
    with open(filepath, 'w') as f:
        json.dump(geojson, f, indent=2)
    print(f"[+] Created synthetic WGS84 GeoJSON: {filepath}")

def create_outside_geojson(filename):
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    filepath = os.path.join(FIXTURES_DIR, filename)
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.35, 48.85], [2.36, 48.85], [2.36, 48.86], [2.35, 48.86], [2.35, 48.85]]]
            }
        }]
    }
    with open(filepath, 'w') as f:
        json.dump(geojson, f, indent=2)
    print(f"[+] Created out-of-bounds GeoJSON: {filepath}")

if __name__ == '__main__':
    create_raster('baseline_2020.tif', 'forest')
    create_raster('current_compliant_2026.tif', 'compliant')
    create_raster('current_violation_2026.tif', 'violation')
    create_geojson_in_wgs84('test_farm_wgs84.geojson')
    create_outside_geojson('test_outside.geojson')
