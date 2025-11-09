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
#include "utils.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// Rotary encoder pins
// Wiring: GND -> ESP32 GND, Pin "2" -> ESP32 GND, N -> GPIO26, N̅ -> GPIO27
#define ENCODER_PIN_A       GPIO_NUM_26  // Phase A (N pin)
#define ENCODER_PIN_B       GPIO_NUM_27  // Phase B (N̅ pin)

// PCNT configuration
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

    // Configure GPIO pull-ups for mechanical encoder
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << ENCODER_PIN_A) | (1ULL << ENCODER_PIN_B),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure GPIO pull-ups: %s", esp_err_to_name(ret));
        return ret;
    }

    // PCNT unit configuration
    pcnt_unit_config_t unit_config = {
        .high_limit = PCNT_HIGH_LIMIT,
        .low_limit = PCNT_LOW_LIMIT,
    };

    ret = pcnt_new_unit(&unit_config, &pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    // Quadrature encoder configuration (simpler API)
    pcnt_chan_config_t chan_a_config = {
        .edge_gpio_num = ENCODER_PIN_A,
        .level_gpio_num = ENCODER_PIN_B,
    };

    pcnt_channel_handle_t pcnt_chan_a = NULL;
    ret = pcnt_new_channel(pcnt_unit, &chan_a_config, &pcnt_chan_a);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT channel A: %s", esp_err_to_name(ret));
        return ret;
    }

    pcnt_chan_config_t chan_b_config = {
        .edge_gpio_num = ENCODER_PIN_B,
        .level_gpio_num = ENCODER_PIN_A,
    };

    pcnt_channel_handle_t pcnt_chan_b = NULL;
    ret = pcnt_new_channel(pcnt_unit, &chan_b_config, &pcnt_chan_b);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT channel B: %s", esp_err_to_name(ret));
        return ret;
    }

    // Set edge and level actions for quadrature decoding
    pcnt_channel_set_edge_action(pcnt_chan_a, PCNT_CHANNEL_EDGE_ACTION_DECREASE, PCNT_CHANNEL_EDGE_ACTION_INCREASE);
    pcnt_channel_set_level_action(pcnt_chan_a, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    pcnt_channel_set_edge_action(pcnt_chan_b, PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_DECREASE);
    pcnt_channel_set_level_action(pcnt_chan_b, PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    // Add glitch filter to reduce noise from mechanical contacts
    pcnt_glitch_filter_config_t filter_config = {
        .max_glitch_ns = 1000,  // Filter glitches < 1us
    };
    ret = pcnt_unit_set_glitch_filter(pcnt_unit, &filter_config);
    if (ret != ESP_OK) {
        LOG_WARN(TAG, "Failed to set glitch filter: %s", esp_err_to_name(ret));
    }

    // Enable and start the PCNT unit
    ret = pcnt_unit_enable(pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to enable PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_clear_count(pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to clear PCNT count: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_start(pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to start PCNT unit: %s", esp_err_to_name(ret));
        return ret;
    }

    LOG_INFO(TAG, "Rotary encoder initialized on GPIO %d (A) and %d (B)", ENCODER_PIN_A, ENCODER_PIN_B);
    return ESP_OK;
}

esp_err_t sensors_init(void)
{
    esp_err_t ret;

    // Initialize rotary encoder
    ret = encoder_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize encoder");
        return ret;
    }

    vTaskDelay(pdMS_TO_TICKS(5)); // Small delay to ensure settings take effect

    LOG_INFO(TAG, "All sensors initialized successfully");
    return ESP_OK;
}

int32_t encoder_get_position(void)
{
    if (pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder not initialized");
        return 0;
    }

    int count = 0;
    esp_err_t ret = pcnt_unit_get_count(pcnt_unit, &count);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to get encoder count: %s", esp_err_to_name(ret));
        return encoder_offset;
    }

    return count + encoder_offset;
}

void encoder_reset_position(void)
{
    if (pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder not initialized");
        return;
    }

    encoder_offset = 0;
    pcnt_unit_clear_count(pcnt_unit);
    last_position = 0;
    LOG_INFO(TAG, "Encoder position reset to 0");
}

float encoder_get_velocity(uint32_t sample_period_ms)
{
    if (pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder not initialized");
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