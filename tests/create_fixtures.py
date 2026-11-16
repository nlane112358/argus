#!/usr/bin/env python3
import json
import os
import numpy as np
from osgeo import gdal, ogr, osr

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def create_synthetic_raster(filename):
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    filepath = os.path.join(FIXTURES_DIR, filename)
    width = 100
    height = 100
    bands = 4
    
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(filepath, width, height, bands, gdal.GDT_Float32)
    
    # Origin in UTM Zone 21S: 650000 E, 8800000 N, pixel resolution 10m x 10m
    geo_transform = [650000.0, 10.0, 0.0, 8800000.0, 0.0, -10.0]
    ds.SetGeoTransform(geo_transform)
    
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32721) # WGS 84 / UTM zone 21S
    ds.SetProjection(srs.ExportToWkt())
    
    np.random.seed(42)
    for b in range(1, bands + 1):
        band = ds.GetRasterBand(b)
        data = np.random.uniform(0.1, 0.8, (height, width)).astype(np.float32)
        # Induce a degraded patch in the center
        data[40:60, 40:60] = 0.05
        band.WriteArray(data)
        band.FlushCache()
    ds = None
    print(f"[+] Created synthetic raster: {filepath}")

def create_geojson_in_wgs84(filename):
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    filepath = os.path.join(FIXTURES_DIR, filename)
    srs_utm = osr.SpatialReference()
    srs_utm.ImportFromEPSG(32721)
    
    srs_wgs84 = osr.SpatialReference()
    srs_wgs84.ImportFromEPSG(4326)
    srs_wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    transform = osr.CoordinateTransformation(srs_utm, srs_wgs84)
    
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
                    "asset_id": "FARM-AMAZON-001",
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
    create_synthetic_raster('test_raster_utm.tif')
    create_geojson_in_wgs84('test_farm_wgs84.geojson')
    create_outside_geojson('test_outside.geojson')
