/**************************************************************************************************/
/**
 * @file utils.h
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief Utility functions and logging configuration
 *
 * @version 0.1
 * @date 2025-11-08
 *
 * @copyright Copyright (c) 2025
 *
 */
/**************************************************************************************************/

#ifndef UTILS_H
#define UTILS_H

/*------------------------------------------------------------------------------------------------*/
// HEADERS                                                                                        */
/*------------------------------------------------------------------------------------------------*/

#include "esp_log.h"

/*------------------------------------------------------------------------------------------------*/
// LOGGING CONFIGURATION                                                                          */
/*------------------------------------------------------------------------------------------------*/

// Define logging level - uncomment ONE of these:
#define ERROR_LOGGING_ONLY    1 // Only show errors and warnings
#define FULL_LOGGING          0 // Show all logs (info, debug, errors, warnings)

/*------------------------------------------------------------------------------------------------*/
// LOGGING MACROS                                                                                 */
/*------------------------------------------------------------------------------------------------*/

#if FULL_LOGGING
    // Full logging - all levels enabled
    #define LOG_INFO(tag, format, ...)    ESP_LOGI(tag, format, ##__VA_ARGS__)
    #define LOG_DEBUG(tag, format, ...)   ESP_LOGD(tag, format, ##__VA_ARGS__)
    #define LOG_WARN(tag, format, ...)    ESP_LOGW(tag, format, ##__VA_ARGS__)
    #define LOG_ERROR(tag, format, ...)   ESP_LOGE(tag, format, ##__VA_ARGS__)

#elif ERROR_LOGGING_ONLY
    // Error logging only - suppress info and debug
    #define LOG_INFO(tag, format, ...)    // No-op
    #define LOG_DEBUG(tag, format, ...)   ESP_LOGD(tag, format, ##__VA_ARGS__)
    #define LOG_WARN(tag, format, ...)    ESP_LOGW(tag, format, ##__VA_ARGS__)
    #define LOG_ERROR(tag, format, ...)   ESP_LOGE(tag, format, ##__VA_ARGS__)

#else
    // Default: Full logging
    #define LOG_INFO(tag, format, ...)    ESP_LOGI(tag, format, ##__VA_ARGS__)
    #define LOG_DEBUG(tag, format, ...)   ESP_LOGD(tag, format, ##__VA_ARGS__)
    #define LOG_WARN(tag, format, ...)    ESP_LOGW(tag, format, ##__VA_ARGS__)
    #define LOG_ERROR(tag, format, ...)   ESP_LOGE(tag, format, ##__VA_ARGS__)
#endif

#endif // UTILS_H
