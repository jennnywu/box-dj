/**************************************************************************************************/
/**
 * @file inputs.c
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief Input handling for buttons and potentiometer
 *
 * @version 0.1
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
#include <string.h>
#include "driver/gpio.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "inputs.h"
#include "utils.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// Button GPIO pins
#define SOUND_EFFECT_BUTTON_ONE     GPIO_NUM_4
#define SOUND_EFFECT_BUTTON_TWO     GPIO_NUM_16
#define SOUND_EFFECT_BUTTON_THREE   GPIO_NUM_17
#define SOUND_EFFECT_BUTTON_FOUR    GPIO_NUM_5
#define SONG_ONE_SPEED              GPIO_NUM_12
#define SONG_TWO_SPEED              GPIO_NUM_13

// Potentiometer ADC
#define VOLUME_POTENTIOMETER_CHANNEL    ADC_CHANNEL_6  // GPIO 34
#define VOLUME_POTENTIOMETER_UNIT       ADC_UNIT_1

#define SLIDER_POTENTIOMETER_CHANNEL    ADC_CHANNEL_7  // GPIO 35
#define SLIDER_POTENTIOMETER_UNIT       ADC_UNIT_1

// Debounce time in microseconds (50ms)
#define DEBOUNCE_TIME_US            50000

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "INPUTS";

// Button state array
static volatile button_state_t button_states[NUM_BUTTONS];

// GPIO to button index mapping
static const gpio_num_t button_gpios[NUM_BUTTONS] = {
    SOUND_EFFECT_BUTTON_ONE,   // BUTTON_SFX_1
    SOUND_EFFECT_BUTTON_TWO,   // BUTTON_SFX_2
    SOUND_EFFECT_BUTTON_THREE, // BUTTON_SFX_3
    SOUND_EFFECT_BUTTON_FOUR,  // BUTTON_SFX_4
    SONG_ONE_SPEED,            // BUTTON_SONG_1
    SONG_TWO_SPEED             // BUTTON_SONG_2
};

// ADC handle and calibration
static adc_oneshot_unit_handle_t adc_handle = NULL;
static adc_cali_handle_t adc_cali_handle = NULL;

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

/**************************************************************************************************/
/**
 * @name
 * @brief
 *
 *
 * @param arg
 *
 */
/**************************************************************************************************/
static void button_isr_handler(void *arg);

/**************************************************************************************************/
/**
 * @name
 * @brief
 *
 *
 *
 * @return esp_err_t
 */
/**************************************************************************************************/
static esp_err_t buttons_init(void);

/**************************************************************************************************/
/**
 * @name
 * @brief
 *
 *
 *
 * @return esp_err_t
 */
/**************************************************************************************************/
static esp_err_t volume_potentiometer_init(void);

/**************************************************************************************************/
/**
 * @name
 * @brief
 *
 *
 *
 * @return esp_err_t
 */
/**************************************************************************************************/
static esp_err_t slider_potentiometer_init(void);

/**************************************************************************************************/
/**
 * @name
 * @brief Get the button index object
 *
 *
 * @param gpio
 *
 * @return int
 */
/**************************************************************************************************/
static int get_button_index(gpio_num_t gpio);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

static void IRAM_ATTR button_isr_handler(void *arg)
{
    gpio_num_t gpio = (gpio_num_t)(uint32_t)arg;
    int button_idx = get_button_index(gpio);

    if (button_idx < 0) return;

    uint32_t now = (uint32_t)(esp_timer_get_time());
    uint32_t time_since_last = now - button_states[button_idx].last_press;

    // Debounce: ignore if pressed within debounce time
    if (time_since_last > DEBOUNCE_TIME_US) {
        button_states[button_idx].pressed = true;
        button_states[button_idx].last_press = now;
        LOG_DEBUG(TAG, "Button %d pressed (GPIO %d)\n", button_idx, gpio);
    }
}

static int get_button_index(gpio_num_t gpio)
{
    for (int i = 0; i < NUM_BUTTONS; i++) {
        if (button_gpios[i] == gpio) {
            return i;
        }
    }
    return -1;
}

static esp_err_t buttons_init(void)
{
    esp_err_t ret;

    // Initialize button states
    memset((void *)button_states, 0, sizeof(button_states));

    // Configure GPIO for each button
    for (int i = 0; i < NUM_BUTTONS; i++) {
        gpio_num_t gpio = button_gpios[i];

        // Configure GPIO as input with pull-up
        gpio_config_t io_conf = {
            .pin_bit_mask = (1ULL << gpio),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_NEGEDGE  // Trigger on falling edge (button press)
        };

        ret = gpio_config(&io_conf);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to configure GPIO %d: %s", gpio, esp_err_to_name(ret));
            return ret;
        }
    }

    // Install GPIO ISR service
    ret = gpio_install_isr_service(0);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        // ESP_ERR_INVALID_STATE means service already installed (OK)
        LOG_ERROR(TAG, "Failed to install GPIO ISR service: %s", esp_err_to_name(ret));
        return ret;
    }

    // Attach interrupt handler for each button
    for (int i = 0; i < NUM_BUTTONS; i++) {
        gpio_num_t gpio = button_gpios[i];
        ret = gpio_isr_handler_add(gpio, button_isr_handler, (void *)(uint32_t)gpio);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to add ISR handler for GPIO %d: %s", gpio, esp_err_to_name(ret));
            return ret;
        }
    }

    LOG_INFO(TAG, "Buttons initialized with hardware interrupts");
    return ESP_OK;
}

