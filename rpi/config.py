#!/usr/bin/env python3
"""
Configuration file for DJ Mixer system
"""

# ==================== PATHS ====================
HOME_PATH = "/home/jenny/box-dj/"
MUSIC_PATH_1 = "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"
MUSIC_PATH_2 = "rpi/example-mp3/charli-xcx-365.mp3"  # Only used if DUAL_DECK_MODE = True

# ==================== DECK CONFIGURATION ====================
DUAL_DECK_MODE = False  # Set to True for two-deck mixing, False for single deck

# ==================== I2C CONFIGURATION ====================
I2C_BUS = 1                    # RPi5 I2C bus (usually 1)
ESP32_DECK1_ADDR = 0x42        # ESP32 slave address for Deck 1
ESP32_DECK2_ADDR = 0x43        # ESP32 slave address for Deck 2 (if using two)
DATA_PACKET_SIZE = 12          # 12 bytes: position(4) + velocity(4) + timestamp(4)
I2C_POLL_RATE_MS = 20          # Poll I2C every 20ms (50Hz)

# ==================== ENCODER SETTINGS ====================
VELOCITY_WINDOW_SIZE = 10      # Longer window for low-resolution encoder (24 PPR)
MIN_PLAYBACK_RATE = 0.0        # Minimum playback speed (0 = stopped)
MAX_PLAYBACK_RATE = 3.0        # Maximum playback speed (3.0 = triple speed)

# Position-based control settings (only used in POSITION mode)
POSITION_CENTER = 1000         # Center position for neutral speed
POSITION_RANGE = 500           # ±500 counts for ±50% speed change

# Velocity-based control settings (only used in VELOCITY mode)
VELOCITY_SCALE = 100.0         # Velocity divisor for rate control (adjust for sensitivity)

# ==================== LOW-RESOLUTION ENCODER SETTINGS ====================
# For encoders with low PPR (pulses per revolution), we need predictive velocity
ENCODER_PPR = 24               # Pulses per revolution of your encoder
VELOCITY_PREDICTION = True     # Use predictive velocity tracking (recommended for PPR < 100)
VELOCITY_CHANGE_THRESHOLD = 0.15  # Only update rate if velocity changes by 15% or more
VELOCITY_TIMEOUT_MS = 500      # If no encoder change for 500ms, assume stopped

# ==================== AUDIO SETTINGS ====================
DEFAULT_VOLUME = 1.0           # Default volume (0.0 to 1.0)
VOLUME_STEP = 0.1              # Volume increment/decrement step

# ==================== CONTROL MODES ====================
# Control mode for deck speed
CONTROL_MODE_VELOCITY = "velocity"      # Use velocity for scratching/dynamic control
CONTROL_MODE_POSITION = "position"      # Use position for turntable-style pitch control
CONTROL_MODE_TURNTABLE = "turntable"    # Vinyl turntable mode - encoder velocity IS playback speed

# Default control modes for each deck
DECK1_CONTROL_MODE = CONTROL_MODE_VELOCITY  # Use turntable mode by default
DECK2_CONTROL_MODE = CONTROL_MODE_VELOCITY

# ==================== TURNTABLE MODE SETTINGS ====================
# This defines what encoder velocity means "normal speed" (1.0x playback)
# Calculate as: (Encoder PPR × Motor RPM) / 60
# Example: 24 PPR encoder, 10 RPM motor = (24 × 10) / 60 = 4 counts/second
NORMAL_SPEED_COUNTS_PER_SEC = 0.5

TURN_TABLE_BASELINE_VEL = NORMAL_SPEED_COUNTS_PER_SEC  # e.g., 4 counts/sec

# Velocity threshold for "stopped" turntable (pause playback)
# For low-resolution encoders, this should be very low
STOP_THRESHOLD_COUNTS_PER_SEC = 0.5  # If velocity < 0.5 counts/s, might be stopped

# Timeout for detecting actual stop (seconds)
# If no encoder movement for this long, consider it stopped
STOP_TIMEOUT_SEC = 0.5  # No position change for 0.5s = truly stopped

# Extrapolation: Keep playing at last known rate even when encoder doesn't change
# This smooths out low-resolution encoder readings
ENABLE_EXTRAPOLATION = True

# Allow negative velocity (playing backwards/scratching)
ALLOW_REVERSE_PLAYBACK = True

# ==================== DEBUG SETTINGS ====================
DEBUG_PRINT_I2C = True         # Print I2C read values
DEBUG_PRINT_RATE = True        # Print rate changes
DEBUG_PRINT_VOLUME = True      # Print volume changes

# ==================== SMOOTHING SETTINGS ====================
SMOOTHING_ALPHA = 0.9          # Exponential smoothing factor for rate transitions (0.0–1.0)
MAX_RATE_DELTA_PER_SEC = 1.6   # Optional hard cap on rate change speed (per second)

# ==================== SPEED THRESHOLDING ====================
NORMAL_SPEED_MIN = -120          # Minimum normal speed for smoothing calculations
NORMAL_SPEED_MAX = -80         # Maximum normal speed for smoothing calculations 
# TIME_TO_AVERAGE_SECONDS = 5     # Number of samples to average for speed thresholding

