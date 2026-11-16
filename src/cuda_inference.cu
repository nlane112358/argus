#include "inference.hpp"
#include <cuda_runtime.h>
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <cmath>

__global__ void evaluateDeforestationKernel(const float* __restrict__ input, int totalPixels, float* outputScore) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx < totalPixels) {
        float val = input[idx];
        if (val < 0.15f) {
            atomicAdd(outputScore, 1.0f);
        }
    }
}

void runInference(const float* h_data, int width, int height, int bands, float* h_score) {
    if (!h_data || !h_score || width <= 0 || height <= 0 || bands <= 0) {
        throw std::invalid_argument("Inference requires a non-empty raster patch and score output.");
    }

    size_t bytes = static_cast<size_t>(width) * height * bands * sizeof(float);
    float* d_input = nullptr;
    float* d_score = nullptr;
    float h_accumScore = 0.0f;

    cudaMalloc(&d_input, bytes);
    cudaMalloc(&d_score, sizeof(float));

    cudaMemcpy(d_input, h_data, bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_score, &h_accumScore, sizeof(float), cudaMemcpyHostToDevice);

    int totalPixels = width * height * bands;
    int threadsPerBlock = 256;
    int blocks = (totalPixels + threadsPerBlock - 1) / threadsPerBlock;

    evaluateDeforestationKernel<<<blocks, threadsPerBlock>>>(d_input, totalPixels, d_score);
    cudaDeviceSynchronize();

    cudaMemcpy(&h_accumScore, d_score, sizeof(float), cudaMemcpyDeviceToHost);
    *h_score = h_accumScore / static_cast<float>(width * height);

    cudaFree(d_input);
    cudaFree(d_score);
}

__global__ void evaluateBiTemporalKernel(
    const float* __restrict__ baseRed,
    const float* __restrict__ baseNIR,
    const float* __restrict__ currRed,
    const float* __restrict__ currNIR,
    size_t planeSize,
    float baselineThreshold,
    float degradedThreshold,
    float deltaThreshold,
    unsigned long long* d_baselineForestCount,
    unsigned long long* d_deforestedCount,
    float* d_sumBaseNDVI,
    float* d_sumCurrNDVI,
    float* d_sumDeltaNDVI
) {
    size_t idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx < planeSize) {
        float rBase = baseRed[idx];
        float nBase = baseNIR[idx];
        float rCurr = currRed[idx];
        float nCurr = currNIR[idx];
        const float eps = 1e-6f;

        float ndviBase = (nBase - rBase) / (nBase + rBase + eps);
        float ndviCurr = (nCurr - rCurr) / (nCurr + rCurr + eps);
        ndviBase = fmaxf(-1.0f, fminf(1.0f, ndviBase));
        ndviCurr = fmaxf(-1.0f, fminf(1.0f, ndviCurr));
        float deltaNDVI = ndviCurr - ndviBase;

        atomicAdd(d_sumBaseNDVI, ndviBase);
        atomicAdd(d_sumCurrNDVI, ndviCurr);
        atomicAdd(d_sumDeltaNDVI, deltaNDVI);

        if (ndviBase >= baselineThreshold) {
            atomicAdd(d_baselineForestCount, 1ULL);
            if (ndviCurr <= degradedThreshold || deltaNDVI <= deltaThreshold) {
                atomicAdd(d_deforestedCount, 1ULL);
            }
        }
    }
}

