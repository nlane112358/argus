#!/usr/bin/env python3
"""
Argus Optical Visualizer Module
Renders True-Color (RGB) photographic optical satellite images alongside
deforestation risk detection overlays.
"""

import os
import sys
import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()


def stretch_channel(channel: np.ndarray, nodata_mask: np.ndarray = None, p_low: float = 2.0, p_high: float = 98.0) -> np.ndarray:
    valid = channel[~nodata_mask] if nodata_mask is not None else channel
    if len(valid) == 0:
        return np.zeros_like(channel, dtype=np.uint8)

    vmin = np.percentile(valid, p_low)
    vmax = np.percentile(valid, p_high)

    if vmax <= vmin:
        vmax = vmin + 1e-4

    stretched = np.clip((channel - vmin) / (vmax - vmin) * 255.0, 0, 255).astype(np.uint8)
    return stretched


def make_true_color_rgb(r: np.ndarray, g: np.ndarray, b: np.ndarray, nodata_mask: np.ndarray = None) -> np.ndarray:
    r_str = stretch_channel(r, nodata_mask)
    g_str = stretch_channel(g, nodata_mask)
    b_str = stretch_channel(b, nodata_mask)

    rgb = np.dstack([r_str, g_str, b_str])
    if nodata_mask is not None:
        rgb[nodata_mask] = [25, 25, 30]
    return rgb


