# DJ Mixer Project - Complete Package

## What's Included

All files for your RPi5 DJ mixer with encoder control via ESP32 I2C communication.

### Core Files

1. **config.py** - Central configuration
   - Audio file paths
   - I2C settings (address, bus, poll rate)
   - Encoder parameters (velocity scaling, position ranges)
   - Control modes and debug flags

2. **encoder_reader.py** - I2C & Velocity Processing
   - `EncoderSmoother` class: Smooths velocity using sliding window
   - `EncoderReader` class: Handles I2C communication with ESP32
   - Standalone test mode: Run directly to test encoder reading

3. **dj_mixer.py** - Main Application
   - `DJDeck` class: Controls one deck (rate, volume, encoder)
   - `DJMixer` class: Full GStreamer pipeline + I2C integration
   - Supports single or dual encoder setups
   - Two control modes: velocity (scratching) or position (pitch slider)

4. **test_i2c.py** - Diagnostic Tool
   - Tests I2C connectivity
   - Verifies ESP32 communication
   - Shows live encoder data
   - Run this FIRST to verify everything works

### Documentation

5. **README.md** - Comprehensive Guide
   - Hardware requirements and wiring
   - Software installation steps
   - Configuration options explained
   - Troubleshooting guide
   - Performance tips

6. **QUICKSTART.md** - 5-Minute Setup
   - Minimal steps to get running
   - Quick troubleshooting checklist
   - Common sensitivity adjustments

7. **ESP32_REFERENCE.cpp** - ESP32 Code Guide
   - Explains required I2C protocol
   - Data format specification
   - Example encoder interrupt code
   - Dual ESP32 setup notes

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 5                          │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐                      │
│  │   MP3 File   │    │   MP3 File   │                      │
│  │   (Deck 1)   │    │   (Deck 2)   │                      │
│  └──────┬───────┘    └──────┬───────┘                      │
│         │                    │                              │
│         v                    v                              │
│  ┌──────────────┐    ┌──────────────┐                      │
│  │  filesrc +   │    │  filesrc +   │                      │
│  │  decodebin   │    │  decodebin   │  GStreamer           │
│  └──────┬───────┘    └──────┬───────┘  Pipeline            │
│         │                    │                              │
│         v                    v                              │
│  ┌──────────────┐    ┌──────────────┐                      │
│  │    pitch     │◄─┐ │    pitch     │◄─┐                   │
│  │  (rate ctrl) │  │ │  (rate ctrl) │  │  Rate Control     │
│  └──────┬───────┘  │ └──────┬───────┘  │  (from encoder)   │
│         │          │         │          │                   │
│         │   ┌──────┴─────────┴──────┐  │                   │
│         │   │  I2C Reader (50Hz)    │  │                   │
│         │   │  ┌──────────────────┐ │  │                   │
│         │   │  │ EncoderSmoother  │ ├──┘                   │
│         │   │  │ (velocity calc)  │ │                      │
│         │   │  └──────────────────┘ │                      │
│         │   └──────────▲─────────────┘                      │
│         │              │                                    │
│         v              │ I2C                                │
│  ┌──────────────┐      │ (Wire)                            │
│  │ audiomixer   │      │                                    │
│  │  (combine)   │      │                                    │
│  └──────┬───────┘      │                                    │
│         │              │                                    │
│         v              │                                    │
│  ┌──────────────┐      │                                    │
│  │  pulsesink   │      │                                    │
│  │  (to audio)  │      │                                    │
│  └──────────────┘      │                                    │
│                        │                                    │
└────────────────────────┼────────────────────────────────────┘
                         │
                         │ I2C (SDA/SCL/GND)
                         │
                ┌────────▼─────────┐
                │      ESP32       │
                │  ┌────────────┐  │
                │  │   Rotary   │  │
                │  │   Encoder  │  │
                │  └────────────┘  │
                │                  │
                │  Sends every 10ms:│
                │  - Position      │
                │  - Timestamp     │
                │  (velocity calc  │
                │   done on RPi)   │
                └──────────────────┘
