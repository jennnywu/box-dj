#!/usr/bin/env python3
"""
Raspberry Pi 5 I2C Master - Read encoder data from ESP32 slave

Wiring:
    ESP32          RPi5
    GPIO33 (SDA) → Pin 3 (SDA)
    GPIO32 (SCL) → Pin 5 (SCL)
    GND          → GND

Install: sudo apt-get install python3-smbus i2c-tools
Enable I2C: sudo raspi-config -> Interface Options -> I2C -> Enable
"""

import smbus2
import struct
import time

# I2C Configuration
I2C_BUS = 1              # RPi5 I2C bus (usually 1)
ESP32_I2C_ADDR = 0x42    # ESP32 slave address
DATA_PACKET_SIZE = 12    # 12 bytes: position(4) + velocity(4) + timestamp(4)

def read_encoder_data(bus):
    """
    Read encoder data from ESP32 via I2C

    Returns:
        tuple: (position, velocity, timestamp) or None on error
    """
    try:
        # Read 12 bytes from ESP32 slave
        data = bus.read_i2c_block_data(ESP32_I2C_ADDR, 0, DATA_PACKET_SIZE)

        # Unpack data (little-endian format)
        # position: int32 (signed)
        # velocity: int32 (signed, fixed-point * 100)
        # timestamp: uint32 (unsigned)
        position = struct.unpack('<i', bytes(data[0:4]))[0]
        velocity_fixed = struct.unpack('<i', bytes(data[4:8]))[0]
        timestamp = struct.unpack('<I', bytes(data[8:12]))[0]

        # Convert velocity from fixed-point to float
        velocity = velocity_fixed / 100.0

        return position, velocity, timestamp

    except Exception as e:
        print(f"Error reading I2C data: {e}")
        return None

def main():
    """Main function to continuously read encoder data"""
    print("Raspberry Pi 5 - ESP32 Encoder I2C Reader")
    print(f"Reading from ESP32 at address 0x{ESP32_I2C_ADDR:02X}")
    print("-" * 60)

    # Initialize I2C bus
    bus = smbus2.SMBus(I2C_BUS)

    try:
        while True:
            result = read_encoder_data(bus)

            if result:
                position, velocity, timestamp = result
                print(f"Position: {position:8d} counts | "
                      f"Velocity: {velocity:8.2f} counts/s | "
                      f"Time: {timestamp:10d} ms")

            time.sleep(0.01)  # Read every 200ms (matches ESP32 update rate)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bus.close()

if __name__ == "__main__":
    main()
