#!/usr/bin/env python3
"""
Argus FastAPI REST API Backend
Provides cloud-native endpoints for automated EUDR satellite compliance audits,
JSON verdicts for ERP integration, and downloadable PDF certification dossiers.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from python.pdf_generator import generate_eudr_pdf

app = FastAPI(
    title="Argus EUDR Compliance Engine API",
    description="Automated satellite due diligence API for Regulation (EU) 2023/1115",
    version="2.0.0",
)

# Enable CORS for web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "engine": "Argus Automated Satellite ESG & EUDR Auditor",
        "version": "2.0.0",
        "standard": "Regulation (EU) 2023/1115",
        "endpoints": {
            "health": "/health",
            "audit_json": "POST /api/v1/audit",
            "audit_pdf": "POST /api/v1/audit/pdf",
            "audit_image": "POST /api/v1/audit/image",
            "docs": "/docs",
        },
    }


@app.get("/health")
def health():
    binary_path = PROJECT_ROOT / "esg_auditor"
    has_binary = binary_path.exists()
    return {
        "status": "healthy" if has_binary else "degraded",
        "binary_compiled": has_binary,
        "gdal_support": True,
        "stac_integration": True,
    }


def _run_internal_audit(
    geojson_bytes: bytes,
    mock: bool = False,
    mock_violation: bool = False,
    tolerance: float = 2.0,
    save_png: bool = True
) -> dict:
    """Helper to save temporary GeoJSON, run the audit, and parse results."""
    tmp_dir = tempfile.mkdtemp(prefix="argus_api_")
    poly_path = os.path.join(tmp_dir, "input_parcel.geojson")
    with open(poly_path, "wb") as f:
        f.write(geojson_bytes)

    png_path = os.path.join(tmp_dir, "audit_map.png") if save_png else None
    cli_script = PROJECT_ROOT / "scripts" / "argus_cloud_audit.py"

    cmd = [
        sys.executable,
        str(cli_script),
        poly_path,
        "--json",
        "--tolerance", str(tolerance),
    ]
    if mock:
        cmd.append("--mock")
    if mock_violation:
        cmd.append("--mock-violation")
    if png_path:
        cmd.extend(["--save-png", png_path])

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        # Find JSON payload in stdout
        raw_out = proc.stdout.strip()
        start_idx = raw_out.find("{")
        end_idx = raw_out.rfind("}")
        if start_idx == -1 or end_idx == -1:
            raise ValueError(f"No JSON output from auditor: {proc.stderr}")
        report_data = json.loads(raw_out[start_idx : end_idx + 1])
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Audit execution error: {str(e)}")

    return {
        "report": report_data,
        "tmp_dir": tmp_dir,
        "png_path": png_path if (png_path and os.path.exists(png_path)) else None,
        "poly_path": poly_path,
        "exit_code": proc.returncode,
    }


@app.post("/api/v1/audit")
async def audit_parcel(
    file: UploadFile = File(...),
    mock: bool = Query(False, description="Run in offline mock mode using synthetic fixtures"),
    mock_violation: bool = Query(False, description="Simulate deforested non-compliant parcel in mock mode"),
    tolerance: float = Query(2.0, description="Max allowed canopy loss percentage"),
):
    """
    Ingests a farm polygon (.geojson), queries Sentinel-2 cloud satellites,
    and returns an automated EUDR compliance verification report.
    """
    content = await file.read()
    res = _run_internal_audit(content, mock=mock, mock_violation=mock_violation, tolerance=tolerance, save_png=False)
    shutil.rmtree(res["tmp_dir"], ignore_errors=True)
    return JSONResponse(content=res["report"], status_code=200 if res["report"]["is_compliant"] else 200)


@app.post("/api/v1/audit/pdf")
async def audit_parcel_pdf(
    file: UploadFile = File(...),
    mock: bool = Query(False, description="Run in offline mock mode using synthetic fixtures"),
    mock_violation: bool = Query(False, description="Simulate deforested non-compliant parcel in mock mode"),
    tolerance: float = Query(2.0, description="Max allowed canopy loss percentage"),
):
    """
    Ingests a farm polygon, executes the audit, and returns an official,
    tamper-evident EUDR Compliance Audit Dossier (PDF).
    """
    content = await file.read()
    res = _run_internal_audit(content, mock=mock, mock_violation=mock_violation, tolerance=tolerance, save_png=True)
    
    pdf_path = os.path.join(res["tmp_dir"], "EUDR_Compliance_Certificate.pdf")
    generate_eudr_pdf(res["report"], res["png_path"] or "", pdf_path)

    asset_id = res["report"].get("asset_id", "PARCEL")
    filename = f"EUDR_Certificate_{asset_id}.pdf"

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
    )


@app.post("/api/v1/audit/image")
async def audit_parcel_image(
    file: UploadFile = File(...),
    mock: bool = Query(False, description="Run in offline mock mode using synthetic fixtures"),
    mock_violation: bool = Query(False, description="Simulate deforested non-compliant parcel in mock mode"),
):
    """
    Ingests a farm polygon and returns the 3-panel satellite comparison PNG.
    """
    content = await file.read()
    res = _run_internal_audit(content, mock=mock, mock_violation=mock_violation, save_png=True)
    if not res["png_path"] or not os.path.exists(res["png_path"]):
        shutil.rmtree(res["tmp_dir"], ignore_errors=True)
        raise HTTPException(status_code=500, detail="Could not generate comparison visual.")

    return FileResponse(res["png_path"], media_type="image/png", filename="audit_comparison.png")
