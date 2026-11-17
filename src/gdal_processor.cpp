#include "gdal_processor.hpp"
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <cmath>
#include <limits>
#include <ogr_spatialref.h>
#include <ogr_api.h>
#include <cpl_conv.h>

GDALProcessor::GDALProcessor() {
    GDALAllRegister();
    OGRRegisterAll();

    // High-performance Cloud-Optimized GeoTIFF (COG) HTTP/2 tuning
    CPLSetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR");
    CPLSetConfigOption("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES");
    CPLSetConfigOption("GDAL_HTTP_MULTIPLEX", "YES");
    CPLSetConfigOption("GDAL_HTTP_VERSION", "2");
    CPLSetConfigOption("VSI_CACHE", "YES");
    CPLSetConfigOption("VSI_CACHE_SIZE", "67108864"); // 64 MB chunk cache
    CPLSetConfigOption("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.vrt,.json");
}

GDALProcessor::~GDALProcessor() {}

ParcelMetadata GDALProcessor::getParcelMetadata(const std::string& vectorPath, const std::string& referenceRasterPath) {
    ParcelMetadata meta;

    GDALDataset* poVectorDS = static_cast<GDALDataset*>(
        GDALOpenEx(vectorPath.c_str(), GDAL_OF_VECTOR, nullptr, nullptr, nullptr));
    if (!poVectorDS) {
        throw std::runtime_error("Failed to open vector file: " + vectorPath);
    }

    OGRLayer* poLayer = poVectorDS->GetLayer(0);
    if (!poLayer) {
        GDALClose(poVectorDS);
        throw std::runtime_error("Vector file contains no layers: " + vectorPath);
    }

    // Determine target SRS from reference raster if available
    const OGRSpatialReference* poRasterSRS = nullptr;
    OGRSpatialReference oRasterSRS;
    GDALDataset* poRasterDS = static_cast<GDALDataset*>(GDALOpen(referenceRasterPath.c_str(), GA_ReadOnly));
    if (poRasterDS) {
        poRasterSRS = poRasterDS->GetSpatialRef();
        if (!poRasterSRS) {
            const char* pszWkt = poRasterDS->GetProjectionRef();
            if (pszWkt && pszWkt[0] != '\0') {
                oRasterSRS.importFromWkt(pszWkt);
                poRasterSRS = &oRasterSRS;
            }
        }
    }

    const OGRSpatialReference* poVectorSRS = poLayer->GetSpatialRef();
    OGRSpatialReference oDefaultVectorSRS;
    if (!poVectorSRS) {
        oDefaultVectorSRS.SetWellKnownGeogCS("WGS84");
        oDefaultVectorSRS.SetAxisMappingStrategy(OAMS_TRADITIONAL_GIS_ORDER);
        poVectorSRS = &oDefaultVectorSRS;
    }

    OGRCoordinateTransformation* poCT = nullptr;
    if (poVectorSRS && poRasterSRS && !poVectorSRS->IsSame(poRasterSRS)) {
        poCT = OGRCreateCoordinateTransformation(poVectorSRS, poRasterSRS);
    }

    poLayer->ResetReading();
    OGRFeature* poFeature = nullptr;
    double totalAreaM2 = 0.0;
    bool metadataExtracted = false;

    while ((poFeature = poLayer->GetNextFeature()) != nullptr) {
        meta.featureCount++;

        if (!metadataExtracted) {
            int idxAsset = poFeature->GetFieldIndex("asset_id");
            if (idxAsset >= 0 && poFeature->IsFieldSetAndNotNull(idxAsset)) {
                meta.assetId = poFeature->GetFieldAsString(idxAsset);
            }
            int idxComm = poFeature->GetFieldIndex("commodity");
            if (idxComm >= 0 && poFeature->IsFieldSetAndNotNull(idxComm)) {
                meta.commodity = poFeature->GetFieldAsString(idxComm);
            }
            metadataExtracted = true;
        }

        OGRGeometry* poGeom = poFeature->GetGeometryRef();
        if (poGeom) {
            OGRGeometry* poGeomTrans = poGeom->clone();
            if (poCT) {
                poGeomTrans->transform(poCT);
            }
            // For projected coordinate systems in meters (e.g. UTM), OGR_G_Area returns square meters
            totalAreaM2 += OGR_G_Area(reinterpret_cast<OGRGeometryH>(poGeomTrans));
            OGRGeometryFactory::destroyGeometry(poGeomTrans);
        }
        OGRFeature::DestroyFeature(poFeature);
    }

    if (poCT) {
        OCTDestroyCoordinateTransformation(poCT);
    }
    if (poRasterDS) {
        GDALClose(poRasterDS);
    }
    GDALClose(poVectorDS);

    // Convert square meters to hectares (1 ha = 10,000 m2)
    meta.areaHectares = totalAreaM2 / 10000.0;
    return meta;
}

