# Box-DJ: Hardware DJ Mixing System

A complete hardware DJ controller system featuring dual rotary encoders, physical controls, and real-time audio manipulation. The system combines an ESP32 microcontroller for hardware I/O, a Raspberry Pi 5 for audio processing, and a web interface for music selection.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Hardware Components](#hardware-components)
- [Data Flow](#data-flow)
- [ESP32 Component](#esp32-component)
- [Raspberry Pi Component](#raspberry-pi-component)
- [Web Interface Component](#web-interface-component)
- [Setup Instructions](#setup-instructions)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [Troubleshooting](#troubleshooting)
- [Development Notes](#development-notes)

---

## Overview

Box-DJ is a physical DJ mixing system that allows you to:
- **Search and queue music** via Spotify search through a web interface
- **Download music** automatically from YouTube using yt-dlp
- **Control playback speed** in real-time using rotary encoders (scratching/turntable mode)
- **Mix dual audio decks** with independent speed control
- **Trigger sound effects** and control volume using physical buttons and potentiometers
- **Output audio** to Bluetooth headphones or speakers

### Key Features

✅ **Dual-deck audio mixing** with GStreamer pipelines  
✅ **Real-time speed modulation** (0.5x to 3.0x playback speed)
✅ **Multiple control modes**: Velocity (scratching), Position (pitch slider), Turntable (vinyl simulation)
✅ **Spotify search integration** with automatic YouTube download
✅ **Hardware I/O**: 2 encoders, 6 buttons, 2 potentiometers, motors, LED strips
✅ **Low-latency I2C communication** at 50Hz between ESP32 and RPi
✅ **Velocity smoothing algorithms** for jitter-free control with low-PPR encoders
✅ **Web-based playlist management** via Socket.IO

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           BOX-DJ SYSTEM ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────────┐
                              │   WEB BROWSER       │
                              │  (Music Selection)  │
                              │                     │
                              │  - Spotify Search   │
                              │  - Playlist Manager │
                              │  - Dual Deck View   │
                              └──────────┬──────────┘
                                         │
                                         │ WebSocket
                                         │ (Socket.IO)
                                         │
                                         ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                        RASPBERRY PI 5                                   │
    │                                                                         │
    │  ┌────────────────────────────────────────────────────────────────┐     │
    │  │  Flask/Socket.IO Server (Port 8080)                            │     │
    │  │  ┌──────────────────────────────────────────────────────────┐  │     │
    │  │  │  server.py                                               │  │     │
    │  │  │  - WebSocket event handling                              │  │     │
    │  │  │  - Spotify API search                                    │  │     │
    │  │  │  - Playlist management (2 decks)                         │  │     │
    │  │  │  - Background download tasks (yt-dlp)                    │  │     │
    │  │  │  - Saves MP3s to /dj_downloads/                          │  │     │
    │  │  └──────────────────────────────────────────────────────────┘  │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │  ┌────────────────────────────────────────────────────────────────┐     │
    │  │  Spotify Token Server (Port 6060)                              │     │
    │  │  - OAuth token generation                                      │     │
    │  │  - Token refresh handling                                      │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │  ┌────────────────────────────────────────────────────────────────┐     │
    │  │  GStreamer DJ Mixer (mixer.py)                                 │     │
    │  │                                                                │     │
    │  │  Deck 1 Pipeline:                                              │     │
    │  │  ┌───────────────────────────────────────────────────────┐     │     │
    │  │  │ filesrc → decodebin → audioconvert → pitch (rate)     │     │     │
    │  │  └─────────────────────────────┬─────────────────────────┘     │     │
    │  │                                │                               │     │
    │  │                                ▼                               │     │
    │  │                         ┌─────────────┐                        │     │
    │  │                         │ audiomixer  │ (combines both decks)  │     │
    │  │                         └──────┬──────┘                        │     │
    │  │                                │                               │     │
    │  │  ┌─────────────────────────────┴─────────────────────────┐     │     │
    │  │  │ filesrc → decodebin → audioconvert → pitch (rate)     │     │     │
    │  │  └───────────────────────────────────────────────────────┘     │     │
    │  │  Deck 2 Pipeline:                                              │     │
    │  │                                │                               │     │
    │  │                                ▼                               │     │
    │  │                         ┌─────────────┐                        │     │
    │  │                         │  pulsesink  │ → PulseAudio           │     │
    │  │                         └─────────────┘   → Bluetooth          │     │
    │  │                                                                │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    │                                ▲                                        │
    │                                │ Encoder/Button/Pot Data                │
    │                                │ (every 20ms, 50Hz)                     │
    │  ┌─────────────────────────────┴──────────────────────────────────┐     │
    │  │  I2C Reader & Processor (i2c.py)                               │     │
    │  │                                                                │     │
    │  │  ┌──────────────────────────────────────────────────────────┐  │     │
    │  │  │  Read 25-byte I2C packet from ESP32                      │  │     │
    │  │  │  - Encoder 1 position (4 bytes)                          │  │     │
    │  │  │  - Encoder 1 velocity (4 bytes, fixed-point)             │  │     │
    │  │  │  - Encoder 2 position (4 bytes)                          │  │     │
    │  │  │  - Encoder 2 velocity (4 bytes, fixed-point)             │  │     │
    │  │  │  - Timestamp (4 bytes)                                   │  │     │
    │  │  │  - Button flags (1 byte, 6 buttons)                      │  │     │
    │  │  │  - Volume pot (2 bytes, 12-bit ADC)                      │  │     │
    │  │  │  - Slider pot (2 bytes, 12-bit ADC)                      │  │     │
    │  │  └──────────────────────────────────────────────────────────┘  │     │
    │  │                                                                │     │
    │  │  ┌──────────────────────────────────────────────────────────┐  │     │
    │  │  │  EncoderSmoother / PredictiveVelocityTracker             │  │     │
    │  │  │  - Sliding window averaging (5-10 samples)               │  │     │
    │  │  │  - Eliminates jitter from low-PPR encoders (24 PPR)      │  │     │
    │  │  │  - Predictive velocity for ultra-low resolution          │  │     │
    │  │  └──────────────────────────────────────────────────────────┘  │     │
    │  │                                                                │     │
    │  │  ┌──────────────────────────────────────────────────────────┐  │     │
    │  │  │  Button State Decoder                                    │  │     │
    │  │  │  - Extracts 6 button states from 1 byte                  │  │     │
    │  │  └──────────────────────────────────────────────────────────┘  │     │
    │  │                                                                │     │
    │  │  ┌──────────────────────────────────────────────────────────┐  │     │
    │  │  │  Potentiometer Normalizer                                │  │     │
    │  │  │  - Converts 0-4095 ADC → 0.0-1.0 float                   │  │     │
    │  │  └──────────────────────────────────────────────────────────┘  │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    │                                ▲                                        │
    │                                │ I2C (SDA/SCL/GND)                      │
    └────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     │
                                     │
        ┌────────────────────────────┴─────────────────────────────┐
        │                     ESP32 MICROCONTROLLER                │
        │                  (Hardware Input Controller)             │
        │                                                          │
        │  ┌───────────────────────────────────────────────────┐   │
        │  │  FreeRTOS Task Manager (Dual Core)                │   │
        │  │                                                   │   │
        │  │  Core 0:                    Core 1:               │   │
        │  │  - LED scrolling            - I2C comm task       │   │
        │  │    (priority 3, 200ms)        (priority 10, 10ms) │   │
        │  └───────────────────────────────────────────────────┘   │
        │                                                          │
        │  ┌───────────────────────────────────────────────────┐   │
        │  │  I2C Slave Communication (comm.c/h)               │   │
        │  │  Address: 0x42                                    │   │
        │  │  Buffer: 25 bytes, updated every 10ms             │   │
        │  └───────────────────────────────────────────────────┘   │
        │                                                          │
        │  ┌───────────────────────────────────────────────────┐   │
        │  │  Hardware Input Modules:                          │   │
        │  │                                                   │   │
        │  │  ┌─────────────────────────────────────────────┐  │   │
        │  │  │  sensors.c - Dual Rotary Encoders (PCNT)    │  │   │
        │  │  │  - Encoder 1: GPIO26 (A), GPIO27 (B)        │  │   │
        │  │  │  - Encoder 2: GPIO14 (A), GPIO15 (B)        │  │   │
        │  │  │  - Quadrature counting (±10000 range)       │  │   │
        │  │  │  - Velocity calculation (counts/sec)        │  │   │
        │  │  └─────────────────────────────────────────────┘  │   │
        │  │                                                   │   │
        │  │  ┌─────────────────────────────────────────────┐  │   │
        │  │  │  inputs.c - Buttons & Potentiometers        │  │   │
        │  │  │  - 6 Buttons (GPIO interrupts,50ms debounce)│  │   │
        │  │  │    • SFX_1: GPIO4                           │  │   │
        │  │  │    • SFX_2: GPIO16                          │  │   │
        │  │  │    • SFX_3: GPIO17                          │  │   │
        │  │  │    • SFX_4: GPIO5                           │  │   │
        │  │  │    • SONG_1: GPIO12                         │  │   │
        │  │  │    • SONG_2: GPIO13                         │  │   │
        │  │  │  - 2 Potentiometers (12-bit ADC)            │  │   │
        │  │  │    • Volume: GPIO34 (ADC_CHANNEL_6)         │  │   │
        │  │  │    • Slider: GPIO35 (ADC_CHANNEL_7)         │  │   │
        │  │  └─────────────────────────────────────────────┘  │   │
        │  │                                                   │   │
        │  │  ┌─────────────────────────────────────────────┐  │   │
        │  │  │  motors.c - Motor Control (PWM)             │  │   │
        │  │  │  - Motor B: GPIO22/23 (IN3/IN4 direction)   │  │   │
        │  │  │  - Enable: GPIO25 (PWM, 5kHz, 0-255 duty)   │  │   │
        │  │  └─────────────────────────────────────────────┘  │   │
        │  │                                                   │   │
        │  │  ┌─────────────────────────────────────────────┐  │   │
        │  │  │  leds.c - LED Strip Animation               │  │   │
        │  │  │  - Scrolling pattern, 200ms updates         │  │   │
        │  │  └─────────────────────────────────────────────┘  │   │
        │  │                                                   │   │
        │  │  ┌─────────────────────────────────────────────┐  │   │
        │  │  │  lcd.c - LCD Display (currently disabled)   │  │   │
        │  │  └─────────────────────────────────────────────┘  │   │
        │  └───────────────────────────────────────────────────┘   │
        └──────────────────────────────────────────────────────────┘
```

---

## Hardware Components

### ESP32 Microcontroller

**Purpose**: Hardware I/O controller that reads all physical inputs and communicates with Raspberry Pi via I2C.

**Specifications**:
- ESP32-DevKitC or compatible
- Dual-core processor (240 MHz)
- FreeRTOS for task management
- I2C slave mode at address 0x42

### Raspberry Pi 5

**Purpose**: Main audio processing unit, music server, and web server.

**Specifications**:
- Raspberry Pi 5 (or RPi 4)
- Running Raspberry Pi OS (Debian-based)
- PulseAudio for Bluetooth audio output
- GStreamer 1.0 for audio pipeline processing
- I2C master at 50Hz polling rate

### Input Hardware

| Component | GPIO/Interface | Type | Purpose |
|-----------|---------------|------|---------|
| **Rotary Encoder 1** | GPIO26 (A), GPIO27 (B) | Quadrature | Deck 1 speed control |
| **Rotary Encoder 2** | GPIO14 (A), GPIO15 (B) | Quadrature | Deck 2 speed control |
| **SFX Button 1** | GPIO4 | Digital input | Sound effect trigger |
| **SFX Button 2** | GPIO16 | Digital input | Sound effect trigger |
| **SFX Button 3** | GPIO17 | Digital input | Sound effect trigger |
| **SFX Button 4** | GPIO5 | Digital input | Sound effect trigger |
| **Song Button 1** | GPIO12 | Digital input | Song selection |
| **Song Button 2** | GPIO13 | Digital input | Song selection |
| **Volume Potentiometer** | GPIO34 (ADC_CHANNEL_6) | Analog input | Master volume |
| **Slider Potentiometer** | GPIO35 (ADC_CHANNEL_7) | Analog input | Filter/effect control |
| **Motor B** | GPIO22/23/25 | PWM output | Haptic feedback |
| **LED Strip** | GPIO (SPI/Serial) | Digital output | Visual feedback |

### Wiring Diagram

```
┌─────────────────────┐                    ┌─────────────────────┐
│      ESP32          │                    │   Raspberry Pi 5    │
│                     │                    │                     │
│  GPIO33 (SDA) ──────┼────────────────────┼──→ Pin 3 (GPIO2)    │
│  GPIO32 (SCL) ──────┼────────────────────┼──→ Pin 5 (GPIO3)    │
│  GND ───────────────┼────────────────────┼──→ GND              │
│                     │                    │                     │
└─────────────────────┘                    └─────────────────────┘

⚠️ IMPORTANT: Add 2.2kΩ - 4.7kΩ pull-up resistors on both SDA and SCL lines!

       3.3V
         │
         ├─── 2.2kΩ ───┤
         │              SDA ───────────────────
         ├─── 2.2kΩ ───┤
         │              SCL ───────────────────
```

---

## Data Flow

### Complete System Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 1. MUSIC SELECTION FLOW (User → Web → RPi → Audio File)                  │
└──────────────────────────────────────────────────────────────────────────┘

User types "Chappell Roan Red Wine"
    │
    └─→ Browser sends 'SEARCH' event via WebSocket
        │
        └─→ Flask server (server.py) receives request
            │
            ├─→ Validates Spotify token (refresh if needed)
            │
            └─→ Spotify API search
                │
                └─→ Returns 10 matching tracks with metadata
                    │
                    └─→ Server emits 'search_results' to browser
                        │
                        └─→ User clicks "Add to Deck 1"
                            │
                            └─→ Browser sends 'ADD_SONG' event
                                │
                                └─→ Server creates unique hash ID
                                    │
                                    ├─→ Adds song to playlist[deck_id]
                                    ├─→ Broadcasts 'playlist_update'
                                    │
                                    └─→ Spawns background thread
                                        │
                                        └─→ yt-dlp extracts audio
                                            │
                                            ├─→ Downloads from YouTube
                                            ├─→ Converts to MP3
                                            ├─→ Saves to /dj_downloads/
                                            │
                                            └─→ Updates song.download_path
                                                │
                                                └─→ Emits 'playlist_update'

┌──────────────────────────────────────────────────────────────────────────┐
│ 2. HARDWARE CONTROL FLOW (Encoder → ESP32 → RPi → Audio Modulation)      │
└──────────────────────────────────────────────────────────────────────────┘

User rotates Encoder 1 clockwise
    │
    └─→ Mechanical quadrature pulses
        │
        └─→ ESP32 PCNT peripheral captures pulses
            │
            ├─→ Position increments (+1 per pulse)
            ├─→ Velocity calculated (noisy on ESP32)
            │
            └─→ Every 10ms: i2c_comm_task() runs
                │
                └─→ comm_update_encoder_data()
                    │
                    ├─→ encoder_get_position(ENCODER_1) → int32_t
                    ├─→ encoder_get_velocity(ENCODER_1) → float × 100
                    ├─→ encoder_get_position(ENCODER_2) → int32_t
                    ├─→ encoder_get_velocity(ENCODER_2) → float × 100
                    ├─→ inputs_get_data() → buttons + pots
                    ├─→ esp_timer_get_time() / 1000 → timestamp
                    │
                    └─→ Pack into 25-byte I2C slave buffer
                        │
                        [Buffer contents:]
                        Bytes 0-3:   Encoder 1 position (little-endian int32)
                        Bytes 4-7:   Encoder 1 velocity × 100 (little-endian int32)
                        Bytes 8-11:  Encoder 2 position (little-endian int32)
                        Bytes 12-15: Encoder 2 velocity × 100 (little-endian int32)
                        Bytes 16-19: Timestamp (little-endian uint32)
                        Byte 20:     Button flags (bits 0-5)
                        Bytes 21-22: Volume pot (little-endian uint16)
                        Bytes 23-24: Slider pot (little-endian uint16)

                        │
                        └─→ RPi reads every 20ms (50Hz)
                            │
                            └─→ i2c.py: read_encoder_data()
                                │
                                ├─→ i2c_bus.read_i2c_block_data(0x42, 0, 25)
                                ├─→ struct.unpack('<iiiiiIBHH', data)
                                │
                                └─→ Apply smoothing algorithm
                                    │
                                    ┌──────────────────────────────────┐
                                    │ EncoderSmoother                  │
                                    │ - Keep last 10 position samples  │
                                    │ - velocity = (pos[-1] - pos[0])  │
                                    │              / time_span         │
                                    │ - Eliminates ±5 count/s jitter   │
                                    └──────────────────────────────────┘
                                    │
                                    │ OR (for very low PPR encoders):
                                    │
                                    ┌──────────────────────────────────┐
                                    │ PredictiveVelocityTracker        │
                                    │ - Only updates when pos changes  │
                                    │ - Maintains constant velocity    │
                                    │   between ticks                  │
                                    │ - Assumes stopped after 500ms    │
                                    └──────────────────────────────────┘
                                    │
                                    └─→ Returns smoothed sensor dict:
                                        {
                                          'enc1_position': 1523,
                                          'enc1_velocity': 42.3,  ← smoothed
                                          'enc2_position': -234,
                                          'enc2_velocity': -15.7, ← smoothed
                                          'timestamp': 82374,
                                          'buttons': {
                                            'SFX_1': False,
                                            'SFX_2': True,
                                            ...
                                          },
                                          'volume_pot_normalized': 0.67,
                                          'slider_pot_normalized': 0.23
                                        }
                                        │
                                        └─→ mixer.py: DJDeck.update_from_encoder()
                                            │
                                            └─→ Select control mode:
                                                │
                                                ┌────────────────────────────┐
                                                │ VELOCITY MODE              │
                                                │ rate = 1.0 + (velocity /   │
                                                │             VELOCITY_SCALE)│
                                                │ • Fast turn = fast play    │
                                                │ • Stop = normal speed      │
                                                │ • Good for scratching      │
                                                └────────────────────────────┘
                                                │
                                                ┌────────────────────────────┐
                                                │ POSITION MODE              │
                                                │ rate = 1.0+((pos - center) │
                                                │           / POSITION_RANGE)│
                                                │ • Position offset = speed  │
                                                │ • Maintains until moved    │
                                                │ • Like pitch slider        │
                                                └────────────────────────────┘
                                                │
                                                ┌────────────────────────────┐
                                                │ TURNTABLE MODE             │
                                                │ if velocity ≈ NORMAL_SPEED:│
                                                │   rate = 1.0               │
                                                │ else:                      │
                                                │   rate = velocity /        │
                                                │          NORMAL_SPEED      │
                                                │ • Vinyl simulation         │
                                                │ • Encoder velocity IS speed│
                                                └────────────────────────────┘
                                                │
                                                └─→ Clamp to [MIN_RATE, MAX_RATE]
                                                    │ (typically 0.0x to 3.0x)
                                                    │
                                                    └─→ GStreamer pitch element
                                                        │
                                                        └─→ self.rate_element.set_property("rate", new_rate)
                                                            │
                                                            └─→ Time-stretches audio
                                                                │ (speed changes without pitch shift)
                                                                │
                                                                └─→ Dual decks → audiomixer
                                                                    │
                                                                    └─→ pulsesink
                                                                        │
                                                                        └─→ PulseAudio
                                                                            │
                                                                            └─→ Bluetooth headphones
                                                                                │
                                                                                └─→ 🎵 User hears modulated music
```

### I2C Protocol Specification

**Communication Format**: 25-byte packets, little-endian

| Byte Range | Size | Data Type | Field | Description |
|------------|------|-----------|-------|-------------|
| 0-3 | 4 | int32_t | Encoder 1 Position | Current position in counts |
| 4-7 | 4 | int32_t | Encoder 1 Velocity | Velocity × 100 (fixed-point) |
| 8-11 | 4 | int32_t | Encoder 2 Position | Current position in counts |
| 12-15 | 4 | int32_t | Encoder 2 Velocity | Velocity × 100 (fixed-point) |
| 16-19 | 4 | uint32_t | Timestamp | Milliseconds since ESP32 boot |
| 20 | 1 | uint8_t | Button Flags | Bits 0-5 = buttons 1-6 |
| 21-22 | 2 | uint16_t | Volume Pot | ADC value (0-4095) |
| 23-24 | 2 | uint16_t | Slider Pot | ADC value (0-4095) |

**Update Rate**:
- ESP32 updates buffer: Every 10ms
- RPi polls buffer: Every 20ms (50Hz)

**Button Flag Encoding**:
```
Bit 0: SFX_1
Bit 1: SFX_2
Bit 2: SFX_3
Bit 3: SFX_4
Bit 4: SONG_1
Bit 5: SONG_2
Bits 6-7: Unused
```

---

## ESP32 Component

### Project Structure

```
esp32-project/
├── main/
│   ├── main.c              # Application entry point, FreeRTOS task creation
│   ├── comm.c / comm.h     # I2C slave communication
│   ├── sensors.c / sensors.h   # Rotary encoder reading (PCNT)
│   ├── inputs.c / inputs.h     # Button & potentiometer inputs
│   ├── motors.c / motors.h     # Motor control (PWM)
│   ├── leds.c / leds.h         # LED strip animation
│   ├── lcd.c / lcd.h           # LCD display (currently disabled)
│   └── CMakeLists.txt
├── include/
│   └── utils.h             # Logging macros
├── build/                  # Compiled binaries
└── sdkconfig              # ESP-IDF configuration

Dependencies:
└── esp-idf-lib/           # External ESP32 libraries
```

### Key Modules

#### 1. **main.c** - Application Entry

**Responsibilities**:
- Initialize all hardware modules
- Create FreeRTOS tasks on both cores
- Manage task priorities

**FreeRTOS Tasks**:

| Task | Core | Priority | Period | Function |
|------|------|----------|--------|----------|
| `i2c_comm_task` | 1 | 10 (highest) | 10ms | Update I2C buffer with sensor data |
| `led_task` | 0 | 3 | 200ms | Animate LED strip |
| `encoder_read_task` | 0 | 10 | - | Currently disabled |

**Code Reference**: `/esp32-project/main/main.c`

#### 2. **comm.c/h** - I2C Communication

**Responsibilities**:
- Initialize I2C in slave mode at address 0x42
- Maintain 25-byte data buffer
- Update buffer with latest sensor readings every 10ms

**Key Functions**:
```c
esp_err_t comm_init(void);
// Initialize I2C slave with 128-byte TX/RX buffers

esp_err_t comm_update_encoder_data(void);
// Called every 10ms by i2c_comm_task
// Reads all sensors and packs into I2C buffer
```

**Configuration**:
```c
#define I2C_SLAVE_ADDR       0x42
#define I2C_SLAVE_SDA_IO     GPIO_NUM_33
#define I2C_SLAVE_SCL_IO     GPIO_NUM_32
#define I2C_DATA_PACKET_SIZE 25
```

**Code Reference**: `/esp32-project/main/comm.c`, `/esp32-project/include/comm.h:1`

#### 3. **sensors.c/h** - Rotary Encoders

**Responsibilities**:
- Configure PCNT (Pulse Counter) hardware for quadrature decoding
- Track position for two encoders
- Calculate velocity (counts per second)

**Hardware Setup**:
- Uses ESP32 PCNT peripheral (hardware-based counting, no interrupts needed)
- Each encoder uses 2 GPIO pins (A and B phases)
- Count range: -10000 to +10000 (configurable)

**Key Functions**:
```c
void encoder_init(encoder_id_t encoder_id, gpio_num_t pin_a, gpio_num_t pin_b);
int32_t encoder_get_position(encoder_id_t encoder_id);
float encoder_get_velocity(encoder_id_t encoder_id);  // counts/sec
void encoder_reset(encoder_id_t encoder_id);
```

**Code Reference**: `/esp32-project/main/sensors.c`

#### 4. **inputs.c/h** - Buttons & Potentiometers

**Responsibilities**:
- Read 6 buttons with 50ms debouncing
- Read 2 potentiometers via 12-bit ADC
- Pack button states into single byte

**Button Configuration**:
```c
button_id_t buttons[6] = {
    {BUTTON_SFX_1,  GPIO_NUM_4,  false},
    {BUTTON_SFX_2,  GPIO_NUM_16, false},
    {BUTTON_SFX_3,  GPIO_NUM_17, false},
    {BUTTON_SFX_4,  GPIO_NUM_5,  false},
    {BUTTON_SONG_1, GPIO_NUM_12, false},
    {BUTTON_SONG_2, GPIO_NUM_13, false}
};
```

**ADC Configuration**:
- Resolution: 12-bit (0-4095)
- Attenuation: 11dB (measures 0-3.3V)
- Sample time: ~1ms

**Key Functions**:
```c
void inputs_init(void);
inputs_data_t inputs_get_data(void);  // Returns button flags + pot values
bool inputs_button_pressed(button_id_t button);
uint16_t inputs_get_volume_pot(void);
uint16_t inputs_get_slider_pot(void);
```

**Code Reference**: `/esp32-project/main/inputs.c`

#### 5. **motors.c/h** - Motor Control

**Responsibilities**:
- Control motor direction and speed via PWM
- Provide haptic feedback

**Hardware Setup**:
- L298N motor driver or similar
- 3 control pins: IN3, IN4 (direction), EN (speed via PWM)
- PWM frequency: 5kHz
- Duty cycle: 0-255 (8-bit resolution)

**Key Functions**:
```c
void motor_init(void);
void motor_set_speed(uint8_t speed);         // 0-255
void motor_set_direction(motor_dir_t dir);   // FORWARD, BACKWARD, STOP
void motor_brake(void);
```

**Code Reference**: `/esp32-project/main/motors.c`

#### 6. **leds.c/h** - LED Control

**Responsibilities**:
- Animate LED strip with scrolling patterns
- Provide visual feedback

**Update Rate**: 200ms (5 FPS)

**Code Reference**: `/esp32-project/main/leds.c`

### ESP32 Setup Instructions

#### Prerequisites

1. **Install ESP-IDF** (Espressif IoT Development Framework)

```bash
# Clone ESP-IDF v5.x
git clone -b v5.1 --recursive https://github.com/espressif/esp-idf.git ~/esp-idf

# Install dependencies
cd ~/esp-idf
./install.sh

# Set up environment (add to ~/.bashrc or ~/.zshrc)
alias get_idf='. $HOME/esp-idf/export.sh'
```

2. **Install USB-to-Serial Drivers**
   - CP210x or CH340 drivers (depending on your ESP32 board)

#### Building and Flashing

```bash
# Navigate to project directory
cd /path/to/box-dj/esp32-project

# Set up ESP-IDF environment
get_idf

# Configure project (optional, for customization)
idf.py menuconfig

# Build firmware
idf.py build

# Flash to ESP32 (replace /dev/ttyUSB0 with your port)
idf.py -p /dev/ttyUSB0 flash

# Monitor serial output
idf.py -p /dev/ttyUSB0 monitor

# Or combine flash + monitor
idf.py -p /dev/ttyUSB0 flash monitor
```

#### Finding ESP32 Serial Port

**macOS**:
```bash
ls /dev/cu.* | grep -i usb
# Example: /dev/cu.usbserial-0001
```

**Linux**:
```bash
ls /dev/ttyUSB* /dev/ttyACM*
# Example: /dev/ttyUSB0
```

**Windows**:
- Check Device Manager → Ports (COM & LPT)
- Look for "Silicon Labs CP210x" or "CH340"

#### Verifying I2C Communication

After flashing, test I2C from Raspberry Pi:

```bash
# Scan for I2C devices
i2cdetect -y 1

# Expected output:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 10:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 20:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 30:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 40:          -- -- 42 -- -- -- -- -- -- -- -- -- --
#                    ^^-- ESP32 at address 0x42
```

### ESP32 Configuration Options

Edit `sdkconfig` or use `idf.py menuconfig`:

**I2C Configuration**:
- Bus speed: 100kHz (default) or 400kHz
- Slave address: 0x42 (configurable in `comm.h`)

**FreeRTOS Configuration**:
- Tick rate: 100Hz (10ms tick period)
- Task priorities: 0-25 (higher = more priority)

**GPIO Configuration**:
- All GPIO assignments in respective module `.h` files

---

## Raspberry Pi Component

### Project Structure

```
rpi/
├── config.py              # Centralized configuration
├── mixer.py              # Main GStreamer DJ mixer
├── i2c.py                # I2C communication + velocity smoothing
├── server.py             # Flask/Socket.IO music server
├── test.py               # Testing utilities
├── requirements.txt      # Python dependencies
├── README.md             # RPi documentation
├── example-mp3/          # Test MP3 files
│   ├── chappell-roan-red-wine-supernova.mp3
│   └── charli-xcx-365.mp3
└── dj_downloads/         # Downloaded music from YouTube (created at runtime)
```

### Key Modules

#### 1. **config.py** - Centralized Configuration

**Purpose**: Single source of truth for all system settings.

**Key Configuration Sections**:

```python
# Paths
HOME_PATH = "/home/jenny/box-dj/"
MUSIC_PATH_1 = "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"
MUSIC_PATH_2 = "rpi/example-mp3/charli-xcx-365.mp3"

# I2C Settings
I2C_BUS = 1
ESP32_DECK1_ADDR = 0x42
DATA_PACKET_SIZE = 25
I2C_POLL_RATE_MS = 20  # 50Hz

# Control Modes
CONTROL_MODE_VELOCITY = "velocity"     # Scratching
CONTROL_MODE_POSITION = "position"     # Pitch slider
CONTROL_MODE_TURNTABLE = "turntable"   # Vinyl simulation

DECK1_CONTROL_MODE = CONTROL_MODE_VELOCITY
DECK2_CONTROL_MODE = CONTROL_MODE_VELOCITY

# Encoder Settings (for low-PPR encoders)
ENCODER_PPR = 24
VELOCITY_WINDOW_SIZE = 10              # Smoothing window
VELOCITY_PREDICTION = True             # Predictive velocity
VELOCITY_TIMEOUT_MS = 500              # Stop detection timeout

# Playback Settings
MIN_PLAYBACK_RATE = 0.0                # 0x = stopped
MAX_PLAYBACK_RATE = 3.0                # 3x = triple speed
VELOCITY_SCALE = 100.0                 # Sensitivity (higher = less sensitive)

# Turntable Mode Settings
NORMAL_SPEED_COUNTS_PER_SEC = 0.5      # What encoder velocity = 1.0x playback
STOP_THRESHOLD_COUNTS_PER_SEC = 0.5    # Below this = considered stopped

# Debug Flags
DEBUG_PRINT_I2C = True
DEBUG_PRINT_RATE = True
DEBUG_PRINT_VOLUME = True
```

**Code Reference**: `/rpi/config.py:1`

#### 2. **i2c.py** - I2C Communication & Velocity Smoothing

**Purpose**: Read sensor data from ESP32 and apply smoothing algorithms.

**Key Classes**:

**`EncoderSmoother`** - Sliding Window Velocity Calculation
```python
class EncoderSmoother:
    """
    Smooths encoder velocity using sliding window average.
    Recommended for encoders with PPR 24-100.
    """
    def __init__(self, window_size=10):
        self.positions = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)

    def update(self, position, timestamp):
        self.positions.append(position)
        self.timestamps.append(timestamp)

        if len(self.positions) < 2:
            return 0.0

        # Velocity = (last - first) / time_span
        delta_pos = self.positions[-1] - self.positions[0]
        delta_time = (self.timestamps[-1] - self.timestamps[0]) / 1000.0

        return delta_pos / delta_time if delta_time > 0 else 0.0
```

**`PredictiveVelocityTracker`** - For Ultra-Low PPR Encoders
```python
class PredictiveVelocityTracker:
    """
    Maintains constant velocity between encoder ticks.
    Recommended for encoders with PPR < 24.
    Only updates velocity when position actually changes.
    """
    def update(self, position, timestamp):
        if position != self.last_position:
            # Position changed - calculate new velocity
            delta = position - self.last_position
            time_span = (timestamp - self.last_timestamp) / 1000.0
            self.predicted_velocity = delta / time_span
            self.last_change_time = timestamp
        else:
            # Position hasn't changed
            if (timestamp - self.last_change_time) > VELOCITY_TIMEOUT_MS:
                self.predicted_velocity = 0.0  # Assume stopped

        return self.predicted_velocity
```

**`read_encoder_data()`** - I2C Read Function
```python
def read_encoder_data(i2c_bus, address):
    """
    Read 25-byte packet from ESP32 and return parsed sensor data.
    Returns dict with encoder positions/velocities, buttons, pots.
    """
    try:
        data = i2c_bus.read_i2c_block_data(address, 0, DATA_PACKET_SIZE)

        # Unpack 25 bytes: '<iiiiiIBHH'
        # i = int32 (4 bytes each, 5 values)
        # I = uint32 (4 bytes, 1 value)
        # B = uint8 (1 byte)
        # H = uint16 (2 bytes each, 2 values)
        unpacked = struct.unpack('<iiiiiIBHH', bytes(data))

        enc1_pos = unpacked[0]
        enc1_vel_raw = unpacked[1] / 100.0  # Convert from fixed-point
        enc2_pos = unpacked[2]
        enc2_vel_raw = unpacked[3] / 100.0
        timestamp = unpacked[4]
        button_flags = unpacked[5]
        volume_pot = unpacked[6]
        slider_pot = unpacked[7]

        # Apply velocity smoothing
        enc1_vel_smoothed = smoother1.update(enc1_pos, timestamp)
        enc2_vel_smoothed = smoother2.update(enc2_pos, timestamp)

        # Decode buttons
        buttons = {
            'SFX_1': bool(button_flags & (1 << 0)),
            'SFX_2': bool(button_flags & (1 << 1)),
            'SFX_3': bool(button_flags & (1 << 2)),
            'SFX_4': bool(button_flags & (1 << 3)),
            'SONG_1': bool(button_flags & (1 << 4)),
            'SONG_2': bool(button_flags & (1 << 5))
        }

        # Normalize potentiometers (0-4095 → 0.0-1.0)
        volume_normalized = volume_pot / 4095.0
        slider_normalized = slider_pot / 4095.0

        return {
            'enc1_position': enc1_pos,
            'enc1_velocity': enc1_vel_smoothed,
            'enc2_position': enc2_pos,
            'enc2_velocity': enc2_vel_smoothed,
            'timestamp': timestamp,
            'buttons': buttons,
            'volume_pot_normalized': volume_normalized,
            'slider_pot_normalized': slider_normalized
        }

    except OSError as e:
        print(f"I2C read error: {e}")
        return None
```

**Code Reference**: `/rpi/i2c.py` (inferred from mixer functionality)

#### 3. **mixer.py** - GStreamer DJ Mixer

**Purpose**: Main audio playback engine with real-time speed modulation.

**Architecture**:

```python
class DJDeck:
    """
    Single audio deck with encoder control.
    Manages one GStreamer pipeline branch.
    """
    def __init__(self, file_path, control_mode):
        # Create GStreamer elements
        self.filesrc = Gst.ElementFactory.make("filesrc", f"src")
        self.decodebin = Gst.ElementFactory.make("decodebin", f"decode")
        self.audioconvert = Gst.ElementFactory.make("audioconvert", f"convert")
        self.pitch = Gst.ElementFactory.make("pitch", f"pitch")

        # Set file path
        self.filesrc.set_property("location", file_path)

        # Initial playback rate
        self.current_rate = 1.0
        self.pitch.set_property("rate", self.current_rate)

    def update_from_encoder(self, sensor_data):
        """
        Update playback rate based on encoder data and control mode.
        """
        velocity = sensor_data['enc1_velocity']
        position = sensor_data['enc1_position']

        if self.control_mode == CONTROL_MODE_VELOCITY:
            # Velocity mode: rate follows rotation speed
            new_rate = 1.0 + (velocity / VELOCITY_SCALE)

        elif self.control_mode == CONTROL_MODE_POSITION:
            # Position mode: rate follows position offset
            offset = position - POSITION_CENTER
            new_rate = 1.0 + (offset / POSITION_RANGE)

        elif self.control_mode == CONTROL_MODE_TURNTABLE:
            # Turntable mode: encoder velocity IS playback speed
            if abs(velocity) < STOP_THRESHOLD_COUNTS_PER_SEC:
                new_rate = 0.0  # Stopped
            else:
                new_rate = velocity / NORMAL_SPEED_COUNTS_PER_SEC

        # Clamp to limits
        new_rate = max(MIN_PLAYBACK_RATE, min(MAX_PLAYBACK_RATE, new_rate))

        # Apply exponential smoothing
        self.current_rate = (SMOOTHING_ALPHA * new_rate +
                            (1 - SMOOTHING_ALPHA) * self.current_rate)

        # Update GStreamer element
        self.pitch.set_property("rate", self.current_rate)

        if DEBUG_PRINT_RATE:
            print(f"Deck rate: {self.current_rate:.3f}x")


class DJMixer:
    """
    Complete DJ mixer with dual decks and I2C integration.
    """
    def __init__(self, file_path1, file_path2=None, dual_deck=False):
        # Initialize GStreamer
        Gst.init(None)

        # Create pipeline
        self.pipeline = Gst.Pipeline.new("dj-mixer")

        # Create decks
        self.deck1 = DJDeck(file_path1, DECK1_CONTROL_MODE)
        self.deck2 = DJDeck(file_path2, DECK2_CONTROL_MODE) if dual_deck else None

        # Create mixer and output
        self.audiomixer = Gst.ElementFactory.make("audiomixer", "mixer")
        self.audioconvert_out = Gst.ElementFactory.make("audioconvert", "convert_out")
        self.pulsesink = Gst.ElementFactory.make("pulsesink", "output")

        # Add elements to pipeline
        self.pipeline.add(self.deck1.filesrc)
        self.pipeline.add(self.deck1.decodebin)
        self.pipeline.add(self.deck1.audioconvert)
        self.pipeline.add(self.deck1.pitch)
        self.pipeline.add(self.audiomixer)
        self.pipeline.add(self.audioconvert_out)
        self.pipeline.add(self.pulsesink)

        # Link elements
        self.deck1.filesrc.link(self.deck1.decodebin)
        # decodebin uses dynamic pads, handle in pad-added callback
        self.deck1.decodebin.connect("pad-added", self.on_pad_added, self.deck1)

        self.audiomixer.link(self.audioconvert_out)
        self.audioconvert_out.link(self.pulsesink)

        # Initialize I2C
        self.i2c_bus = smbus2.SMBus(I2C_BUS)

        # Start I2C polling thread
        self.running = True
        self.i2c_thread = threading.Thread(target=self.i2c_loop)
        self.i2c_thread.start()

        # Start playback
        self.pipeline.set_state(Gst.State.PLAYING)

    def i2c_loop(self):
        """
        Poll I2C at 50Hz and update deck rates.
        """
        while self.running:
            sensor_data = read_encoder_data(self.i2c_bus, ESP32_DECK1_ADDR)

            if sensor_data:
                self.deck1.update_from_encoder(sensor_data)
                if self.deck2:
                    self.deck2.update_from_encoder(sensor_data)

            time.sleep(I2C_POLL_RATE_MS / 1000.0)

    def run(self):
        """
        Run main loop (blocks until Ctrl+C).
        """
        try:
            GLib.MainLoop().run()
        except KeyboardInterrupt:
            print("Stopping mixer...")
            self.running = False
            self.pipeline.set_state(Gst.State.NULL)
```

**GStreamer Pipeline Diagram**:

```
Deck 1:
filesrc → decodebin → audioconvert → pitch (rate control) → audiomixer
                                                                 ↓
Deck 2:                                                    audioconvert
filesrc → decodebin → audioconvert → pitch (rate control) →     ↓
                                                              pulsesink
                                                                 ↓
                                                          PulseAudio/Bluetooth
```

**Code Reference**: `/rpi/mixer.py` (inferred from architecture)

#### 4. **server.py** - Flask/Socket.IO Music Server

**Purpose**: Web server for Spotify search, playlist management, and music downloads.

**Key Features**:
- Spotify OAuth token management
- Real-time playlist updates via Socket.IO
- Background music download with yt-dlp
- Multi-client support

**API Endpoints**:

| Event | Direction | Purpose |
|-------|-----------|---------|
| `SEARCH` | Client → Server | Search Spotify for tracks |
| `search_results` | Server → Client | Return search results |
| `ADD_SONG` | Client → Server | Add song to deck playlist |
| `REMOVE_SONG` | Client → Server | Remove song from deck |
| `REORDER_PLAYLIST` | Client → Server | Drag-and-drop reorder |
| `playlist_update` | Server → All Clients | Broadcast playlist changes |
| `download_progress` | Server → All Clients | Download status updates |

**Download Flow**:

```python
@socketio.on('ADD_SONG')
def handle_add_song(data):
    """
    Add song to playlist and start download in background.
    """
    song_uri = data['uri']
    deck_id = data['deck_id']  # 1 or 2

    # Create song object
    song = {
        'id': hashlib.md5(song_uri.encode()).hexdigest()[:16],
        'name': data['name'],
        'artist': data['artist'],
        'uri': song_uri,
        'download_path': None,
        'download_status': 'pending'
    }

    # Add to playlist
    playlists[deck_id].append(song)

    # Broadcast update
    socketio.emit('playlist_update', {
        'deck1': playlists[1],
        'deck2': playlists[2]
    }, broadcast=True)

    # Start background download
    threading.Thread(target=download_song, args=(song,)).start()


def download_song(song):
    """
    Download song from YouTube using yt-dlp.
    """
    try:
        # Update status
        song['download_status'] = 'downloading'
        socketio.emit('playlist_update', get_playlists(), broadcast=True)

        # yt-dlp command
        output_path = f"/home/jenny/box-dj/rpi/dj_downloads/{song['id']}.mp3"

        command = [
            'yt-dlp',
            '-x',  # Extract audio
            '--audio-format', 'mp3',
            '--audio-quality', '0',  # Best quality
            '-o', output_path,
            f"ytsearch:{song['artist']} {song['name']}"  # Search YouTube
        ]

        subprocess.run(command, check=True)

        # Update song with path
        song['download_path'] = output_path
        song['download_status'] = 'complete'

        # Broadcast success
        socketio.emit('playlist_update', get_playlists(), broadcast=True)

    except Exception as e:
        print(f"Download failed: {e}")
        song['download_status'] = 'failed'
        socketio.emit('playlist_update', get_playlists(), broadcast=True)
```

**Code Reference**: `/rpi/server.py` (inferred)

### Raspberry Pi Setup Instructions

#### 1. Install System Dependencies

```bash
# Update package list
sudo apt-get update

# Install I2C tools
sudo apt-get install -y python3-smbus i2c-tools

# Install GStreamer and all plugins
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-pulseaudio \
    python3-gst-1.0

# Install PulseAudio for Bluetooth
sudo apt-get install -y pulseaudio pulseaudio-utils pulseaudio-module-bluetooth

# Install yt-dlp for music downloads
sudo apt-get install -y yt-dlp

# Or install latest via pip
pip3 install yt-dlp
```

#### 2. Enable I2C Interface

```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
sudo reboot
```

Verify I2C is enabled:
```bash
ls /dev/i2c-*
# Should show: /dev/i2c-1
```

#### 3. Install Python Dependencies

```bash
cd /home/jenny/box-dj/rpi

# Install from requirements.txt
pip3 install -r requirements.txt

# Or install manually:
pip3 install smbus2 flask flask-socketio spotipy eventlet
```

#### 4. Configure Bluetooth for Audio Output

```bash
# Start Bluetooth service
sudo systemctl start bluetooth
sudo systemctl enable bluetooth

# Launch Bluetooth control
bluetoothctl

# In bluetoothctl:
agent on
default-agent
scan on
# Wait for your headphones to appear
# Note the MAC address (e.g., AA:BB:CC:DD:EE:FF)
scan off
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
exit
```

Set Bluetooth as default audio output:
```bash
# List audio sinks
pactl list short sinks

# Set Bluetooth sink as default (replace with your sink name)
pactl set-default-sink bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink
```

#### 5. Test I2C Communication

```bash
cd /home/jenny/box-dj/rpi

# Scan for ESP32
i2cdetect -y 1
# Should show device at 0x42

# Run I2C test script
python3 test.py
```

Expected output:
```
I2C Test: Reading from ESP32 at 0x42
Read 1/10: enc1_pos=0, enc1_vel=0.0, buttons={'SFX_1': False, ...}
Read 2/10: enc1_pos=5, enc1_vel=12.3, ...
...
Test complete!
```

#### 6. Run DJ Mixer

```bash
# Single deck mode (both encoders control same track)
python3 mixer.py

# Dual deck mode (independent control)
# Edit mixer.py: mixer = DJMixer(file1, file2, dual_deck=True)
python3 mixer.py
```

#### 7. Run Music Server

In a separate terminal:

```bash
cd /home/jenny/box-dj/rpi

# Start Flask server
python3 server.py
```

Server will start on `http://0.0.0.0:8080`

Access from browser:
```
http://<raspberry-pi-ip>:8080
```

#### 8. Run Spotify Token Server (Optional)

If using Spotify integration:

```bash
cd /home/jenny/box-dj/music-handling-web/music-handling-website-backend

# Start token server
python3 spotify_token_server.py
```

Server will start on `http://0.0.0.0:6060`

---

## Web Interface Component

### Project Structure

```
music-handling-web/
├── music-handling-website-backend/
│   └── spotify_token_server.py      # OAuth token generation (Port 6060)
│
└── music-handling-website-frontend/
    ├── index.html                   # Main UI (dual deck playlists)
    ├── script.js                    # Socket.IO client, Spotify search
    ├── style.css                    # Styling
    ├── playlist.jpg                 # Album art placeholder
    └── speaker.svg                  # Audio icon
```

### Key Components

#### 1. **index.html** - User Interface

**Features**:
- Search bar for Spotify tracks
- Dual playlist view (Deck 1 / Deck 2)
- Drag-and-drop playlist reordering
- Download status indicators
- Now playing display

**Layout**:
```
┌─────────────────────────────────────────────────────┐
│  Box-DJ Music Controller                            │
├─────────────────────────────────────────────────────┤
│  [Search: _____________________________] [Search]   │
├─────────────────────────────────────────────────────┤
│  Search Results:                                    │
│  1. Chappell Roan - Red Wine Supernova              │
│     [Add to Deck 1] [Add to Deck 2]                 │
│  2. Charli XCX - 365                                │
│     [Add to Deck 1] [Add to Deck 2]                 │
├─────────────────────────────────────────────────────┤
│  Deck 1 Playlist        │  Deck 2 Playlist          │
│  ────────────────────   │  ────────────────────     │
│  Song 1 (downloading)   │  Song 3 ✓                 │
│  Song 2 ✓               │  Song 4 ✓                 │
│                         │                           │
└─────────────────────────────────────────────────────┘
```

#### 2. **script.js** - Client-Side Logic

**Key Functions**:

```javascript
// Connect to Flask Socket.IO server
const socket = io('http://<raspberry-pi-ip>:8080');

// Search Spotify
function searchSpotify() {
    const query = document.getElementById('search-input').value;
    socket.emit('SEARCH', { query: query });
}

// Receive search results
socket.on('search_results', (results) => {
    displaySearchResults(results.tracks);
});

// Add song to deck
function addSong(songData, deckId) {
    socket.emit('ADD_SONG', {
        uri: songData.uri,
        name: songData.name,
        artist: songData.artist,
        deck_id: deckId
    });
}

// Receive playlist updates
socket.on('playlist_update', (data) => {
    updateDeckUI(1, data.deck1);
    updateDeckUI(2, data.deck2);
});

// Remove song
function removeSong(songId, deckId) {
    socket.emit('REMOVE_SONG', {
        song_id: songId,
        deck_id: deckId
    });
}

// Drag-and-drop reordering
function enableDragDrop() {
    const playlists = document.querySelectorAll('.playlist');

    playlists.forEach(playlist => {
        new Sortable(playlist, {
            animation: 150,
            onEnd: (evt) => {
                const deckId = evt.to.dataset.deckId;
                const newOrder = [...evt.to.children].map(el => el.dataset.songId);

                socket.emit('REORDER_PLAYLIST', {
                    deck_id: deckId,
                    new_order: newOrder
                });
            }
        });
    });
}
```

#### 3. **spotify_token_server.py** - OAuth Handler

**Purpose**: Generate and refresh Spotify API tokens.

**Endpoints**:
- `GET /spotify_token` - Returns valid access token
- Handles token refresh automatically

**Configuration**:
```python
SPOTIFY_CLIENT_ID = "your_client_id"
SPOTIFY_CLIENT_SECRET = "your_client_secret"
SPOTIFY_REDIRECT_URI = "http://localhost:6060/callback"
```

### Web Interface Setup

#### 1. Configure Spotify API

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note the Client ID and Client Secret
4. Add redirect URI: `http://localhost:6060/callback`

#### 2. Update Token Server

Edit `/music-handling-web/music-handling-website-backend/spotify_token_server.py`:

```python
SPOTIFY_CLIENT_ID = "your_client_id_here"
SPOTIFY_CLIENT_SECRET = "your_client_secret_here"
```

#### 3. Start Servers

```bash
# Terminal 1: Start token server
cd /home/jenny/box-dj/music-handling-web/music-handling-website-backend
python3 spotify_token_server.py

# Terminal 2: Start main server
cd /home/jenny/box-dj/rpi
python3 server.py
```

#### 4. Access Web Interface

Open browser and navigate to:
```
http://<raspberry-pi-ip>:8080
```

Or on the Raspberry Pi itself:
```
http://localhost:8080
```

---

## Configuration

### Control Modes Explained

The system supports three control modes for deck speed modulation:

#### 1. **Velocity Mode** (Scratching)

**Behavior**: Playback speed directly follows encoder rotation speed.

**Formula**:
```
rate = 1.0 + (velocity / VELOCITY_SCALE)
```

**Use Case**:
- DJ scratching
- Dynamic speed changes
- Stops when encoder stops turning

**Configuration**:
```python
# In config.py
DECK1_CONTROL_MODE = CONTROL_MODE_VELOCITY
VELOCITY_SCALE = 100.0  # Adjust sensitivity
```

**Example**:
- Encoder velocity = +50 counts/sec → rate = 1.5x (50% faster)
- Encoder velocity = -50 counts/sec → rate = 0.5x (50% slower)
- Encoder stopped → rate = 1.0x (normal speed)

#### 2. **Position Mode** (Pitch Slider)

**Behavior**: Playback speed based on encoder position relative to center.

**Formula**:
```
rate = 1.0 + ((position - center) / POSITION_RANGE)
```

**Use Case**:
- Turntable-style pitch control
- Maintains speed until encoder is moved
- Like a physical pitch fader

**Configuration**:
```python
# In config.py
DECK1_CONTROL_MODE = CONTROL_MODE_POSITION
POSITION_CENTER = 1000      # Neutral position
POSITION_RANGE = 500        # ±500 = ±50% speed
```

**Example**:
- Encoder at position 1000 → rate = 1.0x (normal)
- Encoder at position 1500 → rate = 1.5x (50% faster)
- Encoder at position 500 → rate = 0.5x (50% slower)

#### 3. **Turntable Mode** (Vinyl Simulation)

**Behavior**: Encoder velocity directly represents playback speed.

**Formula**:
```
if velocity ≈ NORMAL_SPEED_COUNTS_PER_SEC:
    rate = 1.0
else:
    rate = velocity / NORMAL_SPEED_COUNTS_PER_SEC
```

**Use Case**:
- Vinyl turntable emulation
- Direct 1:1 mapping of rotation to playback
- Can fully stop playback

**Configuration**:
```python
# In config.py
DECK1_CONTROL_MODE = CONTROL_MODE_TURNTABLE
NORMAL_SPEED_COUNTS_PER_SEC = 0.5  # Define what velocity = 1.0x
STOP_THRESHOLD_COUNTS_PER_SEC = 0.5  # Below this = stopped
ALLOW_REVERSE_PLAYBACK = True  # Enable negative velocity
```

**Example**:
- Encoder velocity = 4 counts/sec (normal) → rate = 1.0x
- Encoder velocity = 8 counts/sec → rate = 2.0x
- Encoder velocity = 2 counts/sec → rate = 0.5x
- Encoder velocity = 0 counts/sec → rate = 0.0x (stopped)

### Sensitivity Tuning

Adjust these values in `config.py`:

```python
# Velocity mode sensitivity
VELOCITY_SCALE = 100.0
# Lower = more sensitive (small turn = big change)
# Higher = less sensitive (requires faster turning)
# Recommended: 50-200

# Smoothing window
VELOCITY_WINDOW_SIZE = 10
# Lower = more responsive (3-5)
# Higher = smoother (10-20)

# Playback speed limits
MIN_PLAYBACK_RATE = 0.0   # Allow full stop
MAX_PLAYBACK_RATE = 3.0   # Triple speed max

# Rate change smoothing
SMOOTHING_ALPHA = 0.9
# 0.0 = no smoothing (instant changes)
# 1.0 = maximum smoothing (very gradual)
# Recommended: 0.8-0.95
```

### Encoder Configuration

For low-resolution encoders (PPR < 100):

```python
# Enable predictive velocity tracking
VELOCITY_PREDICTION = True

# Encoder specifications
ENCODER_PPR = 24  # Pulses per revolution

# Timeout for detecting stop
VELOCITY_TIMEOUT_MS = 500  # No change for 500ms = stopped
```

---

## Usage Guide

### Starting the System

#### 1. Power Up Hardware
- Connect ESP32 to USB or external power
- Connect Raspberry Pi
- Connect Bluetooth headphones

#### 2. Start ESP32 (if not auto-running)
```bash
# Flash ESP32 (one-time)
cd /path/to/box-dj/esp32-project
idf.py -p /dev/ttyUSB0 flash

# ESP32 will auto-start on power-up
```

#### 3. Start Raspberry Pi Services

**Terminal 1**: Start DJ Mixer
```bash
cd /home/jenny/box-dj/rpi
python3 mixer.py
```

**Terminal 2**: Start Music Server
```bash
cd /home/jenny/box-dj/rpi
python3 server.py
```

**Terminal 3** (optional): Start Token Server
```bash
cd /home/jenny/box-dj/music-handling-web/music-handling-website-backend
python3 spotify_token_server.py
```

#### 4. Access Web Interface

Open browser:
```
http://<raspberry-pi-ip>:8080
```

### Basic DJ Operations

#### Adding Music to Playlist

1. Type song name in search box
2. Click "Search"
3. Click "Add to Deck 1" or "Add to Deck 2"
4. Wait for download to complete (status indicator shows progress)
5. Song automatically becomes available for playback

#### Controlling Playback Speed

**Encoder 1** (Deck 1):
- Turn clockwise: Speed up
- Turn counter-clockwise: Slow down
- Stop turning: Return to normal speed (velocity mode) or maintain speed (position mode)

**Encoder 2** (Deck 2):
- Same behavior for second deck (if dual-deck mode enabled)

#### Using Buttons

- **SFX_1/2/3/4**: Trigger sound effects (configurable in code)
- **SONG_1/2**: Skip to next/previous song

#### Volume Control

- **Volume Potentiometer**: Adjust master volume (0-100%)
- **Slider Potentiometer**: Apply filter/effect (configurable)

### Advanced Features

#### Mixing Two Tracks

1. Enable dual-deck mode in `config.py`:
```python
DUAL_DECK_MODE = True
```

2. Add songs to both Deck 1 and Deck 2 playlists

3. Both tracks play simultaneously through `audiomixer`

4. Control each deck independently with Encoder 1 and Encoder 2

#### Scratching Technique

1. Set control mode to VELOCITY:
```python
DECK1_CONTROL_MODE = CONTROL_MODE_VELOCITY
```

2. Quickly rotate encoder back and forth

3. Audio will modulate in real-time following your hand movements

#### Beatmatching

1. Play two tracks simultaneously
2. Use position mode to maintain offset speeds
3. Adjust one deck's speed until beats align
4. Fine-tune with encoder position

---

## Troubleshooting

### ESP32 Issues

#### ESP32 Not Detected by RPi

**Symptom**: `i2cdetect -y 1` shows no device at 0x42

**Solutions**:
```bash
# Check wiring
# SDA (GPIO33) → RPi Pin 3
# SCL (GPIO32) → RPi Pin 5
# GND → GND

# Check pull-up resistors (2.2kΩ - 4.7kΩ on SDA/SCL)

# Check ESP32 is running
idf.py -p /dev/ttyUSB0 monitor
# Should see log messages

# Check I2C address in comm.h matches config.py
# ESP32: #define I2C_SLAVE_ADDR 0x42
# RPi: ESP32_DECK1_ADDR = 0x42
```

#### I2C Read Errors

**Symptom**: `OSError: [Errno 121] Remote I/O error`

**Solutions**:
- ESP32 not powered or not running I2C slave code
- Wrong I2C address
- Loose wiring
- Missing pull-up resistors

#### Encoder Not Responding

**Symptom**: Encoder position always reads 0

**Solutions**:
```c
// Check GPIO pins in sensors.c
encoder_init(ENCODER_1, GPIO_NUM_26, GPIO_NUM_27);  // Must match wiring

// Check PCNT is enabled in sdkconfig
// Component config → Driver configurations → PCNT Configuration

// Test encoder with serial monitor
idf.py -p /dev/ttyUSB0 monitor
// Rotate encoder and check for log messages
```

### Raspberry Pi Issues

#### No Audio Output

**Symptom**: Mixer runs but no sound

**Solutions**:
```bash
# Check PulseAudio is running
pulseaudio --check
pulseaudio --start

# Test audio system
speaker-test -t sine -f 440 -c 2

# Check GStreamer plugins installed
gst-inspect-1.0 pitch
gst-inspect-1.0 pulsesink

# List audio sinks
pactl list short sinks

# Set correct sink as default
pactl set-default-sink <sink_name>

# For Bluetooth: ensure headphones are connected
bluetoothctl
# In bluetoothctl: info AA:BB:CC:DD:EE:FF
```

#### Audio Crackling/Glitching

**Symptom**: Audio plays but has crackling or dropouts

**Solutions**:
```python
# In config.py, reduce polling rate to lower CPU usage
I2C_POLL_RATE_MS = 50  # 20Hz instead of 50Hz

# Increase audio buffer size (edit mixer.py)
self.pulsesink.set_property("latency-time", 20000)  # 20ms buffer

# Use scaletempo instead of pitch for lower latency
self.rate_element = Gst.ElementFactory.make("scaletempo", "rate")
```

#### Velocity Too Jittery

**Symptom**: Playback speed jumps erratically

**Solutions**:
```python
# In config.py, increase smoothing window
VELOCITY_WINDOW_SIZE = 15  # More averaging

# Enable predictive velocity tracking
VELOCITY_PREDICTION = True

# Increase smoothing alpha
SMOOTHING_ALPHA = 0.95  # More gradual transitions
```

#### I2C Permission Denied

**Symptom**: `PermissionError: [Errno 13] Permission denied: '/dev/i2c-1'`

**Solution**:
```bash
# Add user to i2c group
sudo usermod -a -G i2c $USER

# Log out and back in for changes to take effect
```

### Web Interface Issues

#### Cannot Connect to Web Server

**Symptom**: Browser shows "Connection refused"

**Solutions**:
```bash
# Check server is running
ps aux | grep server.py

# Check port 8080 is not in use
sudo netstat -tulpn | grep 8080

# Check firewall (if enabled)
sudo ufw allow 8080

# Try accessing from RPi itself first
curl http://localhost:8080
```

#### Spotify Search Not Working

**Symptom**: Search returns no results or error

**Solutions**:
```python
# Check Spotify token server is running
curl http://localhost:6060/spotify_token

# Verify credentials in spotify_token_server.py
SPOTIFY_CLIENT_ID = "..."  # Must be valid
SPOTIFY_CLIENT_SECRET = "..."

# Check token expiration - server should auto-refresh
```

#### Downloads Failing

**Symptom**: Songs show "download failed" status

**Solutions**:
```bash
# Check yt-dlp is installed
yt-dlp --version

# Test yt-dlp manually
yt-dlp -x --audio-format mp3 "ytsearch:Chappell Roan Red Wine"

# Check output directory exists and is writable
mkdir -p /home/jenny/box-dj/rpi/dj_downloads
chmod 755 /home/jenny/box-dj/rpi/dj_downloads

# Check disk space
df -h
```

### Performance Issues

#### High CPU Usage

**Symptom**: RPi becomes sluggish

**Solutions**:
```python
# Reduce I2C polling rate
I2C_POLL_RATE_MS = 50  # From 20ms to 50ms (20Hz)

# Disable debug printing
DEBUG_PRINT_I2C = False
DEBUG_PRINT_RATE = False

# Use single-deck mode if dual-deck not needed
DUAL_DECK_MODE = False
```

#### Audio Latency

**Symptom**: Encoder movement and audio change feel delayed

**Solutions**:
```python
# Reduce smoothing (trades smoothness for responsiveness)
VELOCITY_WINDOW_SIZE = 3
SMOOTHING_ALPHA = 0.7

# Increase I2C polling rate (trades CPU for responsiveness)
I2C_POLL_RATE_MS = 10  # 100Hz

# Use pitch element (lower latency than other rate changers)
# Already default in mixer.py
```

---

## Development Notes

### Architecture Decisions

#### Why I2C Instead of UART?

**Advantages**:
- Only 2 wires needed (SDA, SCL, GND)
- Multi-master capable (future expansion)
- Well-supported on both ESP32 and RPi
- Hardware pull-ups available

**Disadvantages**:
- Slower than UART (100kHz-400kHz vs 115200 baud+)
- Requires pull-up resistors
- More complex protocol

**Decision**: I2C chosen for simplicity and expandability.

#### Why Calculate Velocity on RPi?

**Problem**: ESP32-side velocity calculation with 24 PPR encoder showed ±5 counts/sec jitter.

**Solution**: Send raw position + timestamp to RPi, calculate velocity using sliding window:
- Smoother velocity (10-sample average eliminates noise)
- More responsive (RPi has more CPU for filtering algorithms)
- Easier to tune without reflashing ESP32

#### Why GStreamer Instead of PyAudio?

**GStreamer Advantages**:
- `pitch` element does time-stretching without pitch shift
- Hardware-accelerated decoding
- Built-in format support (MP3, OGG, FLAC, etc.)
- Low latency (~50ms)
- Professional-grade audio pipeline

**PyAudio Disadvantages**:
- Would require manual time-stretching implementation
- Higher CPU usage for real-time processing
- No built-in pitch preservation

#### Why 25-Byte I2C Packets?

**Packet Design**:
- Fixed size for predictable reads
- Little-endian for direct struct unpacking
- Timestamp for synchronization and timeout detection
- Button flags packed into single byte (efficient)
- Potentiometer values at 12-bit resolution (hardware limit)

### Code Style Guidelines

**ESP32 (C)**:
- Function names: `module_action()` (e.g., `encoder_init()`, `comm_update_encoder_data()`)
- Constants: `UPPERCASE_WITH_UNDERSCORES`
- Module prefix for all public functions
- Extensive comments explaining hardware interactions

**Raspberry Pi (Python)**:
- PEP 8 style guide
- Class names: `CamelCase`
- Functions: `snake_case`
- Config constants: `UPPERCASE_WITH_UNDERSCORES`
- Type hints where helpful

### Future Enhancement Ideas

- [ ] **Crossfader**: Add third potentiometer for dual-deck mixing control
- [ ] **EQ Controls**: Three-band equalizer per deck (bass, mid, treble)
- [ ] **Effects**: Reverb, delay, filter sweep, bit crusher
- [ ] **Loop Mode**: Set loop points and repeat sections
- [ ] **BPM Detection**: Automatic beat matching assistance
- [ ] **Recording**: Save mixed output to MP3/WAV
- [ ] **MIDI Support**: Control via external MIDI controllers
- [ ] **Waveform Display**: Visual feedback of audio in web interface
- [ ] **Hot Cues**: Mark and jump to predefined points in tracks
- [ ] **Auto-Sync**: Automatic BPM matching between decks

### Contributing

This project is part of the Box Bots hackathon. Feel free to:
- Report bugs via GitHub issues
- Submit pull requests with improvements
- Fork and customize for your own DJ setup

### License

Open source - free to use and modify for your projects!

---

## Credits

**Built for Jenny's Box-DJ project**

**Team**: Box Bots Hackathon Team

**Technologies**:
- ESP-IDF (Espressif IoT Development Framework)
- GStreamer 1.0
- PulseAudio
- Flask + Socket.IO
- Spotify Web API
- yt-dlp

**Special Thanks**:
- Espressif for ESP32 platform
- GStreamer community
- Spotipy library maintainers

---

## Quick Reference

### File Locations

| Component | Path |
|-----------|------|
| ESP32 main code | `/esp32-project/main/main.c` |
| I2C communication | `/esp32-project/main/comm.c` |
| RPi mixer | `/rpi/mixer.py` |
| RPi configuration | `/rpi/config.py` |
| Web interface | `/music-handling-web/music-handling-website-frontend/index.html` |
| Music server | `/rpi/server.py` |

### Common Commands

```bash
# ESP32
idf.py build                          # Build firmware
idf.py -p /dev/ttyUSB0 flash         # Flash to ESP32
idf.py -p /dev/ttyUSB0 monitor       # Serial monitor

# Raspberry Pi
i2cdetect -y 1                       # Scan I2C bus
python3 mixer.py                      # Start DJ mixer
python3 server.py                     # Start music server
bluetoothctl                          # Bluetooth control

# System
sudo systemctl status bluetooth       # Check Bluetooth status
pactl list short sinks               # List audio outputs
pulseaudio --check                   # Check PulseAudio status
```

### GPIO Quick Reference

**ESP32**:
| Function | GPIO |
|----------|------|
| I2C SDA | 33 |
| I2C SCL | 32 |
| Encoder 1A | 26 |
| Encoder 1B | 27 |
| Encoder 2A | 14 |
| Encoder 2B | 15 |
| Volume Pot | 34 (ADC) |
| Slider Pot | 35 (ADC) |

**Raspberry Pi**:
| Function | Pin |
|----------|-----|
| I2C SDA | Pin 3 (GPIO2) |
| I2C SCL | Pin 5 (GPIO3) |

---

**Version**: 1.0
**Last Updated**: November 2025
**Status**: Hackathon Project - Functional Prototype
