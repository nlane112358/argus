#pragma once
#include <string>

struct BandConfig {
    int redBandIndex = 2; // 0-indexed: Band 3 is Red (e.g. RGBN)
    int nirBandIndex = 3; // 0-indexed: Band 4 is NIR
};

struct EUDRConfig {
    float baselineForestNDVIThreshold = 0.50f; // Minimum baseline NDVI to qualify as forest canopy
    float currentDegradedNDVIThreshold = 0.30f; // Current NDVI threshold below which canopy is considered degraded
    float deltaNDVIThreshold = -0.20f;          // NDVI drop threshold indicating canopy loss
    float violationTolerancePercent = 2.0f;     // Flag violation if >2% of baseline forest is cleared
};

struct AuditReport {
    std::string assetId = "UNKNOWN";
    std::string commodity = "UNSPECIFIED";
    std::string vectorPath;
    std::string baselineRasterPath;
    std::string currentRasterPath;

    int patchWidth = 0;
    int patchHeight = 0;
    double parcelAreaHectares = 0.0;
    double baselineForestHectares = 0.0;
    double deforestedHectares = 0.0;
    float canopyLossPercentage = 0.0f;
    float meanBaselineNDVI = 0.0f;
    float meanCurrentNDVI = 0.0f;
    float meanDeltaNDVI = 0.0f;

    bool isCompliant = true;
    std::string statusMessage;
};

// Legacy single-epoch inference (backward compatibility)
void runInference(const float* data, int width, int height, int bands, float* score);

// Phase 2: Bi-temporal EUDR change detection inference
AuditReport evaluateBiTemporalEUDR(
    const float* baselineData,
    const float* currentData,
    int width,
    int height,
    int bands,
    double pixelAreaM2,
    const BandConfig& bandConfig,
    const EUDRConfig& eudrConfig
);
