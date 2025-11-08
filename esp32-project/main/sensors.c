/**************************************************************************************************/
/**
 * @file sensors.c
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

/*------------------------------------------------------------------------------------------------*/
/* HEADERS                                                                                        */
/*------------------------------------------------------------------------------------------------*/

#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "driver/pulse_cnt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sensors.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// Rotary encoder pins
#define ENCODER_PIN_N       GPIO_NUM_26  // Main encoder signal (N)
#define ENCODER_PIN_2       GPIO_NUM_27  // Second signal (could be quadrature or differential)
#define ENCODER_VCC_PIN     -1           // Set to GPIO if you need to control power

// PCNT configuration
#define PCNT_UNIT           0
#define PCNT_HIGH_LIMIT     10000
#define PCNT_LOW_LIMIT      -10000

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "SENSORS";
static pcnt_unit_handle_t pcnt_unit = NULL;
static int32_t encoder_offset = 0;
static int32_t last_position = 0;

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

static esp_err_t encoder_init(void);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

static esp_err_t encoder_init(void)
{
    esp_err_t ret;

    // PCNT unit configuration
    pcnt_unit_config_t unit_config = {
        .high_limit = PCNT_HIGH_LIMIT,
        .low_limit = PCNT_LOW_LIMIT,
        .flags.accum_count = 0,  // Don't accumulate on overflow
    };

    ret = pcnt_new_unit(&unit_config, &pcnt_unit);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure channel 0 (main encoder signal N)
    pcnt_chan_config_t chan_a_config = {
        .edge_gpio_num = ENCODER_PIN_N,
        .level_gpio_num = ENCODER_PIN_2,  // Use pin 2 for direction detection
    };

    pcnt_channel_handle_t pcnt_chan_a = NULL;
    ret = pcnt_new_channel(pcnt_unit, &chan_a_config, &pcnt_chan_a);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create PCNT channel A: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure channel 1 (for quadrature decoding)
    pcnt_chan_config_t chan_b_config = {
        .edge_gpio_num = ENCODER_PIN_2,
        .level_gpio_num = ENCODER_PIN_N,
    };

    pcnt_channel_handle_t pcnt_chan_b = NULL;
    ret = pcnt_new_channel(pcnt_unit, &chan_b_config, &pcnt_chan_b);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create PCNT channel B: %s", esp_err_to_name(ret));
        return ret;
    }

    // Set edge and level actions for quadrature decoder
    // Channel A
    pcnt_channel_set_edge_action(pcnt_chan_a, PCNT_CHANNEL_EDGE_ACTION_DECREASE, PCNT_CHANNEL_EDGE_ACTION_INCREASE);
    pcnt_channel_set_level_action(pcnt_chan_a, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    // Channel B
    pcnt_channel_set_edge_action(pcnt_chan_b, PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_DECREASE);
    pcnt_channel_set_level_action(pcnt_chan_b, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    // Add glitch filter (optional, helps with noise)
    pcnt_glitch_filter_config_t filter_config = {
        .max_glitch_ns = 1000,  // Filter out glitches < 1us
    };
    ret = pcnt_unit_set_glitch_filter(pcnt_unit, &filter_config);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set glitch filter: %s", esp_err_to_name(ret));
    }

    // Enable and start the PCNT unit
    ret = pcnt_unit_enable(pcnt_unit);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_clear_count(pcnt_unit);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to clear PCNT count: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_start(pcnt_unit);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "Rotary encoder initialized on GPIO %d and %d", ENCODER_PIN_N, ENCODER_PIN_2);
    return ESP_OK;
}

esp_err_t sensors_init(void)
{
    esp_err_t ret;

    // Initialize rotary encoder
    ret = encoder_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize encoder");
        return ret;
    }

    ESP_LOGI(TAG, "All sensors initialized successfully");
    return ESP_OK;
}

int32_t encoder_get_position(void)
{
    if (pcnt_unit == NULL) {
        ESP_LOGE(TAG, "Encoder not initialized");
        return 0;
    }

    int count = 0;
    esp_err_t ret = pcnt_unit_get_count(pcnt_unit, &count);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get encoder count: %s", esp_err_to_name(ret));
        return encoder_offset;
    }

    return count + encoder_offset;
}

void encoder_reset_position(void)
{
    if (pcnt_unit == NULL) {
        ESP_LOGE(TAG, "Encoder not initialized");
        return;
    }

    encoder_offset = 0;
    pcnt_unit_clear_count(pcnt_unit);
    last_position = 0;
    ESP_LOGI(TAG, "Encoder position reset to 0");
}

float encoder_get_velocity(uint32_t sample_period_ms)
{
    if (pcnt_unit == NULL) {
        ESP_LOGE(TAG, "Encoder not initialized");
        return 0.0;
    }

    int32_t current_position = encoder_get_position();
    int32_t position_diff = current_position - last_position;
    last_position = current_position;

    // Convert to counts per second
    // velocity = (counts / milliseconds) * 1000
    float velocity = (float)position_diff / ((float)sample_period_ms / 1000.0f);

    return velocity;
}