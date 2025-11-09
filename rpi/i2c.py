#!/usr/bin/env python3
"""
Encoder Reader Module
Handles I2C communication with ESP32 and velocity smoothing
Includes predictive velocity tracking for low-resolution encoders
Also handles button input and potentiometer data
"""

import smbus2
from smbus2 import i2c_msg
import struct
import time
from collections import deque
from config import (
    DATA_PACKET_SIZE, VELOCITY_WINDOW_SIZE, DEBUG_PRINT_I2C,
    ENCODER_PPR, VELOCITY_PREDICTION, VELOCITY_TIMEOUT_MS,
    BUTTON_NAMES, POTENTIOMETER_MIN, POTENTIOMETER_MAX
)

class PredictiveVelocityTracker:
    """
    Predictive velocity tracking for low-resolution encoders (e.g., 24 PPR)

    Key concept: Between encoder ticks, maintain constant velocity prediction.
    Only update velocity when we detect actual position change.
    """
    def __init__(self, timeout_ms=VELOCITY_TIMEOUT_MS):
        self.last_position = None
        self.last_timestamp = None
        self.predicted_velocity = 0.0
        self.last_velocity_update_time = None
        self.timeout_ms = timeout_ms

    def update(self, position, timestamp):
        """
        Update velocity prediction based on position change

        Args:
            position: Current encoder position
            timestamp: Current timestamp (ms)

        Returns:
            float: Predicted velocity in counts/second
        """
        current_time_ms = time.time() * 1000  # Get actual system time

        # First reading - initialize
        if self.last_position is None:
            self.last_position = position
            self.last_timestamp = timestamp
            self.last_velocity_update_time = current_time_ms
            return 0.0

        # Check if position changed
        position_changed = (position != self.last_position)

        if position_changed:
            # Calculate velocity from position change
            delta_pos = position - self.last_position
            delta_time = (timestamp - self.last_timestamp) / 1000.0  # ms to seconds

            if delta_time > 0.001:  # Avoid division by zero
                new_velocity = delta_pos / delta_time
                self.predicted_velocity = new_velocity
                self.last_velocity_update_time = current_time_ms

            # Update tracking
            self.last_position = position
            self.last_timestamp = timestamp
        else:
            # Position hasn't changed - check timeout
            time_since_last_change = current_time_ms - self.last_velocity_update_time

            if time_since_last_change > self.timeout_ms:
                # No movement for too long - assume stopped
                self.predicted_velocity = 0.0

        return self.predicted_velocity

    def reset(self):
        """Reset the tracker"""
        self.last_position = None
        self.last_timestamp = None
        self.predicted_velocity = 0.0
        self.last_velocity_update_time = None


class EncoderSmoother:
    """
    Smooths encoder velocity calculations using a sliding window
    """
    def __init__(self, window_size=VELOCITY_WINDOW_SIZE):
        self.positions = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)
        self.window_size = window_size
        self.last_velocity = 0.0

    def update(self, position, timestamp):
        """
        Add new position/timestamp and calculate smoothed velocity

        Args:
            position: Current encoder position (counts)
            timestamp: Current timestamp (milliseconds)

        Returns:
            float: Smoothed velocity in counts/second
        """
        self.positions.append(position)
        self.timestamps.append(timestamp)

        # Need at least 2 samples to calculate velocity
        if len(self.positions) < 2:
            return 0.0

        # Calculate velocity from first to last sample in window
        delta_pos = self.positions[-1] - self.positions[0]
        delta_time = (self.timestamps[-1] - self.timestamps[0]) / 1000.0  # ms to seconds

        if delta_time > 0.001:  # Avoid division by zero
            velocity = delta_pos / delta_time
            self.last_velocity = velocity
            return velocity

        return self.last_velocity

    def reset(self):
        """Reset the smoother"""
        self.positions.clear()
        self.timestamps.clear()
        self.last_velocity = 0.0


