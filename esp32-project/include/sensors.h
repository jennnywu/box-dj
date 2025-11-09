/**************************************************************************************************/
/**
 * @file sensors.h
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief Sensor data processing and management
 *
 * @version 0.1
 * @date 2025-11-07
 *
 * @copyright Copyright (c) 2025
 *
 */
/**************************************************************************************************/

#ifndef SENSORS_H
#define SENSORS_H

/*------------------------------------------------------------------------------------------------*/
// HEADERS                                                                                        */
/*------------------------------------------------------------------------------------------------*/

#include <stdio.h>
#include "esp_err.h"

/*------------------------------------------------------------------------------------------------*/
// MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

#define NUM_ENCODERS    2    // Number of encoders (2 for dual deck DJ system)
#define ENCODER_1       0    // Encoder index for deck 1
#define ENCODER_2       1    // Encoder index for deck 2

/*------------------------------------------------------------------------------------------------*/
// GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/



/*------------------------------------------------------------------------------------------------*/
// CLASS DECLARATIONS                                                                             */
/*------------------------------------------------------------------------------------------------*/



/*------------------------------------------------------------------------------------------------*/
// FUNCTION DECLARATIONS                                                                          */
/*------------------------------------------------------------------------------------------------*/

/**************************************************************************************************/
/**
 * @brief Initialize all sensors including rotary encoder
 * @return esp_err_t ESP_OK on success
 */
/**************************************************************************************************/
esp_err_t sensors_init(void);

/**************************************************************************************************/
/**
 * @brief Get the current encoder position (counts)
 * @param encoder_id Encoder index (ENCODER_1 or ENCODER_2)
 * @return int32_t Current encoder position
 */
/**************************************************************************************************/
int32_t encoder_get_position(uint8_t encoder_id);

/**************************************************************************************************/
/**
 * @brief Reset the encoder position to zero
 * @param encoder_id Encoder index (ENCODER_1 or ENCODER_2)
 */
/**************************************************************************************************/
void encoder_reset_position(uint8_t encoder_id);

/**************************************************************************************************/
/**
 * @brief Get the encoder velocity (counts per second)
 * @param encoder_id Encoder index (ENCODER_1 or ENCODER_2)
 * @param sample_period_ms The time period between calls in milliseconds
 * @return float Encoder velocity in counts/second
 */
/**************************************************************************************************/
float encoder_get_velocity(uint8_t encoder_id, uint32_t sample_period_ms);

#endif // SENSORS_H