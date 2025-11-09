# The following five lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

set(ALL_LIBS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include/esp-idf-lib/components)

# Exclude problematic component (pcf8574)
file(GLOB CHILD_COMPONENTS LIST_DIRECTORIES true ${ALL_LIBS_DIR}/*)
list(REMOVE_ITEM CHILD_COMPONENTS ${ALL_LIBS_DIR}/pcf8574)

set(EXTRA_COMPONENT_DIRS ${CHILD_COMPONENTS})

project(esp32-project)
