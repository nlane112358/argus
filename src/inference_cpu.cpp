#include "inference.hpp"
#include <stdexcept>
#include <algorithm>
#include <cmath>
#include <cstddef>

void runInference(const float* data, int width, int height, int bands, float* score) {
    if (!data || !score || width <= 0 || height <= 0 || bands <= 0) {
        throw std::invalid_argument("Inference requires a non-empty raster patch and score output.");
    }

    size_t totalPixels = static_cast<size_t>(width) * height * bands;
    float accumScore = 0.0f;

    for (size_t i = 0; i < totalPixels; ++i) {
        if (data[i] < 0.15f) { // Simulated NDVI drop threshold for tree canopy loss
            accumScore += 1.0f;
        }
    }

    *score = accumScore / static_cast<float>(width * height);
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
    const float* baseRed = baselineData + (bandConfig.redBandIndex * planeSize);
    const float* baseNIR = baselineData + (bandConfig.nirBandIndex * planeSize);
    const float* currRed = currentData + (bandConfig.redBandIndex * planeSize);
    const float* currNIR = currentData + (bandConfig.nirBandIndex * planeSize);

    double sumBaselineNDVI = 0.0;
    double sumCurrentNDVI = 0.0;
    double sumDeltaNDVI = 0.0;

    size_t baselineForestPixels = 0;
    size_t deforestedPixels = 0;
    const float eps = 1e-6f;

    for (size_t i = 0; i < planeSize; ++i) {
        float rBase = baseRed[i];
        float nBase = baseNIR[i];
        float rCurr = currRed[i];
        float nCurr = currNIR[i];

        float ndviBase = (nBase - rBase) / (nBase + rBase + eps);
        float ndviCurr = (nCurr - rCurr) / (nCurr + rCurr + eps);

        // Clamp NDVI values to valid theoretical range [-1.0, 1.0]
        ndviBase = std::max(-1.0f, std::min(1.0f, ndviBase));
        ndviCurr = std::max(-1.0f, std::min(1.0f, ndviCurr));

        float deltaNDVI = ndviCurr - ndviBase;

        sumBaselineNDVI += ndviBase;
        sumCurrentNDVI += ndviCurr;
        sumDeltaNDVI += deltaNDVI;

        bool wasForest = (ndviBase >= eudrConfig.baselineForestNDVIThreshold);
        if (wasForest) {
            baselineForestPixels++;
            bool nowDegraded = (ndviCurr <= eudrConfig.currentDegradedNDVIThreshold) ||
                               (deltaNDVI <= eudrConfig.deltaNDVIThreshold);
            if (nowDegraded) {
                deforestedPixels++;
            }
        }
    }

    report.meanBaselineNDVI = static_cast<float>(sumBaselineNDVI / planeSize);
    report.meanCurrentNDVI = static_cast<float>(sumCurrentNDVI / planeSize);
    report.meanDeltaNDVI = static_cast<float>(sumDeltaNDVI / planeSize);

    double pixelAreaHa = pixelAreaM2 / 10000.0;
    report.baselineForestHectares = baselineForestPixels * pixelAreaHa;
    report.deforestedHectares = deforestedPixels * pixelAreaHa;

    if (baselineForestPixels > 0) {
        report.canopyLossPercentage = static_cast<float>(
            (static_cast<double>(deforestedPixels) / baselineForestPixels) * 100.0);
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