AuditReport evaluateBiTemporalEUDR(
    const float* baselineData,
    const float* currentData,
    int width,
    int height,
    int bands,
    double pixelAreaM2,
    const BandConfig& bandConfig,
    const EUDRConfig& eudrConfig
) {
    if (!baselineData || !currentData || width <= 0 || height <= 0 || bands <= 0) {
        throw std::invalid_argument("Invalid raster patch input buffers for bi-temporal evaluation.");
    }
    if (bandConfig.redBandIndex < 0 || bandConfig.redBandIndex >= bands ||
        bandConfig.nirBandIndex < 0 || bandConfig.nirBandIndex >= bands) {
        throw std::invalid_argument("Specified Red or NIR band index is out of bounds for the raster.");
    }

    AuditReport report;
    report.patchWidth = width;
    report.patchHeight = height;

    size_t planeSize = static_cast<size_t>(width) * height;
    size_t planeBytes = planeSize * sizeof(float);

    const float* h_baseRed = baselineData + (bandConfig.redBandIndex * planeSize);
    const float* h_baseNIR = baselineData + (bandConfig.nirBandIndex * planeSize);
    const float* h_currRed = currentData + (bandConfig.redBandIndex * planeSize);
    const float* h_currNIR = currentData + (bandConfig.nirBandIndex * planeSize);

    float *d_baseRed, *d_baseNIR, *d_currRed, *d_currNIR;
    cudaMalloc(&d_baseRed, planeBytes);
    cudaMalloc(&d_baseNIR, planeBytes);
    cudaMalloc(&d_currRed, planeBytes);
    cudaMalloc(&d_currNIR, planeBytes);

    cudaMemcpy(d_baseRed, h_baseRed, planeBytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_baseNIR, h_baseNIR, planeBytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_currRed, h_currRed, planeBytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_currNIR, h_currNIR, planeBytes, cudaMemcpyHostToDevice);

    unsigned long long *d_baseForest, *d_deforest;
    float *d_sumBase, *d_sumCurr, *d_sumDelta;
    cudaMalloc(&d_baseForest, sizeof(unsigned long long));
    cudaMalloc(&d_deforest, sizeof(unsigned long long));
    cudaMalloc(&d_sumBase, sizeof(float));
    cudaMalloc(&d_sumCurr, sizeof(float));
    cudaMalloc(&d_sumDelta, sizeof(float));

    cudaMemset(d_baseForest, 0, sizeof(unsigned long long));
    cudaMemset(d_deforest, 0, sizeof(unsigned long long));
    cudaMemset(d_sumBase, 0, sizeof(float));
    cudaMemset(d_sumCurr, 0, sizeof(float));
    cudaMemset(d_sumDelta, 0, sizeof(float));

    int threads = 256;
    int blocks = (planeSize + threads - 1) / threads;

    evaluateBiTemporalKernel<<<blocks, threads>>>(
        d_baseRed, d_baseNIR, d_currRed, d_currNIR,
        planeSize,
        eudrConfig.baselineForestNDVIThreshold,
        eudrConfig.currentDegradedNDVIThreshold,
        eudrConfig.deltaNDVIThreshold,
        d_baseForest, d_deforest,
        d_sumBase, d_sumCurr, d_sumDelta
    );
    cudaDeviceSynchronize();

    unsigned long long h_baseForest = 0, h_deforest = 0;
    float h_sumBase = 0.0f, h_sumCurr = 0.0f, h_sumDelta = 0.0f;

    cudaMemcpy(&h_baseForest, d_baseForest, sizeof(unsigned long long), cudaMemcpyDeviceToHost);
    cudaMemcpy(&h_deforest, d_deforest, sizeof(unsigned long long), cudaMemcpyDeviceToHost);
    cudaMemcpy(&h_sumBase, d_sumBase, sizeof(float), cudaMemcpyDeviceToHost);
    cudaMemcpy(&h_sumCurr, d_sumCurr, sizeof(float), cudaMemcpyDeviceToHost);
    cudaMemcpy(&h_sumDelta, d_sumDelta, sizeof(float), cudaMemcpyDeviceToHost);

    cudaFree(d_baseRed);
    cudaFree(d_baseNIR);
    cudaFree(d_currRed);
    cudaFree(d_currNIR);
    cudaFree(d_baseForest);
    cudaFree(d_deforest);
    cudaFree(d_sumBase);
    cudaFree(d_sumCurr);
    cudaFree(d_sumDelta);

    report.meanBaselineNDVI = h_sumBase / static_cast<float>(planeSize);
    report.meanCurrentNDVI = h_sumCurr / static_cast<float>(planeSize);
    report.meanDeltaNDVI = h_sumDelta / static_cast<float>(planeSize);

    double pixelAreaHa = pixelAreaM2 / 10000.0;
    report.baselineForestHectares = h_baseForest * pixelAreaHa;
    report.deforestedHectares = h_deforest * pixelAreaHa;

    if (h_baseForest > 0) {
        report.canopyLossPercentage = static_cast<float>(
            (static_cast<double>(h_deforest) / h_baseForest) * 100.0);
    } else {
        report.canopyLossPercentage = 0.0f;
    }

    if (report.canopyLossPercentage > eudrConfig.violationTolerancePercent) {
        report.isCompliant = false;
        report.statusMessage = "VIOLATION_CONFIRMED (Post-2020 Canopy Loss Exceeds EUDR Tolerance)";
    } else {
        report.isCompliant = true;
        report.statusMessage = "COMPLIANT (No Prohibited Canopy Loss Detected Post-2020)";
    }

    return report;
}
