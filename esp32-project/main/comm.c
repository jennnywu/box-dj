/**************************************************************************************************/
/**
 * @file comm.c
 * @author Ryan Jing (r5jing@uwaterloo.ca)
 * @brief  Communication module for I2C
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
#include <string.h>
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "driver/i2c.h"
#include "comm.h"
#include "sensors.h"
#include "utils.h"
#include "inputs.h"

/*------------------------------------------------------------------------------------------------*/
/* MACROS                                                                                         */
/*------------------------------------------------------------------------------------------------*/

// I2C data packet structure (15 bytes total)
#define I2C_DATA_POSITION_OFFSET    0   // Offset for position (4 bytes)
#define I2C_DATA_VELOCITY_OFFSET    4   // Offset for velocity (4 bytes)
#define I2C_DATA_TIMESTAMP_OFFSET   8   // Offset for timestamp (4 bytes)
#define I2C_DATA_BUTTON_OFFSET      12  // Offset for button flags (1 byte)
#define I2C_DATA_POT_OFFSET         13  // Offset for potentiometer (2 bytes)

/*------------------------------------------------------------------------------------------------*/
/* GLOBAL VARIABLES                                                                               */
/*------------------------------------------------------------------------------------------------*/

static const char *TAG = "COMM";
static uint8_t i2c_data_buffer[I2C_DATA_PACKET_SIZE];

static input_data_t last_input_data = {0};

/*------------------------------------------------------------------------------------------------*/
/* FUNCTION PROTOTYPES                                                                            */
/*------------------------------------------------------------------------------------------------*/



/*------------------------------------------------------------------------------------------------*/
/* FUNCTION DEFINITIONS                                                                           */
/*------------------------------------------------------------------------------------------------*/

esp_err_t comm_init(void)
{
    esp_err_t ret;

    // Configure I2C in slave mode
    i2c_config_t conf_slave = {
        .mode = I2C_MODE_SLAVE,
        .sda_io_num = I2C_SLAVE_SDA_IO,
        .scl_io_num = I2C_SLAVE_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .slave.addr_10bit_en = 0,
        .slave.slave_addr = I2C_SLAVE_ADDR,
        .slave.maximum_speed = 100000,  // 100kHz
    };

    ret = i2c_param_config(I2C_SLAVE_NUM, &conf_slave);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to configure I2C parameters: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = i2c_driver_install(I2C_SLAVE_NUM, conf_slave.mode,
                             I2C_SLAVE_RX_BUF_LEN, I2C_SLAVE_TX_BUF_LEN, 0);
    if (ret != ESP_OK) {
        LOG_ERROR(TAG, "Failed to install I2C driver: %s", esp_err_to_name(ret));
        return ret;
    }

    // Initialize data buffer to zero
    memset(i2c_data_buffer, 0, I2C_DATA_PACKET_SIZE);

    LOG_INFO(TAG, "I2C slave initialized on SDA=%d, SCL=%d, Address=0x%02X, PacketSize=%d bytes",
             I2C_SLAVE_SDA_IO, I2C_SLAVE_SCL_IO, I2C_SLAVE_ADDR, I2C_DATA_PACKET_SIZE);

    return ESP_OK;
}

esp_err_t comm_update_encoder_data(void)
{
    // Get encoder data from sensors module
    int32_t position = encoder_get_position();
    float velocity = encoder_get_velocity(200);  // Assuming 200ms sample period
    uint32_t timestamp = (uint32_t)(esp_timer_get_time() / 1000);  // Convert to ms

    // Get input data (buttons + potentiometer)
    inputs_get_data(&last_input_data);

    // Pack data into buffer (little-endian format)
    // Position (4 bytes)
    i2c_data_buffer[I2C_DATA_POSITION_OFFSET + 0] = (position >> 0) & 0xFF;
    i2c_data_buffer[I2C_DATA_POSITION_OFFSET + 1] = (position >> 8) & 0xFF;
    i2c_data_buffer[I2C_DATA_POSITION_OFFSET + 2] = (position >> 16) & 0xFF;
    i2c_data_buffer[I2C_DATA_POSITION_OFFSET + 3] = (position >> 24) & 0xFF;

    // Velocity (4 bytes - as float converted to int32_t * 100 for fixed-point)
    int32_t velocity_fixed = (int32_t)(velocity * 100.0f);
    i2c_data_buffer[I2C_DATA_VELOCITY_OFFSET + 0] = (velocity_fixed >> 0) & 0xFF;
    i2c_data_buffer[I2C_DATA_VELOCITY_OFFSET + 1] = (velocity_fixed >> 8) & 0xFF;
    i2c_data_buffer[I2C_DATA_VELOCITY_OFFSET + 2] = (velocity_fixed >> 16) & 0xFF;
    i2c_data_buffer[I2C_DATA_VELOCITY_OFFSET + 3] = (velocity_fixed >> 24) & 0xFF;

    // Timestamp (4 bytes)
    i2c_data_buffer[I2C_DATA_TIMESTAMP_OFFSET + 0] = (timestamp >> 0) & 0xFF;
    i2c_data_buffer[I2C_DATA_TIMESTAMP_OFFSET + 1] = (timestamp >> 8) & 0xFF;
    i2c_data_buffer[I2C_DATA_TIMESTAMP_OFFSET + 2] = (timestamp >> 16) & 0xFF;
    i2c_data_buffer[I2C_DATA_TIMESTAMP_OFFSET + 3] = (timestamp >> 24) & 0xFF;

    // Button flags (1 byte)
    i2c_data_buffer[I2C_DATA_BUTTON_OFFSET] = last_input_data.button_flags;

    // Potentiometer value (2 bytes, little-endian)
    i2c_data_buffer[I2C_DATA_POT_OFFSET + 0] = (last_input_data.potentiometer >> 0) & 0xFF;
    i2c_data_buffer[I2C_DATA_POT_OFFSET + 1] = (last_input_data.potentiometer >> 8) & 0xFF;

    // Write data to I2C slave buffer (ready for master to read)
    int written = i2c_slave_write_buffer(I2C_SLAVE_NUM, i2c_data_buffer,
                                         I2C_DATA_PACKET_SIZE, 0);
    if (written < 0) {
        LOG_WARN(TAG, "Failed to write to I2C buffer");
        return ESP_FAIL;
    }

    // Clear button flags after successful transmission
    inputs_clear_button_flags();

    return ESP_OK;
}