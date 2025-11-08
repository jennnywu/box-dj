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
#include "motors.h"
#include "sensors.h"
#include "comm.h"

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

/**************************************************************************************************/
/**
 * @brief Motor control task - changes direction every 3 seconds
 * @param pvParameters Task parameters (unused)
 */
/**************************************************************************************************/
void motor_control_task(void *pvParameters);

/**************************************************************************************************/
/**
 * @brief Encoder reading task - reads position every 200ms
 * @param pvParameters Task parameters (unused)
 */
/**************************************************************************************************/
void encoder_read_task(void *pvParameters);

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

esp_err_t initialize_main(void)
{
    esp_err_t ret = ESP_OK;

    ret = motors_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize motors: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = sensors_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize sensors: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = comm_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize communication module: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "Initialization complete");
    return ESP_OK;
}

void motor_control_task(void *pvParameters)
{
    ESP_LOGI(TAG, "Motor control task started");

    uint8_t state = 0;
    const uint8_t motor_speed = 200;

    while (1) {
        switch (state) {
            case 0:
                ESP_LOGI(TAG, "Motors: FORWARD at speed %d", motor_speed);
                motors_forward(motor_speed);
                break;
            case 1:
                ESP_LOGI(TAG, "Motors: BACKWARD at speed %d", motor_speed);
                motors_backward(motor_speed);
                break;
            case 2:
                ESP_LOGI(TAG, "Motors: STOPPED");
                motors_stop();
                break;
        }

        // Cycle through states: forward -> backward -> stop -> repeat
        state = (state + 1) % 3;

        // Wait 3 seconds before changing direction
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}

void encoder_read_task(void *pvParameters)
{
    ESP_LOGI(TAG, "Encoder reading task started");

    // Reset encoder position to zero at start
    encoder_reset_position();

    const uint32_t sample_period_ms = 200;

    while (1) {
        // Read encoder position and velocity
        int32_t position = encoder_get_position();
        float velocity = encoder_get_velocity(sample_period_ms);

        // Log encoder data
        ESP_LOGI(TAG, "Encoder - Position: %ld counts, Velocity: %.2f counts/sec",
                 (long)position, velocity);

        // Wait 200ms before next reading
        vTaskDelay(pdMS_TO_TICKS(sample_period_ms));
    }
}

void app_main(void)
{
    // Initialize all systems
    esp_err_t ret = initialize_main();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Initialization failed!");
        return;
    }

    ESP_LOGI(TAG, "System initialized successfully");
    ESP_LOGI(TAG, "Creating FreeRTOS tasks...");

    // Create motor control task
    BaseType_t motor_task_created = xTaskCreate(
        motor_control_task,      // Task function
        "motor_control",         // Task name
        4096,                    // Stack size (bytes)
        NULL,                    // Task parameters
        5,                       // Priority
        NULL                     // Task handle
    );

    if (motor_task_created != pdPASS) {
        ESP_LOGE(TAG, "Failed to create motor control task");
        return;
    }

    // Create encoder reading task
    BaseType_t encoder_task_created = xTaskCreate(
        encoder_read_task,       // Task function
        "encoder_read",          // Task name
        4096,                    // Stack size (bytes)
        NULL,                    // Task parameters
        5,                       // Priority
        NULL                     // Task handle
    );

    if (encoder_task_created != pdPASS) {
        ESP_LOGE(TAG, "Failed to create encoder reading task");
        return;
    }

    ESP_LOGI(TAG, "Tasks created successfully - system running");
}