def upscale_array(arr: np.ndarray, min_dim: int = 380) -> np.ndarray:
    h, w = arr.shape[:2]
    scale_y = max(1, min_dim // h)
    scale_x = max(1, min_dim // w)
    scale = max(scale_y, scale_x)

    if scale > 1:
        return np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)
    return arr


def make_deforestation_overlay(current_rgb: np.ndarray, delta_ndvi: np.ndarray, nodata_mask: np.ndarray = None) -> np.ndarray:
    overlay = current_rgb.copy().astype(np.float32)

    deforested = delta_ndvi <= -0.20
    thinned = (delta_ndvi > -0.20) & (delta_ndvi <= -0.10)

    red_color = np.array([235, 30, 40], dtype=np.float32)
    orange_color = np.array([245, 140, 30], dtype=np.float32)

    overlay[deforested] = 0.35 * overlay[deforested] + 0.65 * red_color
    overlay[thinned] = 0.50 * overlay[thinned] + 0.50 * orange_color

    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
    if nodata_mask is not None:
        overlay[nodata_mask] = [25, 25, 30]
    return overlay


def generate_audit_png(
    vector_path: str,
    baseline_raster: str,
    current_raster: str,
    output_png_path: str,
    red_band: int = 1,
    green_band: int = 2,
    blue_band: int = 3,
    nir_band: int = 4,
    asset_id: str = "ASSET-PARCEL",
    is_compliant: bool = True,
    loss_percent: float = 0.0,
) -> str:
    # High-performance Cloud-Optimized GeoTIFF HTTP/2 and caching options
    gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    gdal.SetConfigOption("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
    gdal.SetConfigOption("GDAL_HTTP_MULTIPLEX", "YES")
    gdal.SetConfigOption("GDAL_HTTP_VERSION", "2")
    gdal.SetConfigOption("VSI_CACHE", "YES")
    gdal.SetConfigOption("VSI_CACHE_SIZE", "67108864")
    warp_opts_base = gdal.WarpOptions(
        format="MEM",
        cutlineDSName=vector_path,
        cropToCutline=True,
        dstNodata=-9999.0,
    )
    base_ds = gdal.Warp("", baseline_raster, options=warp_opts_base)
    if not base_ds:
        raise RuntimeError(f"Could not crop baseline raster to vector cutline: {baseline_raster}")

    width = base_ds.RasterXSize
    height = base_ds.RasterYSize
    base_bands = base_ds.RasterCount

    if base_bands >= 4:
        if red_band == 3 and blue_band == 1:
            r_idx, g_idx, b_idx, n_idx = 3, 2, 1, 4
        else:
            r_idx, g_idx, b_idx, n_idx = red_band, green_band, blue_band, nir_band
    elif base_bands == 3:
        r_idx, g_idx, b_idx, n_idx = 1, 2, 3, 1
    else:
        r_idx, g_idx, b_idx, n_idx = 1, 1, 2, 2

    warp_opts_curr = gdal.WarpOptions(
        format="MEM",
        cutlineDSName=vector_path,
        cropToCutline=True,
        width=width,
        height=height,
        dstNodata=-9999.0,
    )
    curr_ds = gdal.Warp("", current_raster, options=warp_opts_curr)
    if not curr_ds:
        raise RuntimeError(f"Could not crop current raster to vector cutline: {current_raster}")

    b_r = base_ds.GetRasterBand(r_idx).ReadAsArray().astype(np.float32)
    b_g = base_ds.GetRasterBand(g_idx).ReadAsArray().astype(np.float32)
    b_b = base_ds.GetRasterBand(b_idx).ReadAsArray().astype(np.float32)
    b_nir = base_ds.GetRasterBand(n_idx).ReadAsArray().astype(np.float32)

    c_r = curr_ds.GetRasterBand(r_idx).ReadAsArray().astype(np.float32)
    c_g = curr_ds.GetRasterBand(g_idx).ReadAsArray().astype(np.float32)
    c_b = curr_ds.GetRasterBand(b_idx).ReadAsArray().astype(np.float32)
    c_nir = curr_ds.GetRasterBand(n_idx).ReadAsArray().astype(np.float32)

    nodata_mask = (b_r == -9999.0) | (c_r == -9999.0) | np.isnan(b_r) | np.isnan(c_r)

    eps = 1e-6
    ndvi_base = np.clip((b_nir - b_r) / (b_nir + b_r + eps), -1.0, 1.0)
    ndvi_curr = np.clip((c_nir - c_r) / (c_nir + c_r + eps), -1.0, 1.0)
    delta_ndvi = ndvi_curr - ndvi_base

    rgb_base = make_true_color_rgb(b_r, b_g, b_b, nodata_mask)
    rgb_curr = make_true_color_rgb(c_r, c_g, c_b, nodata_mask)
    rgb_overlay = make_deforestation_overlay(rgb_curr, delta_ndvi, nodata_mask)

    panel_base = upscale_array(rgb_base, min_dim=380)
    panel_curr = upscale_array(rgb_curr, min_dim=380)
    panel_delta = upscale_array(rgb_overlay, min_dim=380)

    ph, pw, _ = panel_base.shape
    gutter = 14
    total_w = pw * 3 + gutter * 4
    header_h = 75
    footer_h = 45
    total_h = header_h + ph + footer_h

    canvas = np.full((total_h, total_w, 3), 22, dtype=np.uint8)

    status_color = [40, 200, 90] if is_compliant else [235, 40, 40]
    canvas[header_h - 4 : header_h, :] = status_color
    canvas[total_h - 4 : total_h, :] = status_color

    y_start = header_h + 12
    for col_idx, panel in enumerate([panel_base, panel_curr, panel_delta]):
        x1 = gutter * (col_idx + 1) + pw * col_idx
        x2 = x1 + pw
        canvas[y_start - 2 : y_start + ph + 2, x1 - 2 : x2 + 2, :] = [55, 60, 70]
        canvas[y_start : y_start + ph, x1 : x2] = panel

    os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)
    mem_driver = gdal.GetDriverByName("MEM")
    mem_ds = mem_driver.Create("", total_w, total_h, 3, gdal.GDT_Byte)
    for c in range(3):
        mem_ds.GetRasterBand(c + 1).WriteArray(canvas[:, :, c])

    png_driver = gdal.GetDriverByName("PNG")
    png_ds = png_driver.CreateCopy(output_png_path, mem_ds)
    png_ds = None
    mem_ds = None
    base_ds = None
    curr_ds = None

    return output_png_path


def generate_optical_products(
    vector_path: str,
    baseline_raster: str,
    current_raster: str,
    output_dir: str,
    red_band: int = 1,
    green_band: int = 2,
    blue_band: int = 3,
    nir_band: int = 4,
) -> dict:
    """Write aligned, parcel-clipped RGB epochs and an NDVI-change overlay.

    The returned corner coordinates let MapLibre place each PNG at its real
    footprint on the map. Alpha is transparent outside the parcel cutline.
    """
    os.makedirs(output_dir, exist_ok=True)
    warp_opts_base = gdal.WarpOptions(
        format="MEM",
        cutlineDSName=vector_path,
        cropToCutline=True,
        dstNodata=-9999.0,
        resampleAlg="bilinear",
    )
    base_ds = gdal.Warp("", baseline_raster, options=warp_opts_base)
    if not base_ds:
        raise RuntimeError(f"Could not crop baseline raster to vector cutline: {baseline_raster}")

    width, height = base_ds.RasterXSize, base_ds.RasterYSize
    gt = base_ds.GetGeoTransform()
    bounds = [gt[0], gt[3] + height * gt[5], gt[0] + width * gt[1], gt[3]]
    warp_opts_current = gdal.WarpOptions(
        format="MEM",
        cutlineDSName=vector_path,
        outputBounds=bounds,
        outputBoundsSRS=base_ds.GetProjection(),
        width=width,
        height=height,
        dstSRS=base_ds.GetProjection(),
        dstNodata=-9999.0,
        resampleAlg="bilinear",
    )
    curr_ds = gdal.Warp("", current_raster, options=warp_opts_current)
    if not curr_ds:
        raise RuntimeError(f"Could not align current raster to baseline: {current_raster}")

    def read_band(ds, index):
        band = ds.GetRasterBand(index)
        if not band:
            raise RuntimeError(f"Raster is missing requested band {index}")
        return band.ReadAsArray().astype(np.float32)

    b_r, b_g, b_b, b_nir = [read_band(base_ds, i) for i in (red_band, green_band, blue_band, nir_band)]
    c_r, c_g, c_b, c_nir = [read_band(curr_ds, i) for i in (red_band, green_band, blue_band, nir_band)]
    all_bands = (b_r, b_g, b_b, b_nir, c_r, c_g, c_b, c_nir)
    nodata_mask = np.logical_or.reduce([
        (band == -9999.0) | ~np.isfinite(band)
        for band in all_bands
    ])

    rgb_base = make_true_color_rgb(b_r, b_g, b_b, nodata_mask)
    rgb_curr = make_true_color_rgb(c_r, c_g, c_b, nodata_mask)
    delta_ndvi = np.clip(
        (c_nir - c_r) / (c_nir + c_r + 1e-6) - (b_nir - b_r) / (b_nir + b_r + 1e-6),
        -2.0,
        2.0,
    )
    rgb_difference = make_deforestation_overlay(rgb_curr, delta_ndvi, nodata_mask)
    alpha = np.where(nodata_mask, 0, 255).astype(np.uint8)

    def write_rgba(path, rgb):
        rgba = np.dstack([rgb, alpha])
        mem_ds = gdal.GetDriverByName("MEM").Create("", width, height, 4, gdal.GDT_Byte)
        mem_ds.SetGeoTransform(gt)
        mem_ds.SetProjection(base_ds.GetProjection())
        color_interpretations = [gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand, gdal.GCI_AlphaBand]
        for i in range(4):
            band = mem_ds.GetRasterBand(i + 1)
            band.SetColorInterpretation(color_interpretations[i])
            band.WriteArray(rgba[:, :, i])
        png = gdal.GetDriverByName("PNG").CreateCopy(path, mem_ds)
        if not png:
            raise RuntimeError(f"Could not write optical image: {path}")
        png = None
        mem_ds = None

    paths = {
        "baseline": os.path.join(output_dir, "baseline.png"),
        "current": os.path.join(output_dir, "current.png"),
        "difference": os.path.join(output_dir, "difference.png"),
    }
    write_rgba(paths["baseline"], rgb_base)
    write_rgba(paths["current"], rgb_curr)
    write_rgba(paths["difference"], rgb_difference)

    src_srs = osr.SpatialReference()
    src_srs.ImportFromWkt(base_ds.GetProjection())
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(src_srs, wgs84)
    pixel_corners = [
        (0, 0),
        (width, 0),
        (width, height),
        (0, height),
    ]
    image_coordinates = []
    for px, py in pixel_corners:
        x = gt[0] + px * gt[1] + py * gt[2]
        y = gt[3] + px * gt[4] + py * gt[5]
        lon, lat, _ = transform.TransformPoint(x, y)
        image_coordinates.append([lon, lat])

    curr_ds = None
    base_ds = None
    return {"paths": paths, "image_coordinates": image_coordinates}


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 visualizer.py <polygon.geojson> <baseline.tif> <current.tif> <output.png> [r] [g] [b] [nir]")
        sys.exit(1)

    poly = sys.argv[1]
    base = sys.argv[2]
    curr = sys.argv[3]
    out = sys.argv[4]
    r = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    g = int(sys.argv[6]) if len(sys.argv) > 6 else 2
    b = int(sys.argv[7]) if len(sys.argv) > 7 else 3
    nir = int(sys.argv[8]) if len(sys.argv) > 8 else 4

    saved = generate_audit_png(poly, base, curr, out, red_band=r, green_band=g, blue_band=b, nir_band=nir)
    print(f"[+] Successfully exported True-Color Optical audit PNG: {saved}")
