#include "inference.hpp"
#include <cuda_runtime.h>
#include <iostream>
#include <stdexcept>

// Simple CUDA kernel demonstrating parallel pixel evaluation / normalization
__global__ void evaluateDeforestationKernel(const float* __restrict__ input, int totalPixels, float* outputScore) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx < totalPixels) {
        // Example proxy logic: evaluate spectral index or threshold anomaly
        // Real implementations call TensorRT engine context enqueue here.
        float val = input[idx];
        if (val < 0.15f) { // Simulated NDVI drop threshold for tree canopy loss
            atomicAdd(outputScore, 1.0f);
        }
    }
}

void runInference(const float* h_data, int width, int height, int bands, float* h_score) {
    if (!h_data || !h_score || width <= 0 || height <= 0 || bands <= 0) {
        throw std::invalid_argument("Inference requires a non-empty raster patch and score output.");
    }

    size_t bytes = width * height * bands * sizeof(float);
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
    *h_score = h_accumScore / static_cast<float>(width * height); // Normalized index score

    cudaFree(d_input);
    cudaFree(d_score);
}
