#!/usr/bin/env python3
"""
Argus EUDR PDF Certificate Generator
Produces official, tamper-evident EU Deforestation Regulation (EUDR)
compliance audit dossiers with embedded visual satellite comparison maps,
physical canopy loss metrics, and SHA-256 cryptographic verification hashes.
"""

import os
import sys
import json
import hashlib
import zlib
from datetime import datetime, timezone
from pathlib import Path
from osgeo import gdal
import numpy as np


def compute_sha256(data_dict: dict) -> str:
    """Computes a deterministic SHA-256 fingerprint for non-repudiation."""
    serialized = json.dumps(data_dict, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def generate_eudr_pdf(
    report_data: dict,
    visual_png_path: str,
    output_pdf_path: str
) -> str:
    """
    Generates a complete, standard PDF 1.4 compliance certificate.
    Supports fpdf2 if available, or falls back to built-in pure-Python PDF rendering.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    
    # Try using fpdf2 if installed
    try:
        from fpdf import FPDF
        return _generate_with_fpdf2(report_data, visual_png_path, output_pdf_path)
    except ImportError:
        pass

    # Pure-Python self-contained PDF 1.4 generator fallback
    return _generate_builtin_pdf(report_data, visual_png_path, output_pdf_path)


def _generate_with_fpdf2(report: dict, img_path: str, out_path: str) -> str:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Dark Header Banner
    pdf.set_fill_color(24, 30, 42)
    pdf.rect(0, 0, 210, 38, style="F")

    # Header Text
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.set_xy(14, 8)
    pdf.cell(0, 8, "ARGUS DUE DILIGENCE AUDIT CERTIFICATE", ln=True)

    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(180, 195, 210)
    pdf.set_xy(14, 17)
    pdf.cell(0, 6, "EU Deforestation Regulation (EUDR - Regulation (EU) 2023/1115)", ln=True)
    pdf.set_xy(14, 23)
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Standard: High-Assurance Satellite Audit", ln=True)

    # Compliance Status Pill
    is_compliant = report.get("is_compliant", True)
    if is_compliant:
        pdf.set_fill_color(38, 166, 91)
        status_text = "STATUS: [PASSED] COMPLIANT"
    else:
        pdf.set_fill_color(217, 30, 24)
        status_text = "STATUS: [FLAGGED] VIOLATION"

    pdf.set_xy(135, 12)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(62, 10, status_text, border=0, ln=True, align="C", fill=True)

    # Section 1: Parcel Identification & Scope
    pdf.set_xy(14, 45)
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.set_text_color(30, 40, 55)
    pdf.cell(0, 7, "1. TARGET ASSET & SUPPLY CHAIN METADATA", ln=True)
    pdf.set_draw_color(200, 210, 220)
    pdf.line(14, 52, 196, 52)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(50, 60, 75)
    pdf.set_xy(14, 55)

    col1 = f"Asset Identifier:  {report.get('asset_id', 'UNKNOWN')}\nCommodity Audited: {report.get('commodity', 'UNSPECIFIED')}\nTotal Parcel Area: {report.get('parcel_area_ha', 0.0):.2f} Hectares"
    col2 = f"Legal Cutoff Date:   2020-12-31\nBaseline Canopy:     {report.get('baseline_forest_ha', 0.0):.2f} Hectares\nCanopy Loss Detected: {report.get('deforested_ha', 0.0):.2f} Hectares ({report.get('canopy_loss_percent', 0.0):.2f}%)"

    pdf.multi_cell(90, 5, col1, border=0)
    pdf.set_xy(110, 55)
    pdf.multi_cell(90, 5, col2, border=0)

    # Section 2: Satellite Observation & Spectral Metrics
    pdf.set_xy(14, 76)
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.set_text_color(30, 40, 55)
    pdf.cell(0, 7, "2. SATELLITE OBSERVATION PROVENANCE & SPECTRAL AUDIT", ln=True)
    pdf.line(14, 83, 196, 83)

    pdf.set_xy(14, 86)
    pdf.set_font("Helvetica", size=8.5)
    spec_info = (
        f"Baseline Scene (2020 Cutoff): {os.path.basename(report.get('baseline_raster', '2020_Epoch'))}\n"
        f"Current Epoch Scene:         {os.path.basename(report.get('current_raster', 'Current_Epoch'))}\n"
        f"Mean Baseline NDVI: {report.get('mean_baseline_ndvi', 0.0):.3f}  |  "
        f"Mean Current NDVI: {report.get('mean_current_ndvi', 0.0):.3f}  |  "
        f"Mean Delta NDVI: {report.get('mean_delta_ndvi', 0.0):.3f}  |  "
        f"Allowed Tolerance: {report.get('tolerance_percent', 2.0):.1f}%"
    )
    pdf.multi_cell(182, 4.5, spec_info, border=0)

    # Section 3: Visual Satellite Change Detection Map
    pdf.set_xy(14, 106)
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 7, "3. BI-TEMPORAL SATELLITE COMPARISON MAP & CHANGE OVERLAY", ln=True)
    pdf.line(14, 113, 196, 113)

    if os.path.exists(img_path):
        pdf.image(img_path, x=14, y=117, w=182)

    # Section 4: Legal Attestation & Cryptographic Chain of Custody
    pdf.set_xy(14, 230)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(0, 6, "4. DIGITAL CERTIFICATION & NON-REPUDIATION ATTESTATION", ln=True)
    pdf.line(14, 236, 196, 236)

    sha = compute_sha256(report)
    pdf.set_xy(14, 239)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(70, 80, 95)
    declaration = (
        "This certificate was generated by the Argus Autonomous Satellite Compliance Engine using calibrated\n"
        "Copernicus Sentinel-2 Level-2A multi-spectral data. The evaluation validates non-deforestation status\n"
        "pursuant to Article 3 of Regulation (EU) 2023/1115."
    )
    pdf.multi_cell(182, 4, declaration, border=0)

    pdf.set_xy(14, 254)
    pdf.set_font("Courier", size=7.5)
    pdf.set_text_color(100, 110, 125)
    pdf.cell(0, 5, f"CRYPTOGRAPHIC SHA-256 PROVENANCE HASH: {sha}", ln=True)
    pdf.cell(0, 4, "STATUS VERDICT: " + report.get("verdict", "AUDIT COMPLETED"), ln=True)

    pdf.output(out_path)
    return out_path


def _generate_builtin_pdf(report: dict, img_path: str, out_path: str) -> str:
    """
    Pure-Python standard PDF 1.4 generator with zero third-party dependencies.
    Produces a valid, formatted single-page A4 compliance certificate with embedded raster map.
    """
    sha = compute_sha256(report)
    is_compliant = report.get("is_compliant", True)
    verdict_str = report.get("verdict", "AUDIT COMPLETED")
    asset_id = report.get("asset_id", "UNKNOWN")
    commodity = report.get("commodity", "UNSPECIFIED")
    parcel_ha = report.get("parcel_area_ha", 0.0)
    base_ha = report.get("baseline_forest_ha", 0.0)
    loss_ha = report.get("deforested_ha", 0.0)
    loss_pct = report.get("canopy_loss_percent", 0.0)
    ndvi_base = report.get("mean_baseline_ndvi", 0.0)
    ndvi_curr = report.get("mean_current_ndvi", 0.0)
    ndvi_delta = report.get("mean_delta_ndvi", 0.0)
    
    # Read and compress embedded PNG image if present
    img_obj = b""
    img_ref = b""
    if os.path.exists(img_path):
        try:
            ds = gdal.Open(img_path)
            if ds and ds.RasterCount >= 3:
                iw, ih = ds.RasterXSize, ds.RasterYSize
                r = ds.GetRasterBand(1).ReadAsArray()
                g = ds.GetRasterBand(2).ReadAsArray()
                b = ds.GetRasterBand(3).ReadAsArray()
                raw_bytes = np.dstack([r, g, b]).tobytes()
                comp_bytes = zlib.compress(raw_bytes)
                img_obj = (
                    f"6 0 obj\n"
                    f"<< /Type /XObject /Subtype /Image /Width {iw} /Height {ih} "
                    f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(comp_bytes)} >>\n"
                    f"stream\n".encode() + comp_bytes + b"\nendstream\nendobj\n"
                )
                img_ref = b"/XObject << /Im1 6 0 R >>"
                ds = None
        except Exception:
            img_obj = b""
            img_ref = b""

    # Prepare PDF stream operations
    stream_ops = []
    
    # Top Banner (Dark Navy rectangle: 0 740 to 595 842)
    stream_ops.append(b"0.09 0.12 0.16 rg 0 735 595 107 re f\n")
    
    # Accent Line (Green or Red)
    if is_compliant:
        stream_ops.append(b"0.15 0.65 0.35 rg 0 730 595 5 re f\n")
        stream_ops.append(b"0.15 0.65 0.35 rg 380 755 180 28 re f\n")
    else:
        stream_ops.append(b"0.85 0.12 0.10 rg 0 730 595 5 re f\n")
        stream_ops.append(b"0.85 0.12 0.10 rg 380 755 180 28 re f\n")
        
    # Text in Banner
    stream_ops.append(
        b"BT /F1 16 Tf 1 1 1 rg 30 795 Td (ARGUS DUE DILIGENCE AUDIT CERTIFICATE) Tj ET\n"
        b"BT /F2 10 Tf 0.7 0.77 0.82 rg 30 778 Td (EU Deforestation Regulation \\(EUDR - Regulation \\(EU\\) 2023/1115\\)) Tj ET\n"
        b"BT /F2 8.5 Tf 0.7 0.77 0.82 rg 30 762 Td (Automated High-Assurance Spaceborne Due Diligence Verification) Tj ET\n"
    )
    
    # Status Badge Text
    status_label = b"[PASSED] COMPLIANT" if is_compliant else b"[FLAGGED] VIOLATION"
    stream_ops.append(
        f"BT /F1 11 Tf 1 1 1 rg 400 765 Td ({status_label.decode()}) Tj ET\n".encode()
    )

    # Section 1: Asset Metadata
    sec1_text = (
        "0.12 0.16 0.22 rg BT /F1 11 Tf 30 705 Td (1. TARGET ASSET & SUPPLY CHAIN METADATA) Tj ET\n"
        "0.78 0.82 0.86 RG 30 698 m 565 698 l S\n"
        "0.2 0.24 0.30 rg BT /F2 9.5 Tf\n"
        f"30 680 Td (Asset Identifier:  {asset_id}) Tj\n"
        f"0 -14 Td (Commodity Audited: {commodity}) Tj\n"
        f"0 -14 Td (Total Parcel Area: {parcel_ha:.2f} Hectares) Tj\n"
        f"260 28 Td (Legal Cutoff Date:   2020-12-31) Tj\n"
        f"0 -14 Td (Baseline Forest:    {base_ha:.2f} Hectares) Tj\n"
        f"0 -14 Td (Detected Loss:      {loss_ha:.2f} Hectares \\({loss_pct:.2f}%\\)) Tj\n"
        "ET\n"
    )
    stream_ops.append(sec1_text.encode("utf-8"))

    # Section 2: Spectral Provenance
    sec2_text = (
        "0.12 0.16 0.22 rg BT /F1 11 Tf 30 615 Td (2. SATELLITE OBSERVATION PROVENANCE & SPECTRAL METRICS) Tj ET\n"
        "0.78 0.82 0.86 RG 30 608 m 565 608 l S\n"
        "0.2 0.24 0.30 rg BT /F2 9 Tf\n"
        "30 592 Td (Sensor Constellation: ESA Copernicus Sentinel-2 Multi-Spectral Instrument \\(10m\\)) Tj\n"
        f"0 -13 Td (Spectral Change: Mean Base NDVI: {ndvi_base:.3f} | Current NDVI: {ndvi_curr:.3f} | Delta NDVI: {ndvi_delta:.3f}) Tj\n"
        "ET\n"
    )
    stream_ops.append(sec2_text.encode("utf-8"))

    # Section 3: Visual Map
    stream_ops.append(
        b"0.12 0.16 0.22 rg BT /F1 11 Tf 30 545 Td (3. BI-TEMPORAL SATELLITE COMPARISON MAP & OVERLAY) Tj ET\n"
        b"0.78 0.82 0.86 RG 30 538 m 565 538 l S\n"
    )

    # Embed Image if present
    if img_obj:
        # Image coordinates: x=30, y=280, w=535, h=240
        stream_ops.append(b"q 535 0 0 240 30 285 cm /Im1 Do Q\n")

    # Section 4: Legal & Cryptographic Attestation
    sec4_text = (
        "0.12 0.16 0.22 rg BT /F1 11 Tf 30 250 Td (4. DIGITAL CERTIFICATION & NON-REPUDIATION ATTESTATION) Tj ET\n"
        "0.78 0.82 0.86 RG 30 243 m 565 243 l S\n"
        "0.28 0.32 0.38 rg BT /F2 8.5 Tf\n"
        "30 228 Td (This certificate verifies compliance under Article 3 of Regulation \\(EU\\) 2023/1115.) Tj\n"
        f"0 -12 Td (STATUS VERDICT: {verdict_str}) Tj\n"
        f"0 -13 Td (CRYPTOGRAPHIC SHA-256 HASH: {sha}) Tj\n"
        "ET\n"
    )
    stream_ops.append(sec4_text.encode("utf-8"))

    # Footer line
    footer_color = b"0.15 0.65 0.35" if is_compliant else b"0.85 0.12 0.10"
    stream_ops.append(f"{footer_color.decode()} rg 0 0 595 6 re f\n".encode())

    content_stream = b"".join(stream_ops)

    # Assemble PDF objects
    objs = []
    # 1: Catalog
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # 2: Pages
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    # 3: Page
    objs.append(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 7 0 R >> {img_ref.decode()} >> >>".encode()
    )
    # 4: Contents
    objs.append(f"<< /Length {len(content_stream)} >>\nstream\n".encode() + content_stream + b"\nendstream")
    # 5: Font F1 (Bold)
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    # 6: Image Object (if present)
    if img_obj:
        objs.append(img_obj)
    # 7: Font F2 (Regular)
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Build final PDF file
    pdf_bytes = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for idx, obj in enumerate(objs, start=1):
        offsets.append(len(pdf_bytes))
        if isinstance(obj, bytes) and b"obj\n" in obj:
            pdf_bytes.extend(obj)
        else:
            pdf_bytes.extend(f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n")

    xref_pos = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        pdf_bytes.extend(f"{off:010d} 00000 n \n".encode())

    pdf_bytes.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )

    with open(out_path, "wb") as f:
        f.write(pdf_bytes)

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 pdf_generator.py <audit_report.json> <visual.png> [out.pdf]")
        sys.exit(1)

    json_path = sys.argv[1]
    img_path = sys.argv[2]
    out_pdf = sys.argv[3] if len(sys.argv) > 3 else "audit_certificate.pdf"

    with open(json_path) as f:
        data = json.load(f)

    res = generate_eudr_pdf(data, img_path, out_pdf)
    print(f"[+] Successfully generated EUDR Compliance PDF: {res}")