class EncoderReader:
    """
    Reads dual encoder data from ESP32 via I2C
    Supports both traditional smoothing and predictive velocity tracking for each encoder
    """
    def __init__(self, bus, i2c_address, smoother=None, use_predictive=VELOCITY_PREDICTION):
        """
        Initialize encoder reader

        Args:
            bus: smbus2.SMBus instance
            i2c_address: I2C address of ESP32 slave
            smoother: EncoderSmoother instance (creates new one if None)
            use_predictive: Use predictive velocity tracking for low-PPR encoders
        """
        self.bus = bus
        self.i2c_address = i2c_address
        self.use_predictive = use_predictive

        # Separate trackers/smoothers for each encoder
        if use_predictive:
            self.tracker_enc1 = PredictiveVelocityTracker()
            self.tracker_enc2 = PredictiveVelocityTracker()
            print(f"EncoderReader@0x{i2c_address:02X}: Using predictive velocity for 2 encoders (PPR={ENCODER_PPR})")
        else:
            self.smoother_enc1 = smoother if smoother else EncoderSmoother()
            self.smoother_enc2 = EncoderSmoother()
            print(f"EncoderReader@0x{i2c_address:02X}: Using traditional smoothing for 2 encoders")

        self.last_enc1_position = 0
        self.last_enc2_position = 0
        self.last_timestamp = 0
        self.read_errors = 0
        self.total_reads = 0

    def read_raw_data(self):
        """
        Read raw data from ESP32 via I2C

        Returns:
            tuple: (enc1_pos, enc1_vel, enc2_pos, enc2_vel, timestamp, button_flags, volume_pot, slider_pot) or None on error
        """
        try:
            # Read 25 bytes from ESP32 slave (no register addressing)
            # ESP32 is a simple I2C slave - just read data directly
            msg = i2c_msg.read(self.i2c_address, DATA_PACKET_SIZE)
            self.bus.i2c_rdwr(msg)
            data = list(msg)

            # Unpack data (little-endian format)
            # Encoder 1 Position (4 bytes, signed int32)
            enc1_position = struct.unpack('<i', bytes(data[0:4]))[0]

            # Encoder 1 Velocity (4 bytes, signed int32, fixed-point * 100)
            enc1_vel_fixed = struct.unpack('<i', bytes(data[4:8]))[0]
            enc1_velocity_raw = enc1_vel_fixed / 100.0

            # Encoder 2 Position (4 bytes, signed int32)
            enc2_position = struct.unpack('<i', bytes(data[8:12]))[0]

            # Encoder 2 Velocity (4 bytes, signed int32, fixed-point * 100)
            enc2_vel_fixed = struct.unpack('<i', bytes(data[12:16]))[0]
            enc2_velocity_raw = enc2_vel_fixed / 100.0

            # Timestamp (4 bytes, unsigned int32)
            timestamp = struct.unpack('<I', bytes(data[16:20]))[0]

            # Button flags (1 byte, unsigned int8)
            button_flags = data[20]

            # Volume Potentiometer (2 bytes, unsigned int16)
            volume_pot = struct.unpack('<H', bytes(data[21:23]))[0]

            # Slider Potentiometer (2 bytes, unsigned int16)
            slider_pot = struct.unpack('<H', bytes(data[23:25]))[0]

            self.total_reads += 1
            return enc1_position, enc1_velocity_raw, enc2_position, enc2_velocity_raw, timestamp, button_flags, volume_pot, slider_pot

        except Exception as e:
            self.read_errors += 1
            if DEBUG_PRINT_I2C:
                print(f"Error reading I2C from 0x{self.i2c_address:02X}: {e}")
            return None

    def read(self):
        """
        Read all data from ESP32 and calculate smoothed or predicted velocity for both encoders

        Returns:
            dict: {
                'enc1_position': int,
                'enc1_velocity': float (smoothed or predicted, counts/s),
                'enc1_velocity_raw': float (from ESP32),
                'enc2_position': int,
                'enc2_velocity': float (smoothed or predicted, counts/s),
                'enc2_velocity_raw': float (from ESP32),
                'timestamp': int (ms),
                'button_flags': int (byte with button states),
                'buttons': dict (button_name -> bool),
                'buttons_pressed': list (names of pressed buttons),
                'volume_pot': int (0-4095),
                'volume_pot_normalized': float (0.0-1.0),
                'slider_pot': int (0-4095),
                'slider_pot_normalized': float (0.0-1.0),
                'predicted': bool (True if using prediction)
            } or None on error
        """
        raw_data = self.read_raw_data()

        if raw_data is None:
            return None

        enc1_position, enc1_velocity_raw, enc2_position, enc2_velocity_raw, timestamp, button_flags, volume_pot, slider_pot = raw_data

        # Calculate velocity for encoder 1
        if self.use_predictive:
            enc1_velocity = self.tracker_enc1.update(enc1_position, timestamp)
            predicted = True
        else:
            enc1_velocity = self.smoother_enc1.update(enc1_position, timestamp)
            predicted = False

        # Calculate velocity for encoder 2
        if self.use_predictive:
            enc2_velocity = self.tracker_enc2.update(enc2_position, timestamp)
        else:
            enc2_velocity = self.smoother_enc2.update(enc2_position, timestamp)

        self.last_enc1_position = enc1_position
        self.last_enc2_position = enc2_position
        self.last_timestamp = timestamp

        # Decode button flags
        buttons = {}
        buttons_pressed = []
        for i, name in enumerate(BUTTON_NAMES):
            is_pressed = bool(button_flags & (1 << i))
            buttons[name] = is_pressed
            if is_pressed:
                buttons_pressed.append(name)

        # Normalize potentiometer values (0-4095 -> 0.0-1.0)
        volume_pot_normalized = volume_pot / float(POTENTIOMETER_MAX)
        slider_pot_normalized = slider_pot / float(POTENTIOMETER_MAX)

        return {
            'enc1_position': enc1_position,
            'enc1_velocity': enc1_velocity,
            'enc1_velocity_raw': enc1_velocity_raw,
            'enc2_position': enc2_position,
            'enc2_velocity': enc2_velocity,
            'enc2_velocity_raw': enc2_velocity_raw,
            'timestamp': timestamp,
            'button_flags': button_flags,
            'buttons': buttons,
            'buttons_pressed': buttons_pressed,
            'volume_pot': volume_pot,
            'volume_pot_normalized': volume_pot_normalized,
            'slider_pot': slider_pot,
            'slider_pot_normalized': slider_pot_normalized,
            'predicted': predicted
        }

    def get_error_rate(self):
        """Get the I2C read error rate"""
        if self.total_reads == 0:
            return 0.0
        return self.read_errors / self.total_reads

    def reset_tracker(self):
        """Reset the velocity trackers/smoothers for both encoders"""
        if self.use_predictive:
            self.tracker_enc1.reset()
            self.tracker_enc2.reset()
        else:
            self.smoother_enc1.reset()
            self.smoother_enc2.reset()


