/**************************************************************************************************/
/**
 * @file leds.c
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief LED control module for scrolling light effects
 *
 * Hardware Configuration:
 * - 3.3V -> 150Ω resistor -> LED anode -> LED cathode -> GPIO (sink) -> GND
 * - GPIO LOW = LED ON (sinking current)
 * - GPIO HIGH = LED OFF (high impedance)
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
#include "driver/gpio.h"
#include "esp_log.h"
#include "leds.h"
#include "utils.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// LED GPIO pins (active-low sinks)
#define LED_1_GPIO    GPIO_NUM_18
#define LED_2_GPIO    GPIO_NUM_19
#define LED_3_GPIO    GPIO_NUM_21

// LED states (active-low logic)
#define LED_ON        0    // GPIO LOW = sink current = LED ON
#define LED_OFF       1    // GPIO HIGH = LED OFF

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "LEDS";

// Array of LED GPIO pins
static const gpio_num_t led_gpios[NUM_LEDS] = {
    LED_1_GPIO,
    LED_2_GPIO,
    LED_3_GPIO
};

// Current active LED index
static uint8_t current_led = 0;

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

esp_err_t leds_init(void)
{
    esp_err_t ret;

    // Configure all LED GPIOs as outputs
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << LED_1_GPIO) | (1ULL << LED_2_GPIO) | (1ULL << LED_3_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure LED GPIOs: %s", esp_err_to_name(ret));
        return ret;
    }

    // Turn off all LEDs initially (set HIGH for active-low)
    leds_all_off();

    LOG_INFO(TAG, "LEDs initialized on GPIO %d, %d, %d (active-low sinks)",
            LED_1_GPIO, LED_2_GPIO, LED_3_GPIO);

    // Turn on the first LED
    leds_set(0);

    return ESP_OK;
}

void leds_scroll(void)
{
    // Turn off current LED
    gpio_set_level(led_gpios[current_led], LED_OFF);

    // Move to next LED (circular)
    current_led = (current_led + 1) % NUM_LEDS;

    // Turn on next LED
    gpio_set_level(led_gpios[current_led], LED_ON);

    LOG_DEBUG(TAG, "Scrolled to LED %d (GPIO %d)", current_led, led_gpios[current_led]);
}

void leds_set(uint8_t led_index)
{
    if (led_index >= NUM_LEDS) {
        LOG_WARN(TAG, "Invalid LED index: %d (max %d)", led_index, NUM_LEDS - 1);
        return;
    }

    // Turn off all LEDs
    leds_all_off();

    // Turn on the selected LED
    gpio_set_level(led_gpios[led_index], LED_ON);
    current_led = led_index;

    LOG_DEBUG(TAG, "LED %d turned on (GPIO %d)", led_index, led_gpios[led_index]);
}

void leds_all_off(void)
{
    for (uint8_t i = 0; i < NUM_LEDS; i++) {
        gpio_set_level(led_gpios[i], LED_OFF);
    }

    LOG_DEBUG(TAG, "All LEDs turned off");
}
