# Argus: Automated Satellite ESG & EUDR Compliance Auditor

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![C++17](https://img.shields.io/badge/C%2B%2B-17-blue.svg)](https://isocpp.org/)
[![CUDA](https://img.shields.io/badge/CUDA-12.x-green.svg)](https://developer.nvidia.com/cuda-zone)
[![GDAL](https://img.shields.io/badge/GDAL-3.x-brightgreen.svg)](https://gdal.org/)
[![EUDR Compliant](https://img.shields.io/badge/EUDR-Regulation%202023%2F1115-orange.svg)](https://environment.ec.europa.eu/topics/forests/deforestation/regulation-deforestation-free-products_en)

**Argus** is an enterprise-grade, high-performance satellite auditing engine designed to automate compliance verification for the **European Union Deforestation Regulation (EUDR - Regulation (EU) 2023/1115)** and global ESG due diligence mandates.

Given a supplier's farm boundary (GeoJSON, Shapefile, or KML), Argus autonomously queries public satellite catalogs (Sentinel-2), extracts multi-spectral Cloud-Optimized GeoTIFF (COG) streams with zero-copy I/O, evaluates bi-temporal vegetation canopy loss ($\Delta\text{NDVI}$), and produces tamper-evident audit verdicts and visual maps in seconds.

---

## Key Features

- **Autonomous STAC Ingestion**: Queries AWS Earth Search and Microsoft Planetary Computer for cloud-free Sentinel-2 scenes covering the pre-Dec 31, 2020 EUDR cutoff date and present day.
- **Zero-Copy Cloud Streaming**: Uses GDAL `/vsicurl/` and in-memory VRT compositing to stream only the pixels covering the farm (~40KB over the wire) instead of downloading 500MB+ satellite scenes.
- **Bi-Temporal Spectral Engine**: Calculates Normalized Difference Vegetation Index (NDVI) across epochs and computes physical canopy loss in hectares.
- **CUDA & CPU Parity**: Ultra-high-throughput parallel CUDA kernels for batch GPU processing on NVIDIA hardware (T4, A10G, L4, A100), with automatic SIMD CPU fallback.
- **Visual PNG Generation**: Exports side-by-side comparison dashboards with color-coded deforestation heatmaps.
- **Enterprise-Ready**: Emits standardized exit codes (`0` for compliant, `2` for violation) and machine-readable JSON for direct integration into SAP, Oracle, and supply chain ERPs.
- **Cloud Containerized**: Production Docker container compatible with AWS (ECS/EKS/Batch) and GCP (GKE/Cloud Run).

---

## Quickstart

### 1. Autonomous Cloud Audit
Audit any farm parcel anywhere on Earth with a single command:
```bash
# Run cloud audit and export visual comparison PNG and PDF certificate:
./bin/argus audit farm_parcel.geojson --save-png audit_map.png --pdf certificate.pdf

# Output machine-readable JSON for automated ERP pipelines:
./bin/argus audit farm_parcel.geojson --json
```

### 2. Streamlit Web Dashboard & FastAPI Backend
Launch the web UI or the REST API server:
```bash
# Launch Streamlit interactive web dashboard (http://localhost:8501):
./bin/argus serve-ui

# Launch FastAPI REST API server (http://localhost:8000 / http://localhost:8000/docs):
./bin/argus serve-api
```

### 3. Offline / Mock Mode (For Testing & CI/CD)
```bash
./bin/argus audit farm_parcel.geojson --mock --save-png mock_report.png --pdf mock_cert.pdf
```

### 4. Run Test Suite
```bash
./bin/argus test
```

---

## Visual PNG Comparison Output

When `--save-png <path.png>` is passed, Argus generates a 3-panel comparison dashboard:
1. **2020 Baseline Canopy (NDVI)**: Vegetation health at the EUDR cutoff date.
2. **Current Epoch Canopy (NDVI)**: Current vegetation canopy.
3. **Deforestation Change Map ($\Delta\text{NDVI}$)**: Color-coded canopy change (Crimson Red = Deforestation, Green = Preserved Canopy).

---

## Docker & Cloud Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full AWS, GCP, and Kubernetes deployment instructions.

### Run via Docker & Docker Compose
```bash
# Launch the full web UI and API stack with one command:
docker compose up

# Streamlit dashboard: http://localhost:8501
# FastAPI interactive Swagger docs: http://localhost:8000/docs

# Or run one-off CLI audits in Docker:
docker run --rm -v $(pwd):/data argus-eudr-auditor:latest audit farm_parcel.geojson --pdf certificate.pdf
```