static esp_err_t volume_potentiometer_init(void)
{
    esp_err_t ret;

    // Configure ADC1 unit
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = VOLUME_POTENTIOMETER_UNIT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ret = adc_oneshot_new_unit(&init_config, &adc_handle);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize ADC unit: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure ADC channel
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_12,        // 12-bit resolution (0-4095)
        .atten = ADC_ATTEN_DB_12,           // 0-3.3V range (updated from DB_11)
    };

    ret = adc_oneshot_config_channel(adc_handle, VOLUME_POTENTIOMETER_CHANNEL, &config);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure ADC channel: %s", esp_err_to_name(ret));
        return ret;
    }

    // Setup calibration (optional but recommended for accuracy)
    // ESP32 uses line fitting calibration scheme
    adc_cali_line_fitting_config_t cali_config = {
        .unit_id = VOLUME_POTENTIOMETER_UNIT,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    ret = adc_cali_create_scheme_line_fitting(&cali_config, &adc_cali_handle);
    if (ret != ESP_OK) {
        LOG_WARN(TAG, "ADC calibration not available: %s (raw values will be used)", esp_err_to_name(ret));
        adc_cali_handle = NULL;  // Continue without calibration
    }

    LOG_INFO(TAG, "Potentiometer initialized on ADC1_CH6 (GPIO 34)");
    return ESP_OK;
}

static esp_err_t slider_potentiometer_init(void)
{
    esp_err_t ret;

    // ADC unit already initialized by volume_potentiometer_init()
    // Just configure the additional channel

    // Configure ADC channel for slider potentiometer
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_12,        // 12-bit resolution (0-4095)
        .atten = ADC_ATTEN_DB_12,           // 0-3.3V range (updated from DB_11)
    };

    ret = adc_oneshot_config_channel(adc_handle, SLIDER_POTENTIOMETER_CHANNEL, &config);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure slider ADC channel: %s", esp_err_to_name(ret));
        return ret;
    }

    LOG_INFO(TAG, "Slider potentiometer initialized on ADC1_CH7 (GPIO 35)");
    return ESP_OK;
}

esp_err_t inputs_init(void)
{
    esp_err_t ret;

    // Initialize buttons with interrupts
    ret = buttons_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize buttons");
        return ret;
    }

    // Initialize potentiometer
    ret = volume_potentiometer_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize potentiometer");
        return ret;
    }

    ret = slider_potentiometer_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize slider potentiometer");
        return ret;
    }

    LOG_INFO(TAG, "All inputs initialized successfully");
    return ESP_OK;
}

esp_err_t inputs_get_data(input_data_t *data)
{
    if (data == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Build button flags byte (each bit represents a button)
    data->button_flags = 0;
    for (int i = 0; i < NUM_BUTTONS; i++) {
        if (button_states[i].pressed) {
            data->button_flags |= (1 << i);
        }
    }

    // Read volume potentiometer value
    data->volume_potentiometer = inputs_read_volume_potentiometer();

    // Read slider potentiometer value
    data->slider_potentiometer = inputs_read_slider_potentiometer();

    return ESP_OK;
}

void inputs_clear_button_flags(void)
{
    for (int i = 0; i < NUM_BUTTONS; i++) {
        button_states[i].pressed = false;
    }
}

uint16_t inputs_read_volume_potentiometer(void)
{
    int raw_value = 0;
    esp_err_t ret;

    // Read raw ADC value
    ret = adc_oneshot_read(adc_handle, VOLUME_POTENTIOMETER_CHANNEL, &raw_value);
    if (ret != ESP_OK) {
        LOG_WARN(TAG, "Failed to read ADC: %s", esp_err_to_name(ret));
        return 0;
    }

    // Return 12-bit value (0-4095)
    return (uint16_t)raw_value;
}

uint16_t inputs_read_slider_potentiometer(void)
{
    int raw_value = 0;
    esp_err_t ret;

    // Read raw ADC value
    ret = adc_oneshot_read(adc_handle, SLIDER_POTENTIOMETER_CHANNEL, &raw_value);
    if (ret != ESP_OK) {
        LOG_WARN(TAG, "Failed to read ADC: %s", esp_err_to_name(ret));
        return 0;
    }

    // Return 12-bit value (0-4095)
    return (uint16_t)raw_value;
}
