cmake_minimum_required(VERSION 3.18)
project(auditor LANGUAGES CXX)

include(CheckLanguage)
check_language(CUDA)
if(CMAKE_CUDA_COMPILER)
    enable_language(CUDA)
    set(INFERENCE_SOURCE src/cuda_inference.cu)
else()
    set(INFERENCE_SOURCE src/inference_cpu.cpp)
    message(STATUS "CUDA compiler not found; building the CPU inference fallback")
endif()

find_package(GDAL REQUIRED)

add_executable(esg_auditor
    src/main.cpp
    src/gdal_processor.cpp
    ${INFERENCE_SOURCE}
)

target_compile_features(esg_auditor PRIVATE cxx_std_17)
target_include_directories(esg_auditor PRIVATE include)
target_link_libraries(esg_auditor PRIVATE GDAL::GDAL)

if(CMAKE_CUDA_COMPILER)
    set_target_properties(esg_auditor PROPERTIES CUDA_STANDARD 17 CUDA_STANDARD_REQUIRED ON)
endif()
