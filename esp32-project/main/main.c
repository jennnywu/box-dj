/**************************************************************************************************/
/**
 * @file main.c
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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "motors.h"
#include "sensors.h"
#include "comm.h"
#include "lcd.h"
#include "utils.h"
#include "inputs.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/



/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "MAIN";

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/

/**************************************************************************************************/
/**
 * @brief Initialize all system components
 * @return esp_err_t ESP_OK on success
 */
/**************************************************************************************************/
esp_err_t initialize_main(void);

// /**************************************************************************************************/
// /**
//  * @brief Motor control task - changes direction every 3 seconds
//  * @param pvParameters Task parameters (unused)
//  */
// /**************************************************************************************************/
// void motor_control_task(void *pvParameters);

/**************************************************************************************************/
/**
 * @brief Encoder reading task - reads position every 200ms
 * @param pvParameters Task parameters (unused)
 */
/**************************************************************************************************/
void encoder_read_task(void *pvParameters);

/**************************************************************************************************/
/**
 * @brief I2C communication task - sends encoder data to RPi5
 * @param pvParameters Task parameters (unused)
 */
/**************************************************************************************************/
void i2c_comm_task(void *pvParameters);

/**************************************************************************************************/
/**
 * @name start_motors
 * @brief Start the motors with a predefined speed and direction
 *
 * This function initializes the motor control and starts the motors
 * in the forward direction at a specified speed.
 *
 */
/**************************************************************************************************/
esp_err_t start_motors(void);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

esp_err_t initialize_main(void)
{
    esp_err_t ret = ESP_OK;

    ret = motors_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize motors: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = sensors_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize sensors: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = comm_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize communication module: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = inputs_init();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to initialize inputs: %s", esp_err_to_name(ret));
        return ret;
    }

    // ret = lcd_init();
    // if (ret != ESP_OK) {
    //     LOG_ERROR(TAG, "Failed to initialize LCD: %s", esp_err_to_name(ret));
    //     return ret;
    // }

    LOG_INFO(TAG, "Initialization complete");
    return ESP_OK;
}

esp_err_t start_motors(void)
{
    esp_err_t ret;
    const uint8_t motor_speed = 150; // Set desired speed (0-255)
    ret = motors_forward(motor_speed);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to start motors: %s", esp_err_to_name(ret));
    } else {
        LOG_INFO(TAG, "Motors started at speed %d", motor_speed);
    }

    return ret;
}

// void motor_control_task(void *pvParameters)
// {
//     LOG_INFO(TAG, "Motor control task started");

//     uint8_t state = 0;
//     const uint8_t motor_speed = 100;

//     while (1) {
//         switch (state) {
//             case 0:
//                 LOG_INFO(TAG, "Motors: FORWARD at speed %d", motor_speed);
//                 motors_forward(motor_speed);
//                 break;
//             case 1:
//                 LOG_INFO(TAG, "Motors: BACKWARD at speed %d", motor_speed);
//                 motors_backward(motor_speed);
//                 break;
//             case 2:
//                 LOG_INFO(TAG, "Motors: STOPPED");
//                 motors_stop();
//                 break;
//         }

//         // Cycle through states: forward -> backward -> stop -> repeat
//         // state = (state + 1) % 3;

//         // Wait 3 seconds before changing direction
//         vTaskDelay(pdMS_TO_TICKS(3000));
//     }
// }

void encoder_read_task(void *pvParameters)
{
    LOG_INFO(TAG, "Encoder reading task started on core %d", xPortGetCoreID());

    // Reset both encoder positions to zero at start
    encoder_reset_position(ENCODER_1);
    encoder_reset_position(ENCODER_2);

    const uint32_t sample_period_ms = 20;

    while (1) {
        // Read encoder 1 data
        int32_t enc1_pos = encoder_get_position(ENCODER_1);
        float enc1_vel = encoder_get_velocity(ENCODER_1, sample_period_ms);

        // Read encoder 2 data
        int32_t enc2_pos = encoder_get_position(ENCODER_2);
        float enc2_vel = encoder_get_velocity(ENCODER_2, sample_period_ms);

        // Log encoder data
        LOG_INFO(TAG, "Enc1 - Pos: %ld, Vel: %.2f | Enc2 - Pos: %ld, Vel: %.2f",
                 (long)enc1_pos, enc1_vel, (long)enc2_pos, enc2_vel);

        // Wait before next reading
        vTaskDelay(pdMS_TO_TICKS(sample_period_ms));
    }
}

void i2c_comm_task(void *pvParameters)
{
    LOG_INFO(TAG, "I2C communication task started on core %d", xPortGetCoreID());

    const uint32_t update_period_ms = 10;  // Update I2C buffer every 2ms (faster than encoder reading)

    while (1) {
        // Update I2C data buffer with latest encoder data
        esp_err_t ret = comm_update_encoder_data();
        if (ret != ESP_OK) {
            LOG_WARN(TAG, "Failed to update I2C buffer");
        }

        // Wait before next update
        vTaskDelay(pdMS_TO_TICKS(update_period_ms));
    }
}

void app_main(void)
{
    // Initialize all systems
    esp_err_t ret = initialize_main();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Initialization failed!");
        return;
    }

    // Start motors
    ret = start_motors();
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to start motors!");
        return;
    }

    // ret = lcd_show_now_playing("GNARLY");
    // if (ret != ESP_OK) {
    //     LOG_ERROR(TAG, "Failed to display on LCD: %s", esp_err_to_name(ret));
    //     return;
    // }

    LOG_INFO(TAG, "System initialized successfully");
    LOG_INFO(TAG, "Creating FreeRTOS tasks with dual-core configuration...");

    // Create I2C communication task - HIGHEST PRIORITY on Core 1
    BaseType_t i2c_task_created = xTaskCreatePinnedToCore(
        i2c_comm_task,           // Task function
        "i2c_comm",              // Task name
        4096,                    // Stack size (bytes)
        NULL,                    // Task parameters
        10,                      // Priority (highest)
        NULL,                    // Task handle
        1                        // Core 1 (dedicated for I2C)
    );

    if (i2c_task_created != pdPASS) {
        LOG_ERROR(TAG, "Failed to create I2C communication task");
        return;
    }

    // Create encoder reading task - HIGHEST PRIORITY on Core 0
    BaseType_t encoder_task_created = xTaskCreatePinnedToCore(
        encoder_read_task,       // Task function
        "encoder_read",          // Task name
        4096,                    // Stack size (bytes)
        NULL,                    // Task parameters
        10,                      // Priority (highest)
        NULL,                    // Task handle
        0                        // Core 0
    );

    if (encoder_task_created != pdPASS) {
        LOG_ERROR(TAG, "Failed to create encoder reading task");
        return;
    }

    // // Create motor control task - LOWER PRIORITY on Core 0 (same as encoder)
    // BaseType_t motor_task_created = xTaskCreatePinnedToCore(
    //     motor_control_task,      // Task function
    //     "motor_control",         // Task name
    //     4096,                    // Stack size (bytes)
    //     NULL,                    // Task parameters
    //     5,                       // Priority (lower)
    //     NULL,                    // Task handle
    //     0                        // Core 0 (shares with encoder)
    // );

    // if (motor_task_created != pdPASS) {
    //     LOG_ERROR(TAG, "Failed to create motor control task");
    //     return;
    // }

    LOG_INFO(TAG, "All tasks created successfully");
    LOG_INFO(TAG, "Task Configuration:");
    LOG_INFO(TAG, "  Core 0: encoder_read (priority 10), motor_control (priority 5)");
    LOG_INFO(TAG, "  Core 1: i2c_comm (priority 10)");
}