#include "inference.hpp"
#include <stdexcept>
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
