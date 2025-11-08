#!/usr/bin/env python3
"""
Test I2C connection to ESP32
Run this first to verify your I2C setup is working
"""

import sys
import time
import smbus2
from config import I2C_BUS, ESP32_DECK1_ADDR


def test_i2c_connection():
    """Test basic I2C connectivity"""
    print("="*70)
    print("I2C CONNECTION TEST")
    print("="*70)
    print(f"I2C Bus: {I2C_BUS}")
    print(f"ESP32 Address: 0x{ESP32_DECK1_ADDR:02X}")
    print("-"*70)

    try:
        bus = smbus2.SMBus(I2C_BUS)
        print("✓ I2C bus opened successfully")
    except Exception as e:
        print(f"✗ Failed to open I2C bus: {e}")
        print("\nTroubleshooting:")
        print("  1. Enable I2C: sudo raspi-config → Interface Options → I2C")
        print("  2. Install dependencies: sudo apt-get install python3-smbus i2c-tools")
        print("  3. Check wiring: ESP32 SDA→Pin3, SCL→Pin5, GND→GND")
        return False

    # Try to read from ESP32
    print(f"\nAttempting to read from ESP32 at 0x{ESP32_DECK1_ADDR:02X}...")

    success_count = 0
    fail_count = 0

    for i in range(10):
        try:
            data = bus.read_i2c_block_data(ESP32_DECK1_ADDR, 0, 12)
            success_count += 1
            print(f"  Read {i+1}/10: ✓ Received {len(data)} bytes")
            time.sleep(0.1)
        except Exception as e:
            fail_count += 1
            print(f"  Read {i+1}/10: ✗ Error: {e}")
            time.sleep(0.1)

    bus.close()

    print("\n" + "-"*70)
    print(f"Results: {success_count} successes, {fail_count} failures")

    if success_count == 0:
        print("\n✗ I2C CONNECTION FAILED")
        print("\nTroubleshooting:")
        print("  1. Check ESP32 is powered on and running I2C slave code")
        print("  2. Verify I2C address matches (ESP32 code should use 0x42)")
        print("  3. Run 'i2cdetect -y 1' to scan for devices")
        print("  4. Check wiring connections")
        return False
    elif success_count < 10:
        print("\n⚠ PARTIAL CONNECTION - Some reads failed")
        print("  Connection is working but unstable. Check:")
        print("  - Pull-up resistors (1.8kΩ - 4.7kΩ on SDA/SCL)")
        print("  - Wire length (keep < 30cm)")
        print("  - Power supply stability")
        return True
    else:
        print("\n✓ I2C CONNECTION PERFECT")
        print("  You can now run: python3 dj_mixer.py")
        return True


def test_encoder_data():
    """Test reading actual encoder data"""
    from encoder_reader import EncoderReader, EncoderSmoother

    print("\n" + "="*70)
    print("ENCODER DATA TEST")
    print("="*70)
    print("Rotate your encoder and watch the values change")
    print("Press Ctrl+C to stop")
    print("-"*70)

    bus = smbus2.SMBus(I2C_BUS)
    encoder = EncoderReader(bus, ESP32_DECK1_ADDR, EncoderSmoother())

    try:
        for i in range(100):  # Read 100 samples
            data = encoder.read()

            if data:
                print(f"Pos: {data['position']:6d} | "
                      f"Vel(smooth): {data['velocity']:7.1f} | "
                      f"Vel(raw): {data['velocity_raw']:6.1f}")
            else:
                print("Read failed")

            time.sleep(0.02)  # 50Hz

    except KeyboardInterrupt:
        print("\n\nStopped")
    finally:
        bus.close()
        print(f"Error rate: {encoder.get_error_rate():.2%}")


if __name__ == "__main__":
    # Test basic I2C connection
    if test_i2c_connection():
        print("\n" + "="*70)
        response = input("\nRun encoder data test? (y/n): ")
        if response.lower() == 'y':
            test_encoder_data()