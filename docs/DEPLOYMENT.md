# Argus Container Deployment Guide

This guide covers building and running the **Argus ESG & EUDR Compliance Auditor** container with full GDAL support and optional NVIDIA GPU acceleration across local machines, AWS, and GCP.

---

## 1. Quickstart: Building & Running Locally

### Build the Image
```bash
docker build -t argus-auditor:latest .
```

### Run an Autonomous Cloud Audit (CPU)
Mount your local directory containing the farm GeoJSON into `/data`:
```bash
docker run --rm -v $(pwd):/data argus-auditor:latest audit farm_parcel.geojson --save-png audit_map.png
```

### Run with NVIDIA GPU Acceleration
If you have an NVIDIA GPU and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed:
```bash
docker run --rm --gpus all -v $(pwd):/data argus-auditor:latest audit farm_parcel.geojson --save-png audit_map.png
```

### Run the Full Test Suite in Container
```bash
docker run --rm argus-auditor:latest test
```

---

## 2. Deploying on Amazon Web Services (AWS)

### Recommended AWS Instances
- **GPU Inference**: `g4dn.xlarge` (NVIDIA T4, ~$0.52/hr) or `g5.xlarge` (NVIDIA A10G, ~$1.00/hr).
- **CPU Batch Processing**: `c6i.xlarge` or `c7g.xlarge` (AWS Graviton3).

### Step 1: Push to Amazon Elastic Container Registry (ECR)
```bash
# 1. Authenticate Docker to your AWS ECR registry
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# 2. Create the repository (if not already created)
aws ecr create-repository --repository-name argus-auditor --region us-east-1

# 3. Tag and push
docker tag argus-auditor:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/argus-auditor:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/argus-auditor:latest
```

### Step 2: Running via AWS Batch or Amazon ECS
In your ECS / AWS Batch Task Definition:
1. Container image: `<AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/argus-auditor:latest`
2. Resource requirements: `1 GPU` (or 2-4 vCPUs).
3. Command override:
   ```json
   ["audit", "s3://my-supply-chain-bucket/parcels/supplier_001.geojson", "--save-png", "/data/audit_001.png"]
   ```

---

## 3. Deploying on Google Cloud Platform (GCP)

### Recommended GCP Instances
- **GPU Inference**: `n1-standard-4` with 1x NVIDIA T4 GPU, or `g2-standard-4` (NVIDIA L4).
- **CPU Inference**: `c3-standard-4` or `e2-standard-4`.

### Step 1: Push to Google Artifact Registry
```bash
# 1. Configure authentication
gcloud auth configure-docker us-central1-docker.pkg.dev

# 2. Tag and push
docker tag argus-auditor:latest us-central1-docker.pkg.dev/<PROJECT_ID>/argus-repo/argus-auditor:latest
docker push us-central1-docker.pkg.dev/<PROJECT_ID>/argus-repo/argus-auditor:latest
```

### Step 2: Running on Google Kubernetes Engine (GKE) with GPUs
Deploy as a Kubernetes `Job` or `Pod`:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: argus-audit-job
spec:
  template:
    spec:
      containers:
      - name: argus
        image: us-central1-docker.pkg.dev/<PROJECT_ID>/argus-repo/argus-auditor:latest
        args: ["audit", "/data/farm_parcel.geojson", "--save-png", "/data/audit_map.png"]
        resources:
          limits:
            nvidia.com/gpu: 1
        volumeMounts:
        - mountPath: /data
          name: parcel-data
      volumes:
      - name: parcel-data
        gcsFuse:
          bucket: my-eudr-compliance-bucket
      restartPolicy: Never
```

---

## 4. Key Performance Environment Variables

The container comes pre-configured with optimized GDAL streaming parameters:
- `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`: Prevents GDAL from issuing directory listing requests on S3/HTTPS endpoints, accelerating Cloud-Optimized GeoTIFF streaming by **~5x**.
- `GDAL_HTTP_TIMEOUT=30`: Ensures robust network handling over satellite COG HTTP Range connections.
- `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.vrt,.json`: Limits network requests to valid geospatial raster extensions.
