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
#include "driver/adc.h"
#include "esp_adc_cal.h"
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
#define VOLUME_POTENTIOMETER        ADC1_CHANNEL_6  // GPIO 34

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

// ADC characteristics
static esp_adc_cal_characteristics_t *adc_chars = NULL;

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

static void IRAM_ATTR button_isr_handler(void *arg);
static esp_err_t buttons_init(void);
static esp_err_t potentiometer_init(void);
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

static esp_err_t potentiometer_init(void)
{
    esp_err_t ret;

    // Configure ADC1
    ret = adc1_config_width(ADC_WIDTH_BIT_12);  // 12-bit resolution (0-4095)
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure ADC width: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = adc1_config_channel_atten(VOLUME_POTENTIOMETER, ADC_ATTEN_DB_11);  // 0-3.3V range
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure ADC attenuation: %s", esp_err_to_name(ret));
        return ret;
    }

    // Characterize ADC for better accuracy
    adc_chars = calloc(1, sizeof(esp_adc_cal_characteristics_t));
    if (adc_chars == NULL) {
        LOG_ERROR(TAG, "Failed to allocate ADC characteristics");
        return ESP_ERR_NO_MEM;
    }

    esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_WIDTH_BIT_12,
                             1100, adc_chars);

    LOG_INFO(TAG, "Potentiometer initialized on ADC1_CH6");
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
    ret = potentiometer_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize potentiometer");
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

    // Read potentiometer value
    data->potentiometer = inputs_read_potentiometer();

    return ESP_OK;
}

void inputs_clear_button_flags(void)
{
    for (int i = 0; i < NUM_BUTTONS; i++) {
        button_states[i].pressed = false;
    }
}

uint16_t inputs_read_potentiometer(void)
{
    // Read raw ADC value
    int raw_value = adc1_get_raw(VOLUME_POTENTIOMETER);

    if (raw_value < 0) {
        LOG_WARN(TAG, "Failed to read ADC");
        return 0;
    }

    // Return 12-bit value (0-4095)
    return (uint16_t)raw_value;
}
