#include <iostream>
#include <iomanip>
#include <string>
#include <vector>
#include "gdal_processor.hpp"
#include "inference.hpp"

void printUsage(const char* progName) {
    std::cerr << "ARGUS - Automated Satellite ESG & EUDR Compliance Auditor\n"
              << "========================================================\n"
              << "Usage:\n"
              << "  Bi-temporal EUDR Audit (Recommended):\n"
              << "    " << progName << " <polygon.geojson> <baseline_2020.tif> <current.tif> [options]\n\n"
              << "  Single-Epoch Scan (Legacy):\n"
              << "    " << progName << " <polygon.geojson> <raster.tif>\n\n"
              << "Options:\n"
              << "  --json              Output audit report in JSON format for automated ERP integration\n"
              << "  --red <band_idx>    1-based index of Red band (default: 3)\n"
              << "  --nir <band_idx>    1-based index of NIR band (default: 4)\n"
              << "  --tolerance <pct>   Max allowable canopy loss % before violation (default: 2.0)\n";
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        printUsage(argv[0]);
        return 1;
    }

    std::string vectorPath = argv[1];
    std::string firstRasterPath = argv[2];

    // Single-Epoch legacy mode
    if (argc == 3) {
        try {
            std::cout << "[*] Initializing GDAL and extracting spatial window...\n";
            GDALProcessor processor;
            RasterPatch patch = processor.extractPatch(vectorPath, firstRasterPath);
            std::cout << "[+] Extracted patch: " << patch.width << "x" << patch.height 
                      << " pixels across " << patch.bands << " bands.\n";

            std::cout << "[*] Executing inference pipeline...\n";
            float auditScore = 0.0f;
            runInference(patch.data.data(), patch.width, patch.height, patch.bands, &auditScore);

            std::cout << "\n=== ESG AUDIT REPORT ==\n";
            std::cout << "Target Asset Polygon: " << vectorPath << "\n";
            std::cout << "Raster Source Evaluated: " << firstRasterPath << "\n";
            std::cout << "Calculated Degradation Risk Index: " << auditScore << "\n";
            std::cout << "Status: " << (auditScore > 0.05f ? "FLAGGED (Potential EUDR Violation)" : "COMPLIANT") << "\n";
            return (auditScore > 0.05f) ? 2 : 0;
        } catch (const std::exception& e) {
            std::cerr << "[!] Error: " << e.what() << "\n";
            return 1;
        }
    }

    // Bi-temporal EUDR audit mode
    std::string baselineRasterPath = argv[2];
    std::string currentRasterPath = argv[3];

    // Auto-detect argument order if (baseline.tif, target.tif, polygon.geojson) is passed
    if ((vectorPath.rfind(".tif") != std::string::npos || vectorPath.rfind(".vrt") != std::string::npos) &&
        (currentRasterPath.rfind(".geojson") != std::string::npos || currentRasterPath.rfind(".json") != std::string::npos)) {
        vectorPath = argv[3];
        baselineRasterPath = argv[1];
        currentRasterPath = argv[2];
    }

    bool outputJson = false;
    BandConfig bandConfig;
    bandConfig.redBandIndex = 2; // Default Band 3 (0-indexed 2)
    bandConfig.nirBandIndex = 3; // Default Band 4 (0-indexed 3)

    EUDRConfig eudrConfig;
    eudrConfig.violationTolerancePercent = 2.0f;

    for (int i = 4; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json") {
            outputJson = true;
        } else if (arg == "--red" && i + 1 < argc) {
            bandConfig.redBandIndex = std::stoi(argv[++i]) - 1;
        } else if (arg == "--nir" && i + 1 < argc) {
            bandConfig.nirBandIndex = std::stoi(argv[++i]) - 1;
        } else if (arg == "--tolerance" && i + 1 < argc) {
            eudrConfig.violationTolerancePercent = std::stof(argv[++i]);
        }
    }

    try {
        GDALProcessor processor;

        if (!outputJson) {
            std::cout << "[*] Ingesting vector asset and calculating parcel boundaries...\n";
        }
        ParcelMetadata meta = processor.getParcelMetadata(vectorPath, baselineRasterPath);

        if (!outputJson) {
            std::cout << "[*] Extracting baseline raster patch (2020 Cutoff Epoch)...\n";
        }
        RasterPatch baselinePatch = processor.extractPatch(vectorPath, baselineRasterPath);

        if (!outputJson) {
            std::cout << "[*] Extracting current raster patch and aligning spatial grid...\n";
        }
        // Resample current patch to match baseline dimensions exactly
        RasterPatch currentPatch = processor.extractPatch(
            vectorPath, currentRasterPath, baselinePatch.width, baselinePatch.height);

        // Adjust band indices if fewer bands are present
        if (baselinePatch.bands < 4 && bandConfig.nirBandIndex >= baselinePatch.bands) {
            if (baselinePatch.bands == 2) {
                bandConfig.redBandIndex = 0;
                bandConfig.nirBandIndex = 1;
            }
        }

        double pixelAreaM2 = baselinePatch.pixelSizeX * baselinePatch.pixelSizeY;
        if (pixelAreaM2 <= 0.0) {
            pixelAreaM2 = 100.0; // Default 10m x 10m Sentinel-2 pixel
        }

        if (!outputJson) {
            std::cout << "[*] Running bi-temporal spectral change analysis (NDVI differential)...\n";
        }

        AuditReport report = evaluateBiTemporalEUDR(
            baselinePatch.data.data(),
            currentPatch.data.data(),
            baselinePatch.width,
            baselinePatch.height,
            baselinePatch.bands,
            pixelAreaM2,
            bandConfig,
            eudrConfig
        );

        report.assetId = meta.assetId;
        report.commodity = meta.commodity;
        report.vectorPath = vectorPath;
        report.baselineRasterPath = baselineRasterPath;
        report.currentRasterPath = currentRasterPath;
        report.parcelAreaHectares = meta.areaHectares;

        if (outputJson) {
            std::cout << std::fixed << std::setprecision(4);
            std::cout << "{\n"
                      << "  \"audit_standard\": \"EUDR (Regulation (EU) 2023/1115)\",\n"
                      << "  \"asset_id\": \"" << report.assetId << "\",\n"
                      << "  \"commodity\": \"" << report.commodity << "\",\n"
                      << "  \"polygon_file\": \"" << report.vectorPath << "\",\n"
                      << "  \"baseline_raster\": \"" << report.baselineRasterPath << "\",\n"
                      << "  \"current_raster\": \"" << report.currentRasterPath << "\",\n"
                      << "  \"parcel_area_ha\": " << report.parcelAreaHectares << ",\n"
                      << "  \"baseline_forest_ha\": " << report.baselineForestHectares << ",\n"
                      << "  \"deforested_ha\": " << report.deforestedHectares << ",\n"
                      << "  \"canopy_loss_percent\": " << report.canopyLossPercentage << ",\n"
                      << "  \"tolerance_percent\": " << eudrConfig.violationTolerancePercent << ",\n"
                      << "  \"mean_baseline_ndvi\": " << report.meanBaselineNDVI << ",\n"
                      << "  \"mean_current_ndvi\": " << report.meanCurrentNDVI << ",\n"
                      << "  \"mean_delta_ndvi\": " << report.meanDeltaNDVI << ",\n"
                      << "  \"is_compliant\": " << (report.isCompliant ? "true" : "false") << ",\n"
                      << "  \"verdict\": \"" << report.statusMessage << "\"\n"
                      << "}\n";
        } else {
            std::cout << "\n"
                      << "================================================================================\n"
                      << "                 ARGUS: ESG & EUDR COMPLIANCE AUDIT REPORT\n"
                      << "================================================================================\n"
                      << "Target Asset Polygon   : " << report.vectorPath << "\n"
                      << "Asset Identifier       : " << report.assetId << "\n"
                      << "Commodity Audited      : " << report.commodity << "\n"
                      << "Total Parcel Area      : " << std::fixed << std::setprecision(2) << report.parcelAreaHectares << " Hectares\n"
                      << "--------------------------------------------------------------------------------\n"
                      << "Baseline Epoch (2020)  : " << report.baselineRasterPath << "\n"
                      << "Current Epoch          : " << report.currentRasterPath << "\n"
                      << "Extracted Grid Window  : " << report.patchWidth << " x " << report.patchHeight << " pixels\n"
                      << "--------------------------------------------------------------------------------\n"
                      << "Mean Baseline NDVI     : " << std::setprecision(3) << report.meanBaselineNDVI << "\n"
                      << "Mean Current NDVI      : " << report.meanCurrentNDVI << "\n"
                      << "Mean Delta NDVI        : " << report.meanDeltaNDVI << "\n"
                      << "Baseline Forest Canopy : " << std::setprecision(2) << report.baselineForestHectares << " Hectares\n"
                      << "Detected Canopy Loss   : " << report.deforestedHectares << " Hectares (" 
                      << std::setprecision(2) << report.canopyLossPercentage << "% of Baseline Forest)\n"
                      << "Tolerance Threshold    : " << eudrConfig.violationTolerancePercent << "%\n"
                      << "--------------------------------------------------------------------------------\n"
                      << "AUDIT VERDICT          : " << (report.isCompliant ? "[PASSED] " : "[FLAGGED] ") << report.statusMessage << "\n"
                      << "================================================================================\n";
        }

        return report.isCompliant ? 0 : 2;

    } catch (const std::exception& e) {
        std::cerr << "[!] Error: " << e.what() << "\n";
        return 1;
    }
}
