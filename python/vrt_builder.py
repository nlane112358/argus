#!/usr/bin/env python3
"""
Virtual Raster (VRT) Builder for Argus
Builds lightweight, zero-copy GDAL VRT descriptors combining separate Red and NIR
Cloud-Optimized GeoTIFFs (COGs) into multi-band streams.
"""

import os
from typing import List
from osgeo import gdal


class VRTBuilder:
    @staticmethod
    def format_gdal_path(url_or_path: str) -> str:
        """
        Ensures remote HTTP/HTTPS URLs use the GDAL /vsicurl/ virtual file system handler.
        """
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            if not url_or_path.startswith("/vsicurl/"):
                return f"/vsicurl/{url_or_path}"
        elif url_or_path.startswith("s3://"):
            if not url_or_path.startswith("/vsis3/"):
                return f"/vsis3/{url_or_path[5:]}"
        return url_or_path

    @classmethod
    def create_multiband_vrt(cls, output_vrt_path: str, band_paths: List[str]) -> str:
        """
        Creates a multi-band VRT file from separate single-band rasters or URLs.
        Band 1 = band_paths[0] (Red)
        Band 2 = band_paths[1] (NIR)
        """
        formatted_paths = [cls.format_gdal_path(p) for p in band_paths]
        os.makedirs(os.path.dirname(os.path.abspath(output_vrt_path)), exist_ok=True)

        vrt_options = gdal.BuildVRTOptions(
            separate=True,  # Place each input file into a separate band
            resampleAlg="bilinear"
        )

        vrt_ds = gdal.BuildVRT(output_vrt_path, formatted_paths, options=vrt_options)
        if not vrt_ds:
            raise RuntimeError(f"Failed to generate GDAL VRT at: {output_vrt_path}")
        
        vrt_ds.FlushCache()
        vrt_ds = None
        return output_vrt_path
