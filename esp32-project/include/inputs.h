/**************************************************************************************************/
/**
 * @file inputs.h
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief
 *
 * @version 0.1
 * @date 2025-11-08
 *
 * @copyright Copyright (c) 2025
 *
 */
/**************************************************************************************************/

#ifndef INPUTS_H
#define INPUTS_H

/*------------------------------------------------------------------------------------------------*/
// HEADERS                                                                                        */
/*------------------------------------------------------------------------------------------------*/

#include <stdint.h>
#include <stdbool.h>
#include "driver/gpio.h"
#include "esp_err.h"

/*------------------------------------------------------------------------------------------------*/
// MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// Button indices
#define BUTTON_SFX_1    0
#define BUTTON_SFX_2    1
#define BUTTON_SFX_3    2
#define BUTTON_SFX_4    3
#define BUTTON_SONG_1   4
#define BUTTON_SONG_2   5
#define NUM_BUTTONS     6

/*------------------------------------------------------------------------------------------------*/
// TYPE DEFINITIONS                                                                               */
/*------------------------------------------------------------------------------------------------*/

// Button state structure
typedef struct {
    bool pressed;        // Flag indicating button was pressed
    uint32_t last_press; // Timestamp of last press (for debouncing)
} button_state_t;

// Input data packet structure for I2C transmission
typedef struct {
    uint8_t button_flags;   // Bit field: each bit represents a button (0-5)
    uint16_t volume_potentiometer; // Volume potentiometer value (0-4095, 12-bit ADC)
    uint16_t slider_potentiometer; // Slider potentiometer value (0-4095, 12-bit ADC)
} input_data_t;

/*------------------------------------------------------------------------------------------------*/
// FUNCTION DECLARATIONS                                                                          */
/*------------------------------------------------------------------------------------------------*/

/**************************************************************************************************/
/**
 * @brief Initialize all input devices (buttons and potentiometer)
 * @return esp_err_t ESP_OK on success
 */
/**************************************************************************************************/
esp_err_t inputs_init(void);

/**************************************************************************************************/
/**
 * @brief Get current input data (button states and potentiometer value)
 * @param data Pointer to input_data_t structure to fill
 * @return esp_err_t ESP_OK on success
 */
/**************************************************************************************************/
esp_err_t inputs_get_data(input_data_t *data);

/**************************************************************************************************/
/**
 * @brief Clear all button press flags
 */
/**************************************************************************************************/
void inputs_clear_button_flags(void);

/**************************************************************************************************/
/**
 * @brief Read volume potentiometer value (0-4095)
 * @return uint16_t Volume potentiometer ADC value
 */
/**************************************************************************************************/
uint16_t inputs_read_volume_potentiometer(void);

/**************************************************************************************************/
/**
 * @brief Read slider potentiometer value (0-4095)
 * @return uint16_t Slider potentiometer ADC value
 */
/**************************************************************************************************/
uint16_t inputs_read_slider_potentiometer(void);

#endif // INPUTS_H