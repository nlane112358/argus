#pragma once
#include <string>
#include <vector>
#include <gdal_priv.h>
#include <ogrsf_frmts.h>

struct RasterPatch {
    int width = 0;
    int height = 0;
    int bands = 0;
    double pixelSizeX = 0.0;
    double pixelSizeY = 0.0;
    std::vector<float> data; // Band-Sequential: band * (width * height) + y * width + x
};

struct ParcelMetadata {
    std::string assetId = "UNKNOWN";
    std::string commodity = "UNSPECIFIED";
    double areaHectares = 0.0;
    int featureCount = 0;
};

class GDALProcessor {
public:
    GDALProcessor();
    ~GDALProcessor();

    // Extract parcel metadata (asset_id, commodity, area in hectares) from vector
    ParcelMetadata getParcelMetadata(const std::string& vectorPath, const std::string& referenceRasterPath);

    // Extract raster patch cropped to vector envelope. If targetWidth/targetHeight > 0, resamples to target dimensions.
    RasterPatch extractPatch(const std::string& vectorPath, const std::string& rasterPath, int targetWidth = 0, int targetHeight = 0);
};
