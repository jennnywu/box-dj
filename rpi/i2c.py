#!/usr/bin/env python3
"""
Encoder Reader Module
Handles I2C communication with ESP32 and velocity smoothing
Includes predictive velocity tracking for low-resolution encoders
"""

import smbus2
import struct
import time
from collections import deque
from config import (
    DATA_PACKET_SIZE, VELOCITY_WINDOW_SIZE, DEBUG_PRINT_I2C,
    ENCODER_PPR, VELOCITY_PREDICTION, VELOCITY_TIMEOUT_MS
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
    Reads encoder data from ESP32 via I2C
    Supports both traditional smoothing and predictive velocity tracking
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

        if use_predictive:
            self.tracker = PredictiveVelocityTracker()
            print(f"EncoderReader@0x{i2c_address:02X}: Using predictive velocity (PPR={ENCODER_PPR})")
        else:
            self.smoother = smoother if smoother else EncoderSmoother()
            print(f"EncoderReader@0x{i2c_address:02X}: Using traditional smoothing")

        self.last_position = 0
        self.last_timestamp = 0
        self.read_errors = 0
        self.total_reads = 0

    def read_raw_data(self):
        """
        Read raw encoder data from ESP32 via I2C

        Returns:
            tuple: (position, velocity_raw, timestamp) or None on error
        """
        try:
            # Read 12 bytes from ESP32 slave
            data = self.bus.read_i2c_block_data(self.i2c_address, 0, DATA_PACKET_SIZE)

            # Unpack data (little-endian format)
            position = struct.unpack('<i', bytes(data[0:4]))[0]
            velocity_fixed = struct.unpack('<i', bytes(data[4:8]))[0]
            timestamp = struct.unpack('<I', bytes(data[8:12]))[0]

            # Convert velocity from fixed-point to float (ESP32 sends * 100)
            velocity_raw = velocity_fixed / 100.0

            self.total_reads += 1
            return position, velocity_raw, timestamp

        except Exception as e:
            self.read_errors += 1
            if DEBUG_PRINT_I2C:
                print(f"Error reading I2C from 0x{self.i2c_address:02X}: {e}")
            return None

    def read(self):
        """
        Read encoder data and calculate smoothed or predicted velocity

        Returns:
            dict: {
                'position': int,
                'velocity': float (smoothed or predicted, counts/s),
                'velocity_raw': float (from ESP32),
                'timestamp': int (ms),
                'predicted': bool (True if using prediction)
            } or None on error
        """
        raw_data = self.read_raw_data()

        if raw_data is None:
            return None

        position, velocity_raw, timestamp = raw_data

        # Calculate velocity based on mode
        if self.use_predictive:
            velocity = self.tracker.update(position, timestamp)
            predicted = True
        else:
            velocity = self.smoother.update(position, timestamp)
            predicted = False

        self.last_position = position
        self.last_timestamp = timestamp

        return {
            'position': position,
            'velocity': velocity,
            'velocity_raw': velocity_raw,
            'timestamp': timestamp,
            'predicted': predicted
        }

    def get_error_rate(self):
        """Get the I2C read error rate"""
        if self.total_reads == 0:
            return 0.0
        return self.read_errors / self.total_reads

    def reset_tracker(self):
        """Reset the velocity tracker/smoother"""
        if self.use_predictive:
            self.tracker.reset()
        else:
            self.smoother.reset()


def test_encoder_reader():
    """Test function to verify encoder reading"""
    import time
    from config import I2C_BUS, ESP32_DECK1_ADDR

    print("Testing Encoder Reader")
    print(f"Reading from ESP32 at address 0x{ESP32_DECK1_ADDR:02X}")
    print("-" * 70)

    bus = smbus2.SMBus(I2C_BUS)
    encoder = EncoderReader(bus, ESP32_DECK1_ADDR)

    try:
        while True:
            data = encoder.read()

            if data:
                print(f"Pos: {data['position']:6d} | "
                      f"Vel (smooth): {data['velocity']:7.1f} | "
                      f"Vel (raw): {data['velocity_raw']:6.1f} | "
                      f"Time: {data['timestamp']:8d} ms")

            time.sleep(0.02)  # 50Hz

    except KeyboardInterrupt:
        print(f"\nExiting... Error rate: {encoder.get_error_rate():.2%}")
    finally:
        bus.close()


if __name__ == "__main__":
    test_encoder_reader()