RasterPatch GDALProcessor::extractPatch(const std::string& vectorPath, const std::string& rasterPath, int targetWidth, int targetHeight) {
    GDALDataset* poVectorDS = static_cast<GDALDataset*>(
        GDALOpenEx(vectorPath.c_str(), GDAL_OF_VECTOR, nullptr, nullptr, nullptr));
    if (!poVectorDS) {
        throw std::runtime_error("Failed to open vector file: " + vectorPath);
    }

    OGRLayer* poLayer = poVectorDS->GetLayer(0);
    if (!poLayer) {
        GDALClose(poVectorDS);
        throw std::runtime_error("Vector file contains no layers: " + vectorPath);
    }

    GDALDataset* poRasterDS = static_cast<GDALDataset*>(GDALOpen(rasterPath.c_str(), GA_ReadOnly));
    if (!poRasterDS) {
        GDALClose(poVectorDS);
        throw std::runtime_error("Failed to open raster file: " + rasterPath);
    }

    // Determine Vector and Raster Spatial Reference Systems (CRS)
    const OGRSpatialReference* poVectorSRS = poLayer->GetSpatialRef();
    OGRSpatialReference oDefaultVectorSRS;
    if (!poVectorSRS) {
        // RFC 7946 GeoJSON defaults to EPSG:4326 (WGS84)
        oDefaultVectorSRS.SetWellKnownGeogCS("WGS84");
        oDefaultVectorSRS.SetAxisMappingStrategy(OAMS_TRADITIONAL_GIS_ORDER);
        poVectorSRS = &oDefaultVectorSRS;
    }

    const OGRSpatialReference* poRasterSRS = poRasterDS->GetSpatialRef();
    OGRSpatialReference oRasterSRS;
    if (!poRasterSRS) {
        const char* pszWkt = poRasterDS->GetProjectionRef();
        if (pszWkt && pszWkt[0] != '\0') {
            oRasterSRS.importFromWkt(pszWkt);
            poRasterSRS = &oRasterSRS;
        }
    }

    // Set up coordinate transformation if vector and raster coordinate systems differ
    OGRCoordinateTransformation* poCT = nullptr;
    if (poVectorSRS && poRasterSRS && !poVectorSRS->IsSame(poRasterSRS)) {
        poCT = OGRCreateCoordinateTransformation(poVectorSRS, poRasterSRS);
        if (!poCT) {
            std::cerr << "[!] Warning: Unable to create coordinate transformation from vector CRS to raster CRS.\n";
        }
    }

    // Accumulate the combined bounding envelope across all features in the vector layer
    OGREnvelope sCombinedEnvelope;
    bool bEnvelopeInitialized = false;

    poLayer->ResetReading();
    OGRFeature* poFeature = nullptr;
    while ((poFeature = poLayer->GetNextFeature()) != nullptr) {
        OGRGeometry* poGeom = poFeature->GetGeometryRef();
        if (poGeom) {
            OGRGeometry* poGeomTransformed = poGeom->clone();
            if (poCT) {
                poGeomTransformed->transform(poCT);
            }
            OGREnvelope sEnv;
            poGeomTransformed->getEnvelope(&sEnv);
            if (!bEnvelopeInitialized) {
                sCombinedEnvelope = sEnv;
                bEnvelopeInitialized = true;
            } else {
                sCombinedEnvelope.Merge(sEnv);
            }
            OGRGeometryFactory::destroyGeometry(poGeomTransformed);
        }
        OGRFeature::DestroyFeature(poFeature);
    }

    if (poCT) {
        OCTDestroyCoordinateTransformation(poCT);
    }
    GDALClose(poVectorDS);

    if (!bEnvelopeInitialized) {
        GDALClose(poRasterDS);
        throw std::runtime_error("No valid features or geometries found in vector layer.");
    }

    // Fetch and invert GeoTransform to map world coordinates to raster pixel space
    double adfGeoTransform[6];
    if (poRasterDS->GetGeoTransform(adfGeoTransform) != CE_None) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Raster does not have a valid GeoTransform: " + rasterPath);
    }

    double invGeoTransform[6];
    if (!GDALInvGeoTransform(adfGeoTransform, invGeoTransform)) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Failed to invert GeoTransform for raster: " + rasterPath);
    }

    // Map all four corners of the bounding box to pixel coordinates to handle any orientation/rotation
    double cornerX[4] = {sCombinedEnvelope.MinX, sCombinedEnvelope.MinX, sCombinedEnvelope.MaxX, sCombinedEnvelope.MaxX};
    double cornerY[4] = {sCombinedEnvelope.MinY, sCombinedEnvelope.MinY, sCombinedEnvelope.MinY, sCombinedEnvelope.MaxY};

    double minCol = std::numeric_limits<double>::max();
    double maxCol = std::numeric_limits<double>::lowest();
    double minRow = std::numeric_limits<double>::max();
    double maxRow = std::numeric_limits<double>::lowest();

    for (int i = 0; i < 4; ++i) {
        double col = invGeoTransform[0] + cornerX[i] * invGeoTransform[1] + cornerY[i] * invGeoTransform[2];
        double row = invGeoTransform[3] + cornerX[i] * invGeoTransform[4] + cornerY[i] * invGeoTransform[5];
        minCol = std::min(minCol, col);
        maxCol = std::max(maxCol, col);
        minRow = std::min(minRow, row);
        maxRow = std::max(maxRow, row);
    }

    int nXOff = static_cast<int>(std::floor(minCol));
    int nYOff = static_cast<int>(std::floor(minRow));
    int nXEnd = static_cast<int>(std::ceil(maxCol));
    int nYEnd = static_cast<int>(std::ceil(maxRow));

    int rasterWidth = poRasterDS->GetRasterXSize();
    int rasterHeight = poRasterDS->GetRasterYSize();

    // Verify spatial intersection
    if (nXEnd < 0 || nXOff >= rasterWidth || nYEnd < 0 || nYOff >= rasterHeight) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Vector polygon envelope does not intersect raster boundaries.");
    }

    // Clamp coordinates to raster bounds to prevent buffer overflows
    nXOff = std::max(0, nXOff);
    nYOff = std::max(0, nYOff);
    nXEnd = std::min(rasterWidth - 1, nXEnd);
    nYEnd = std::min(rasterHeight - 1, nYEnd);

    int nWidth = nXEnd - nXOff + 1;
    int nHeight = nYEnd - nYOff + 1;

    if (nWidth <= 0 || nHeight <= 0) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Calculated raster patch dimensions are invalid.");
    }

    int nBands = poRasterDS->GetRasterCount();
    if (nBands <= 0) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Raster dataset contains no bands: " + rasterPath);
    }

    // Determine output patch buffer size (support resampling to target dimensions)
    int outWidth = (targetWidth > 0) ? targetWidth : nWidth;
    int outHeight = (targetHeight > 0) ? targetHeight : nHeight;

    RasterPatch patch;
    patch.width = outWidth;
    patch.height = outHeight;
    patch.bands = nBands;
    patch.pixelSizeX = std::abs(adfGeoTransform[1]);
    patch.pixelSizeY = std::abs(adfGeoTransform[5]);
    patch.data.resize(static_cast<size_t>(outWidth) * outHeight * nBands);

    CPLErr err = poRasterDS->RasterIO(
        GF_Read,
        nXOff, nYOff, nWidth, nHeight,
        patch.data.data(), outWidth, outHeight,
        GDT_Float32,
        nBands, nullptr,
        0, 0, 0
    );

    if (err != CE_None) {
        GDALClose(poRasterDS);
        throw std::runtime_error("Failed to read raster data window via RasterIO.");
    }

    GDALClose(poRasterDS);
    return patch;
}
