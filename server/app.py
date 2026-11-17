#!/usr/bin/env python3
"""
Argus Streamlit Web Dashboard
Interactive MVP frontend for supply chain sustainability and compliance officers:
- Drag & drop farm parcel GeoJSON files
- Instant satellite due diligence verification
- Embedded 3-panel visual satellite comparison maps
- One-click Official EUDR PDF Compliance Dossier download
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from python.pdf_generator import generate_eudr_pdf

try:
    import streamlit as st
except ImportError:
    print("[!] Error: Streamlit is not installed. Run 'pip install -r requirements.txt'")
    sys.exit(1)


st.set_page_config(
    page_title="Argus | Satellite EUDR Compliance Auditor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished enterprise typography
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1e2530;
        border-radius: 8px;
        padding: 16px;
        border: 1px solid #2d3748;
        text-align: center;
    }
    .status-passed {
        background-color: #1b4332;
        color: #d8f3dc;
        padding: 12px;
        border-radius: 8px;
        font-weight: bold;
        text-align: center;
        border: 1px solid #2d6a4f;
    }
    .status-failed {
        background-color: #5c1d1d;
        color: #ffccd5;
        padding: 12px;
        border-radius: 8px;
        font-weight: bold;
        text-align: center;
        border: 1px solid #8b0000;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def run_audit(poly_bytes: bytes, mock: bool, mock_violation: bool, tolerance: float):
    tmp_dir = tempfile.mkdtemp(prefix="argus_st_")
    poly_path = os.path.join(tmp_dir, "parcel.geojson")
    with open(poly_path, "wb") as f:
        f.write(poly_bytes)

    png_path = os.path.join(tmp_dir, "comparison.png")
    pdf_path = os.path.join(tmp_dir, "EUDR_Audit_Certificate.pdf")

    cli_script = PROJECT_ROOT / "scripts" / "argus_cloud_audit.py"
    cmd = [
        sys.executable,
        str(cli_script),
        poly_path,
        "--json",
        "--save-png", png_path,
        "--tolerance", str(tolerance),
    ]
    if mock:
        cmd.append("--mock")
    if mock_violation:
        cmd.append("--mock-violation")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    raw = proc.stdout.strip()
    start_idx = raw.find("{")
    end_idx = raw.rfind("}")
    
    if start_idx == -1 or end_idx == -1:
        st.error(f"Audit engine execution failed: {proc.stderr}")
        return None

    report = json.loads(raw[start_idx : end_idx + 1])
    
    # Generate PDF certificate
    if os.path.exists(png_path):
        generate_eudr_pdf(report, png_path, pdf_path)

    return {
        "report": report,
        "png_path": png_path if os.path.exists(png_path) else None,
        "pdf_path": pdf_path if os.path.exists(pdf_path) else None,
    }


# ==============================================================================
# Sidebar Configuration
# ==============================================================================
with st.sidebar:
    st.image("https://img.shields.io/badge/EUDR-Regulation%202023%2F1115-orange", width=220)
    st.title("Audit Settings")
    
    audit_mode = st.radio(
        "Execution Mode",
        ["Live Cloud (Sentinel-2 STAC)", "Offline Mock Simulation"],
        index=0,
    )
    is_mock = audit_mode == "Offline Mock Simulation"
    
    mock_violation = False
    if is_mock:
        mock_violation = st.checkbox("Simulate Deforested Parcel (Failure Case)", value=False)
        
    tolerance = st.slider("Canopy Loss Tolerance (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)

    st.markdown("---")
    st.markdown("### Sample Farm Data")
    load_sample = st.button("Load Brazil Soya Farm (12 Ha)")


# ==============================================================================
# Main Dashboard Area
# ==============================================================================
st.title("🛰️ Argus | Autonomous Satellite EUDR Auditor")
st.markdown(
    "Automated spaceborne due diligence platform verifying non-deforestation status "
    "under **Regulation (EU) 2023/1115**."
)

uploaded_file = st.file_uploader(
    "Upload Farm Parcel Boundary (GeoJSON)",
    type=["geojson", "json"],
    help="Upload polygon coordinates representing supplier farm or plantation boundaries.",
)

poly_bytes = None
if uploaded_file is not None:
    poly_bytes = uploaded_file.read()
elif load_sample:
    sample_path = PROJECT_ROOT / "farm_parcel.geojson"
    if sample_path.exists():
        with open(sample_path, "rb") as f:
            poly_bytes = f.read()
        st.info("Loaded sample parcel: `PARCEL-BRAZIL-SOYA-992` (Mato Grosso, Brazil)")


if poly_bytes:
    with st.spinner("Executing bi-temporal satellite audit (querying ESA Sentinel-2)..."):
        res = run_audit(poly_bytes, mock=is_mock, mock_violation=mock_violation, tolerance=tolerance)

    if res:
        report = res["report"]
        is_compliant = report.get("is_compliant", True)

        st.markdown("---")
        
        # 1. Prominent Status Banner
        if is_compliant:
            st.markdown(
                '<div class="status-passed"><h3>[PASSED] EUDR COMPLIANT</h3>'
                'Zero prohibited canopy loss detected post-December 31, 2020.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-failed"><h3>[FLAGGED] VIOLATION CONFIRMED</h3>'
                'Post-2020 deforestation exceeds regulatory threshold. Commodity is prohibited from EU market entry.</div>',
                unsafe_allow_html=True,
            )

        st.write("")

        # 2. Key Metrics Row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Parcel Area", f"{report.get('parcel_area_ha', 0.0):.2f} ha")
        with col2:
            st.metric("Baseline Canopy (2020)", f"{report.get('baseline_forest_ha', 0.0):.2f} ha")
        with col3:
            st.metric(
                "Detected Canopy Loss",
                f"{report.get('deforested_ha', 0.0):.2f} ha",
                delta=f"-{report.get('canopy_loss_percent', 0.0):.2f}%" if not is_compliant else "0%",
                delta_color="inverse",
            )
        with col4:
            st.metric("Mean Delta NDVI", f"{report.get('mean_delta_ndvi', 0.0):.3f}")

        # 3. Visual Satellite Comparison Map
        st.markdown("### Satellite Imagery & Change Detection Map")
        if res["png_path"]:
            st.image(
                res["png_path"],
                caption="Left: 2020 Cutoff Epoch (Sentinel-2) | Middle: Current Epoch | Right: Deforestation Alert Overlay",
                use_column_width=True,
            )

        # 4. Action Buttons (PDF Download)
        st.markdown("### Compliance Documentation")
        c1, c2 = st.columns([1, 3])
        with c1:
            if res["pdf_path"] and os.path.exists(res["pdf_path"]):
                with open(res["pdf_path"], "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    label="📄 Download Official EUDR PDF Certificate",
                    data=pdf_bytes,
                    file_name=f"EUDR_Certificate_{report.get('asset_id', 'PARCEL')}.pdf",
                    mime="application/pdf",
                )

        # 5. Developer Inspector
        with st.expander("ERP / Developer JSON Payload"):
            st.json(report)