def test_encoder_reader():
    """Test function to verify dual encoder reading and input data"""
    import time
    from config import I2C_BUS, ESP32_DECK1_ADDR

    print("Testing ESP32 Dual Encoder + Dual Potentiometer Data Reader")
    print(f"Reading from ESP32 at address 0x{ESP32_DECK1_ADDR:02X}")
    print("=" * 120)

    bus = smbus2.SMBus(I2C_BUS)
    encoder = EncoderReader(bus, ESP32_DECK1_ADDR)

    try:
        while True:
            data = encoder.read()

            if data:
                # Format button press list
                buttons_str = ", ".join(data['buttons_pressed']) if data['buttons_pressed'] else "None"

                # Print all data
                print(f"[{data['timestamp']:8d} ms] "
                      f"E1: {data['enc1_position']:6d} ({data['enc1_velocity']:6.1f}) | "
                      f"E2: {data['enc2_position']:6d} ({data['enc2_velocity']:6.1f}) | "
                      f"Vol: {data['volume_pot']:4d} | "
                      f"Sld: {data['slider_pot']:4d} | "
                      f"Btn: {buttons_str}")

            time.sleep(0.02)  # 50Hz

    except KeyboardInterrupt:
        print(f"\nExiting... Error rate: {encoder.get_error_rate():.2%}")
    finally:
        bus.close()


if __name__ == "__main__":
    test_encoder_reader()

