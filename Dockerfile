# ==============================================================================
# ARGUS ESG & EUDR Compliance Auditor
# Multi-arch CUDA & GDAL Cloud Container with FastAPI & Streamlit
# Compatible with AWS (ECS/EKS/EC2 g4dn/g5) and GCP (GKE/Compute Engine/Cloud Run)
# ==============================================================================

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

# Prevent interactive prompts during apt package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/app/bin:${PATH}"

# Install core build tools, C++17 compilers, GDAL, and Python 3
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    ca-certificates \
    curl \
    git \
    libgdal-dev \
    gdal-bin \
    python3 \
    python3-dev \
    python3-pip \
    python3-numpy \
    python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Install FastAPI, Streamlit, and PDF generation dependencies
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# GDAL Cloud-Optimized GeoTIFF (COG) / vsicurl performance tuning
ENV GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR \
    GDAL_HTTP_TIMEOUT=30 \
    GDAL_HTTP_MAX_RETRY=5 \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.vrt,.json \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Copy application source code
COPY include/ /app/include/
COPY src/ /app/src/
COPY python/ /app/python/
COPY scripts/ /app/scripts/
COPY server/ /app/server/
COPY bin/ /app/bin/
COPY tests/ /app/tests/
COPY Makefile /app/Makefile
COPY CMakeLists.txt /app/CMakeLists.txt
COPY farm_parcel.geojson /app/farm_parcel.geojson

# Compile C++ and CUDA binaries
RUN make clean && make && chmod +x /app/bin/argus /app/scripts/argus_cloud_audit.py

# Create a shared data directory for mounting input GeoJSONs and output reports
RUN mkdir -p /data
WORKDIR /data

# Expose ports for FastAPI (8000) and Streamlit (8501)
EXPOSE 8000 8501

# Default entrypoint
ENTRYPOINT ["/app/bin/argus"]
CMD ["audit", "--help"]
