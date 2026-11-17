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
- **Optical Epoch Comparison**: Loads parcel-clipped Sentinel-2 true-color images for the 2020 baseline and recent imagery, plus a canopy-decline overlay. Each georeferenced image can be placed over the dashboard map with an opacity control.
- **Statutory EU TRACES-NT XML/JSON Engine**: Exports legally valid Due Diligence Statements (DDS) conforming to European Commission Regulation (EU) 2023/1115 (EUDR) with SHA-256 eIDAS cryptographic electronic seals.
- **Bi-Temporal Epoch Swipe Comparator**: Interactive browser split-slider comparing Dec 31, 2020 EUDR baseline canopy against current audit passes in spectral NDVI or high-resolution RGB.
- **Bulk Smallholder Ingestion & Topology Engine**: Ingests cooperative portfolios with automated coordinate winding correction and geometry self-intersection repair.
- **Enterprise-Ready**: Emits standardized exit codes (`0` for compliant, `2` for violation) and machine-readable JSON for direct integration into SAP, Oracle, and supply chain ERPs.
- **Cloud Containerized**: Production Docker container compatible with AWS (ECS/EKS/Batch) and GCP (GKE/Cloud Run).

### Enterprise Integrations

| Capability | Module | Endpoints (Go `:8080` / FastAPI `:8000`) |
|---|---|---|
| **Optical epoch comparison**: parcel-clipped Sentinel-2 baseline and current RGB images, NDVI decline overlay, and map-layer controls | `scripts/argus_optical_compare.py` · `python/visualizer.py` | `POST /api/optical/compare` |
| **High-resolution fallback**: plots under 0.5 ha are routed to PlanetScope 3m (NICFI), and plots under 0.2 ha to Airbus Pléiades Neo 0.5m, which cuts Sentinel-2 edge-pixel contamination. Supports manual tier override. | `python/highres_provider.py` | `GET /api/sensor/evaluate?ha=0.3&tier=auto` · `GET /api/v1/sensor/evaluate` |
| **Calibrated RTC SAR**: Sentinel-1 γ⁰ backscatter in dB, 5×5 Enhanced Lee speckle filter, VV/VH Radar Vegetation Index, and all-weather canopy disturbance flag (Δγ⁰<sub>VH</sub> < −2.5 dB) | `scripts/argus_sar_compare.py` | `POST /api/sar/compare` (`metadata.rtc_analytics`) |
| **Direct TRACES-NT submission**: DDS payload builder, SHA-256 seal, `YYCC…` reference and receipt | `server/traces_connector.py` | `POST /api/traces/direct-submit` · `POST /api/v1/traces/direct-submit` |
| **SAP S/4HANA gate**: PO pre-shipment screening that returns `BAPI_RET2` (release code `01` approved / `03` blocked) | `server/erp_connectors.py` | `POST /api/erp/sap/po-verify` · `POST /api/v1/erp/sap/po-verify` |
| **Oracle Cloud SCM / GTM**: transaction screening that returns `PASSED` / `HOLD_REGULATORY_RESTRICTION` | `server/erp_connectors.py` | `POST /api/erp/oracle/shipment-clearance` · `POST /api/v1/erp/oracle/shipment-clearance` |

In the dashboard, these appear as the sensor resolution indicator and selector in the Earth Observation header, the RTC strip under the SAR comparison, **Push to EU TRACES-NT** in the dossier modal, and **ERP Hub** in the top bar.

> **Status:** The connectors run in **sandbox mode**. They produce payloads and response shapes that follow each target system's format, but they generate receipts locally. They do not call the live EU TRACES-NT gateway, Planet/Airbus tasking APIs, SAP, or Oracle. Going live needs EU Login/TRACES API credentials, Planet and Airbus OneAtlas API keys, and SAP BTP / Oracle OIC connection config. The RTC SAR path currently derives γ⁰ from Earth Search GRD quicklooks; for fully calibrated results, switch it to the `sentinel-1-rtc` collection on Planetary Computer.

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

### 2. Datadog DRUIDS APM Dashboard & Web Services
Launch the Datadog-standard APM observability dashboard or REST API:
```bash
# Launch Datadog DRUIDS Orbital APM dashboard (http://localhost:8080):
./bin/argus serve-apm
# or: go run main.go

# Launch FastAPI REST API server (http://localhost:8000 / http://localhost:8000/docs):
./bin/argus serve-api
```

The dashboard's **Collect SAR pair** action searches Earth Search for a Sentinel-1 GRD baseline near the 2020 cutoff and a recent scene on the same orbit track. It displays both source quicklooks and a visual pixel difference. The default parcel outlines and portfolio statuses are illustrative; upload a GeoJSON boundary for a parcel-specific search. The quicklook difference is for visual review and is not a calibrated backscatter change product or a compliance determination.

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
# Launch the FastAPI service:
docker compose up api

# FastAPI interactive Swagger docs: http://localhost:8000/docs

# Or run one-off CLI audits in Docker:
docker run --rm -v $(pwd):/data argus-eudr-auditor:latest audit farm_parcel.geojson --pdf certificate.pdf
```
