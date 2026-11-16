#include <iostream>
#include "gdal_processor.hpp"
#include "inference.hpp"

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <supply_chain_polygon.geojson> <raster_image.tif>\n";
        return 1;
    }

    std::string vectorPath = argv[1];
    std::string rasterPath = argv[2];

    try {
        std::cout << "[*] Initializing GDAL and extracting spatial window...\n";
        GDALProcessor processor;
        RasterPatch patch = processor.extractPatch(vectorPath, rasterPath);
        std::cout << "[+] Extracted patch: " << patch.width << "x" << patch.height 
                  << " pixels across " << patch.bands << " bands.\n";

        std::cout << "[*] Executing inference pipeline...\n";
        float auditScore = 0.0f;
        runInference(patch.data.data(), patch.width, patch.height, patch.bands, &auditScore);

        std::cout << "\n=== ESG AUDIT REPORT ==\n";
        std::cout << "Target Asset Polygon: " << vectorPath << "\n";
        std::cout << "Raster Source Evaluated: " << rasterPath << "\n";
        std::cout << "Calculated Degradation Risk Index: " << auditScore << "\n";
        std::cout << "Status: " << (auditScore > 0.05f ? "FLAGGED (Potential EUDR Violation)" : "COMPLIANT") << "\n";

    } catch (const std::exception& e) {
        std::cerr << "[!] Error: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
