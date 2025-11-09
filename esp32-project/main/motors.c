/**************************************************************************************************/
/**
 * @file motors.c
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief
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
#include <stdint.h>
#include "esp_err.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "motors.h"
#include "utils.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// Motor A pins
#define MOTOR_A_IN1         GPIO_NUM_18
#define MOTOR_A_IN2         GPIO_NUM_19
#define MOTOR_A_EN          GPIO_NUM_21

// Motor B pins
#define MOTOR_B_IN3         GPIO_NUM_22
#define MOTOR_B_IN4         GPIO_NUM_23
#define MOTOR_B_EN          GPIO_NUM_25

// PWM Configuration
#define PWM_FREQUENCY       5000              // 5 kHz
#define PWM_RESOLUTION      LEDC_TIMER_8_BIT  // 8-bit = 0-255
#define PWM_TIMER           LEDC_TIMER_0
#define PWM_MODE            LEDC_LOW_SPEED_MODE

// PWM Channels
#define MOTOR_A_CHANNEL     LEDC_CHANNEL_0
#define MOTOR_B_CHANNEL     LEDC_CHANNEL_1

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "MOTORS";

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

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
static esp_err_t motor_gpio_init(void);

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
static esp_err_t motor_pwm_init(void);

/**************************************************************************************************/
/**
 * @name
 * @brief Set the motor direction object
 *
 *
 * @param direction
 *
 */
/**************************************************************************************************/
static void set_motor_direction(motor_direction_t direction);

/**************************************************************************************************/
/**
 * @name
 * @brief Set the motor pwm object
 *
 *
 * @param speed
 *
 */
/**************************************************************************************************/
static void set_motor_pwm(uint8_t speed);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

static esp_err_t motor_gpio_init(void)
{
    esp_err_t ret;

    // Direction pins for both motors
    const gpio_num_t direction_pins[] = {
        MOTOR_A_IN1, MOTOR_A_IN2,
        MOTOR_B_IN3, MOTOR_B_IN4
    };
    int num_pins = sizeof(direction_pins) / sizeof(direction_pins[0]);

    for (int i = 0; i < num_pins; i++) {
        ret = gpio_reset_pin(direction_pins[i]);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to reset GPIO %d: %s",
                     direction_pins[i], esp_err_to_name(ret));
            return ret;
        }

        ret = gpio_set_direction(direction_pins[i], GPIO_MODE_OUTPUT);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to set direction for GPIO %d: %s",
                     direction_pins[i], esp_err_to_name(ret));
            return ret;
        }

        ret = gpio_set_level(direction_pins[i], 0);
        if (ret != ESP_OK) {
            LOG_ERROR(TAG, "Failed to set level for GPIO %d: %s",
                     direction_pins[i], esp_err_to_name(ret));
            return ret;
        }
    }

    LOG_INFO(TAG, "Direction GPIOs initialized");
    return ESP_OK;
}

static esp_err_t motor_pwm_init(void)
{
    esp_err_t ret;

    // Configure PWM timer
    ledc_timer_config_t timer_conf = {
        .speed_mode = PWM_MODE,
        .duty_resolution = PWM_RESOLUTION,
        .timer_num = PWM_TIMER,
        .freq_hz = PWM_FREQUENCY,
        .clk_cfg = LEDC_AUTO_CLK
    };
    ret = ledc_timer_config(&timer_conf);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure PWM timer: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure Motor A PWM channel
    ledc_channel_config_t motor_a_channel = {
        .gpio_num = MOTOR_A_EN,
        .speed_mode = PWM_MODE,
        .channel = MOTOR_A_CHANNEL,
        .timer_sel = PWM_TIMER,
        .duty = 0,
        .hpoint = 0
    };
    ret = ledc_channel_config(&motor_a_channel);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure Motor A PWM: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure Motor B PWM channel
    ledc_channel_config_t motor_b_channel = {
        .gpio_num = MOTOR_B_EN,
        .speed_mode = PWM_MODE,
        .channel = MOTOR_B_CHANNEL,
        .timer_sel = PWM_TIMER,
        .duty = 0,
        .hpoint = 0
    };
    ret = ledc_channel_config(&motor_b_channel);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure Motor B PWM: %s", esp_err_to_name(ret));
        return ret;
    }

    LOG_INFO(TAG, "PWM initialized");
    return ESP_OK;
}

