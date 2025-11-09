/**************************************************************************************************/
/**
 * @file sensors.c
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief Sensor data processing and management - supports dual encoders
 *
 * @version 0.2
 * @date 2025-11-08
 *
 * @copyright Copyright (c) 2025
 *
 */
/**************************************************************************************************/

/*------------------------------------------------------------------------------------------------*/
/* HEADERS                                                                                        */
/*------------------------------------------------------------------------------------------------*/

#include <stdio.h>
#include <stdint.h>
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

// Encoder 1 pins (Deck 1)
#define ENCODER_1_PIN_A       GPIO_NUM_26  // Phase A
#define ENCODER_1_PIN_B       GPIO_NUM_27  // Phase B

// Encoder 2 pins (Deck 2)
#define ENCODER_2_PIN_A       GPIO_NUM_14  // Phase A
#define ENCODER_2_PIN_B       GPIO_NUM_15  // Phase B

// PCNT configuration
#define PCNT_HIGH_LIMIT     10000
#define PCNT_LOW_LIMIT      -10000

/*------------------------------------------------------------------------------------------------*/
/* TYPE DEFINITIONS                                                                               */
/*------------------------------------------------------------------------------------------------*/

typedef struct {
    pcnt_unit_handle_t pcnt_unit;
    pcnt_channel_handle_t pcnt_chan_a;
    pcnt_channel_handle_t pcnt_chan_b;
    int32_t offset;
    int32_t last_position;
    gpio_num_t pin_a;
    gpio_num_t pin_b;
} encoder_state_t;

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "SENSORS";

// Array of encoder states
static encoder_state_t encoders[NUM_ENCODERS] = {
    [ENCODER_1] = {
        .pcnt_unit = NULL,
        .pcnt_chan_a = NULL,
        .pcnt_chan_b = NULL,
        .offset = 0,
        .last_position = 0,
        .pin_a = ENCODER_1_PIN_A,
        .pin_b = ENCODER_1_PIN_B,
    },
    [ENCODER_2] = {
        .pcnt_unit = NULL,
        .pcnt_chan_a = NULL,
        .pcnt_chan_b = NULL,
        .offset = 0,
        .last_position = 0,
        .pin_a = ENCODER_2_PIN_A,
        .pin_b = ENCODER_2_PIN_B,
    }
};

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

static esp_err_t encoder_gpio_init(uint8_t encoder_id);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