```

## Key Design Decisions

### Why Calculate Velocity on RPi?
Your ESP32 velocity data showed excessive noise (±5 counts/s spikes). By calculating velocity on the RPi using a sliding window, we get:
- Smooth, predictable modulation
- Better responsiveness
- Reduced jitter from low-resolution ESP32 calculations

### Two Control Modes

**Velocity Mode (Scratching)**:
```python
rate = 1.0 + (velocity / VELOCITY_SCALE)
# Fast turn = fast playback, stop = normal speed
```

**Position Mode (Turntable)**:
```python
rate = 1.0 + ((position - center) / POSITION_RANGE)
# Position offset = speed change, maintains until moved
```

### Single vs Dual Encoder

**Single Encoder** (default):
- One ESP32 at address 0x42
- Both decks modulated identically
- Simpler setup, good for testing

**Dual Encoder**:
- Two ESP32s at 0x42 and 0x43
- Independent deck control
- True two-deck DJ setup
- Set `use_dual_encoders=True` in dj_mixer.py

## Installation Steps

1. **Copy files to RPi**:
   ```bash
   scp *.py *.md jenny@your-rpi:/home/jenny/box-dj/
   ```

2. **Install dependencies**:
   ```bash
   sudo apt-get install python3-smbus i2c-tools gstreamer1.0-plugins-bad
   pip3 install smbus2
   ```

3. **Enable I2C**:
   ```bash
   sudo raspi-config  # Interface Options → I2C
   ```

4. **Wire ESP32 to RPi**:
   - ESP32 GPIO33 (SDA) → RPi Pin 3
   - ESP32 GPIO32 (SCL) → RPi Pin 5
   - ESP32 GND → RPi GND
   - Add 2.2kΩ pull-ups on SDA/SCL

5. **Test connection**:
   ```bash
   python3 test_i2c.py
   ```

6. **Update config.py** with your MP3 paths

7. **Run**:
   ```bash
   python3 dj_mixer.py
   ```

## Configuration Highlights

### Sensitivity Tuning
```python
VELOCITY_SCALE = 100.0  # Higher = less sensitive
```
- Scratching: 50
- Normal: 100
- Smooth: 200

### Smoothing
```python
VELOCITY_WINDOW_SIZE = 5  # Samples for averaging
```
- More responsive: 3
- Balanced: 5
- Very smooth: 10

### Speed Limits
```python
MIN_PLAYBACK_RATE = 0.5   # Half speed
MAX_PLAYBACK_RATE = 2.0   # Double speed
```

### Polling Rate
```python
I2C_POLL_RATE_MS = 20  # 50Hz
```
- Lower = more responsive (but more CPU)
- Higher = less CPU (but less responsive)

## File Dependencies

```
dj_mixer.py
├── config.py (all settings)
├── encoder_reader.py
│   ├── config.py
│   └── smbus2
└── GStreamer (gi.repository.Gst)

test_i2c.py
├── config.py
└── encoder_reader.py
```

## Next Steps

1. Run `test_i2c.py` to verify connectivity
2. Adjust `VELOCITY_SCALE` in config.py for your preference
3. Try both velocity and position control modes
4. Add second ESP32 for dual deck control
5. Experiment with effects/EQ (see README for ideas)

## Support

All files are self-contained with extensive comments. Check:
- Comments in each .py file for implementation details
- README.md for comprehensive documentation
- QUICKSTART.md for immediate setup
- ESP32_REFERENCE.cpp for ESP32 code requirements

## Version Info

- Python: 3.x
- GStreamer: 1.0
- I2C Bus: 1 (standard for RPi5)
- ESP32 I2C: Slave mode at 0x42 (configurable)
- Protocol: 12-byte packets (position + velocity + timestamp)