static void set_motor_direction(motor_direction_t direction)
{
    switch (direction) {
        case MOTOR_FORWARD:
            LOG_DEBUG(TAG, "Setting direction: FORWARD (IN1=0, IN2=1, IN3=0, IN4=1)");
            // Motor A forward
            gpio_set_level(MOTOR_A_IN1, 0);
            gpio_set_level(MOTOR_A_IN2, 1);
            // Motor B forward
            gpio_set_level(MOTOR_B_IN3, 0);
            gpio_set_level(MOTOR_B_IN4, 1);
            break;

        case MOTOR_BACKWARD:
            LOG_DEBUG(TAG, "Setting direction: BACKWARD (IN1=1, IN2=0, IN3=1, IN4=0)");
            // Motor A backward
            gpio_set_level(MOTOR_A_IN1, 1);
            gpio_set_level(MOTOR_A_IN2, 0);
            // Motor B backward
            gpio_set_level(MOTOR_B_IN3, 1);
            gpio_set_level(MOTOR_B_IN4, 0);
            break;

        case MOTOR_STOP:
            LOG_DEBUG(TAG, "Setting direction: STOP (all pins LOW)");
            // Stop both motors
            gpio_set_level(MOTOR_A_IN1, 0);
            gpio_set_level(MOTOR_A_IN2, 0);
            gpio_set_level(MOTOR_B_IN3, 0);
            gpio_set_level(MOTOR_B_IN4, 0);
            break;
    }
}

static void set_motor_pwm(uint8_t speed)
{
    LOG_DEBUG(TAG, "Setting PWM speed: %d (on EN pins %d, %d)", speed, MOTOR_A_EN, MOTOR_B_EN);

    // Set Motor A speed
    ledc_set_duty(PWM_MODE, MOTOR_A_CHANNEL, speed);
    ledc_update_duty(PWM_MODE, MOTOR_A_CHANNEL);

    // Set Motor B speed
    ledc_set_duty(PWM_MODE, MOTOR_B_CHANNEL, speed);
    ledc_update_duty(PWM_MODE, MOTOR_B_CHANNEL);
}

esp_err_t motors_init(void)
{
    esp_err_t ret;

    // Initialize direction GPIOs
    ret = motor_gpio_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Motor GPIO initialization failed");
        return ret;
    }

    // Initialize PWM
    ret = motor_pwm_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Motor PWM initialization failed");
        return ret;
    }

    // Stop motors initially
    motors_stop();

    LOG_INFO(TAG, "Motors initialized successfully");
    return ESP_OK;
}

esp_err_t motors_set(uint8_t speed, motor_direction_t direction)
{
    // Set direction first
    set_motor_direction(direction);

    // Small delay to allow direction pins to settle before applying PWM
    vTaskDelay(pdMS_TO_TICKS(10));

    // Then set PWM speed
    set_motor_pwm(speed);

    LOG_INFO(TAG, "Motors set - Speed: %d, Direction: %d", speed, direction);
    return ESP_OK;
}

esp_err_t motors_forward(uint8_t speed)
{
    return motors_set(speed, MOTOR_FORWARD);
}

esp_err_t motors_backward(uint8_t speed)
{
    return motors_set(speed, MOTOR_BACKWARD);
}

esp_err_t motors_stop(void)
{
    set_motor_direction(MOTOR_STOP);
    set_motor_pwm(0);

    LOG_INFO(TAG, "Motors stopped");
    return ESP_OK;
}