static esp_err_t encoder_gpio_init(uint8_t encoder_id)
{
    if (encoder_id >= NUM_ENCODERS) {
        LOG_ERROR(TAG, "Invalid encoder ID: %d", encoder_id);
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t ret;
    encoder_state_t *enc = &encoders[encoder_id];

    // Configure GPIO pull-ups for mechanical encoder
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << enc->pin_a) | (1ULL << enc->pin_b),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure GPIO pull-ups for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    // PCNT unit configuration
    pcnt_unit_config_t unit_config = {
        .high_limit = PCNT_HIGH_LIMIT,
        .low_limit = PCNT_LOW_LIMIT,
    };

    ret = pcnt_new_unit(&unit_config, &enc->pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT unit for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    // Quadrature encoder channel A configuration
    pcnt_chan_config_t chan_a_config = {
        .edge_gpio_num = enc->pin_a,
        .level_gpio_num = enc->pin_b,
    };

    ret = pcnt_new_channel(enc->pcnt_unit, &chan_a_config, &enc->pcnt_chan_a);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT channel A for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    // Quadrature encoder channel B configuration
    pcnt_chan_config_t chan_b_config = {
        .edge_gpio_num = enc->pin_b,
        .level_gpio_num = enc->pin_a,
    };

    ret = pcnt_new_channel(enc->pcnt_unit, &chan_b_config, &enc->pcnt_chan_b);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to create PCNT channel B for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    // Set edge and level actions for quadrature decoding
    pcnt_channel_set_edge_action(enc->pcnt_chan_a, PCNT_CHANNEL_EDGE_ACTION_DECREASE,
                                  PCNT_CHANNEL_EDGE_ACTION_INCREASE);
    pcnt_channel_set_level_action(enc->pcnt_chan_a, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
                                   PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    pcnt_channel_set_edge_action(enc->pcnt_chan_b, PCNT_CHANNEL_EDGE_ACTION_INCREASE,
                                  PCNT_CHANNEL_EDGE_ACTION_DECREASE);
    pcnt_channel_set_level_action(enc->pcnt_chan_b, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
                                   PCNT_CHANNEL_LEVEL_ACTION_INVERSE);

    // Add glitch filter to reduce noise from mechanical contacts
    pcnt_glitch_filter_config_t filter_config = {
        .max_glitch_ns = 1000,  // Filter glitches < 1us
    };
    ret = pcnt_unit_set_glitch_filter(enc->pcnt_unit, &filter_config);
    if (ret != ESP_OK) {
        LOG_WARN(TAG, "Failed to set glitch filter for encoder %d: %s",
                encoder_id, esp_err_to_name(ret));
    }

    // Enable and start the PCNT unit
    ret = pcnt_unit_enable(enc->pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to enable PCNT unit for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_clear_count(enc->pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to clear PCNT count for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    ret = pcnt_unit_start(enc->pcnt_unit);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to start PCNT unit for encoder %d: %s",
                 encoder_id, esp_err_to_name(ret));
        return ret;
    }

    LOG_INFO(TAG, "Encoder %d initialized on GPIO %d (A) and %d (B)",
            encoder_id, enc->pin_a, enc->pin_b);
    return ESP_OK;
}

esp_err_t sensors_init(void)
{
    esp_err_t ret;

    // Initialize both encoders
    for (uint8_t i = 0; i < NUM_ENCODERS; i++) {
        ret = encoder_gpio_init(i);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to initialize encoder %d", i);
            return ret;
        }
    }

    vTaskDelay(pdMS_TO_TICKS(5)); // Small delay to ensure settings take effect

    LOG_INFO(TAG, "All %d encoders initialized successfully", NUM_ENCODERS);
    return ESP_OK;
}

int32_t encoder_get_position(uint8_t encoder_id)
{
    if (encoder_id >= NUM_ENCODERS) {
        LOG_ERROR(TAG, "Invalid encoder ID: %d", encoder_id);
        return 0;
    }

    encoder_state_t *enc = &encoders[encoder_id];

    if (enc->pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder %d not initialized", encoder_id);
        return 0;
    }

    int count = 0;
    esp_err_t ret = pcnt_unit_get_count(enc->pcnt_unit, &count);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to get encoder %d count: %s", encoder_id, esp_err_to_name(ret));
        return enc->offset;
    }

    return count + enc->offset;
}

void encoder_reset_position(uint8_t encoder_id)
{
    if (encoder_id >= NUM_ENCODERS) {
        LOG_ERROR(TAG, "Invalid encoder ID: %d", encoder_id);
        return;
    }

    encoder_state_t *enc = &encoders[encoder_id];

    if (enc->pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder %d not initialized", encoder_id);
        return;
    }

    enc->offset = 0;
    pcnt_unit_clear_count(enc->pcnt_unit);
    enc->last_position = 0;
    LOG_INFO(TAG, "Encoder %d position reset to 0", encoder_id);
}

float encoder_get_velocity(uint8_t encoder_id, uint32_t sample_period_ms)
{
    if (encoder_id >= NUM_ENCODERS) {
        LOG_ERROR(TAG, "Invalid encoder ID: %d", encoder_id);
        return 0.0;
    }

    encoder_state_t *enc = &encoders[encoder_id];

    if (enc->pcnt_unit == NULL) {
        LOG_ERROR(TAG, "Encoder %d not initialized", encoder_id);
        return 0.0;
    }

    int32_t current_position = encoder_get_position(encoder_id);
    int32_t position_diff = current_position - enc->last_position;
    enc->last_position = current_position;

    // Convert to counts per second
    // velocity = (counts / milliseconds) * 1000
    float velocity = (float)position_diff / ((float)sample_period_ms / 1000.0f);

    return velocity;
}
