# DJ Mixer with Encoder Control

Python-based DJ mixer that plays MP3 files through GStreamer and modulates playback using rotary encoder data from ESP32 via I2C.

## Features

- **Dual Deck Audio**: Mix two audio tracks simultaneously
- **Real-time Speed Control**: Modulate playback speed using encoder velocity or position
- **Volume Control**: Independent volume control for each deck
- **Smooth Velocity Calculation**: RPi-side velocity smoothing eliminates ESP32 jitter
- **Flexible Control Modes**:
  - Velocity mode: Direct scratching/dynamic control
  - Position mode: Turntable-style pitch control

## Hardware Requirements

- Raspberry Pi 5 (or RPi 4 with I2C enabled)
- ESP32 with rotary encoder connected
- I2C connection between RPi and ESP32
- Audio output (PulseAudio/ALSA compatible)

### Wiring

```
ESP32          RPi5
GPIO33 (SDA) → Pin 3 (SDA/GPIO2)
GPIO32 (SCL) → Pin 5 (SCL/GPIO3)
GND          → GND
```

**Important**: Add pull-up resistors (1.8kΩ - 4.7kΩ) on SDA and SCL lines for stable communication.

## Software Dependencies

### System Packages

```bash
# Install I2C tools
sudo apt-get update
sudo apt-get install -y python3-smbus i2c-tools

# Install GStreamer and plugins
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-pulseaudio \
    python3-gst-1.0

# Install audio system
sudo apt-get install -y pulseaudio pulseaudio-utils
```

### Python Packages

```bash
pip3 install smbus2
```

### Enable I2C

```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
# Reboot after enabling
sudo reboot
```

## Installation

1. **Clone or download files to your Raspberry Pi**

```bash
cd /home/jenny/box-dj/
# Place all .py files here:
# - config.py
# - encoder_reader.py
# - dj_mixer.py
# - test_i2c.py
```

2. **Edit config.py with your settings**

```python
# Update paths to your MP3 files
HOME_PATH = "/home/jenny/box-dj/"
MUSIC_PATH_1 = "rpi/example-mp3/your-song-1.mp3"
MUSIC_PATH_2 = "rpi/example-mp3/your-song-2.mp3"

# Update ESP32 I2C address if different
ESP32_DECK1_ADDR = 0x42
```

3. **Make scripts executable**

```bash
chmod +x dj_mixer.py
chmod +x test_i2c.py
chmod +x encoder_reader.py
```

## Testing

### 1. Verify I2C Connection

```bash
# Scan for I2C devices
i2cdetect -y 1

# You should see your ESP32 address (0x42)
```

### 2. Run Connection Test

```bash
python3 test_i2c.py
```

This will:
- Test I2C bus connectivity
- Attempt 10 reads from ESP32
- Show encoder data (if connection is good)

### 3. Test Encoder Reading

```bash
python3 encoder_reader.py
```

Rotate your encoder and verify:
- Position values change
- Smoothed velocity tracks your rotation
- No excessive read errors

## Running the DJ Mixer

### Basic Usage

#### Connecting to Bluetooth Headphones:
```
bluetoothctl
# Then
agent on
default-agent
scan on # (Wait until you see your speaker's name/MAC address)
scan off
pair YOUR_SPEAKER_MAC_ADDRESS`
trust YOUR_SPEAKER_MAC_ADDRESS
connect YOUR_SPEAKER_MAC_ADDRESS
```

```bash
python3 dj_mixer.py
```

### What to Expect

1. Pipeline starts playing both MP3 files mixed together
2. Encoder rotation modulates playback speed
3. Console shows real-time rate/velocity updates
4. Press Ctrl+C to stop

### Control Modes

**Velocity Mode** (default for both decks):
- Playback speed responds to how fast you turn the encoder
- Great for scratching and dynamic speed changes
- Stops when encoder stops

**Position Mode**:
- Playback speed based on encoder position relative to center
- Like a turntable pitch slider
- Maintains speed until you change position

Edit in `config.py`:
```python
DECK1_CONTROL_MODE = CONTROL_MODE_VELOCITY  # or CONTROL_MODE_POSITION
DECK2_CONTROL_MODE = CONTROL_MODE_VELOCITY  # or CONTROL_MODE_POSITION
```

## Configuration Options

### Speed Control Sensitivity

```python
# In config.py

# Higher = less sensitive (slower speed changes)
VELOCITY_SCALE = 100.0  # Default: 100

# Speed limits
MIN_PLAYBACK_RATE = 0.5   # Minimum 0.5x speed
MAX_PLAYBACK_RATE = 2.0   # Maximum 2.0x speed
```

### Smoothing

```python
# Number of samples for velocity averaging
VELOCITY_WINDOW_SIZE = 5  # Increase for smoother, decrease for more responsive
```

### Position Mode Settings

```python
POSITION_CENTER = 1000      # Neutral position
POSITION_RANGE = 500        # ±500 counts = ±50% speed change
```

### I2C Polling Rate

```python
I2C_POLL_RATE_MS = 20  # 50Hz (20ms interval)
# Lower = more responsive, Higher = less CPU usage
```

## Dual Encoder Setup

For independent control of two decks with two ESP32s:

1. **Set second ESP32 to different I2C address** (e.g., 0x43)

2. **Update config.py**:
```python
ESP32_DECK2_ADDR = 0x43
```

3. **Enable dual encoder mode in dj_mixer.py**:
```python
mixer = DJMixer(file_path1, file_path2, use_dual_encoders=True)
```

## Troubleshooting

### No Audio Output

```bash
# Check PulseAudio is running
pulseaudio --check
pulseaudio --start

# Test audio system
speaker-test -t sine -f 440 -c 2

# Check GStreamer sinks
gst-inspect-1.0 pulsesink
```

### I2C Read Errors

**"Remote I/O error"**:
- ESP32 not powered or not running I2C slave code
- Wrong I2C address
- Bad wiring

**Intermittent reads**:
- Add/check pull-up resistors (1.8kΩ - 4.7kΩ)
- Reduce wire length (<30cm)
- Check power supply stability

**Permission denied**:
```bash
# Add user to i2c group
sudo usermod -a -G i2c $USER
# Log out and back in
```

### GStreamer Errors

**"No element 'pitch'"**:
```bash
# Install bad plugins (contains pitch element)
sudo apt-get install gstreamer1.0-plugins-bad
```

**"Could not link elements"**:
- Check all required GStreamer plugins are installed
- Verify audio file format is supported (MP3, WAV, OGG, etc.)

### Latency Issues

The `pitch` element adds ~50-100ms latency. For ultra-low latency:

1. Use `scaletempo` instead of `pitch` in `dj_mixer.py`:
```python
rate1 = Gst.ElementFactory.make("scaletempo", "rate1")
```

Note: `scaletempo` has different audio characteristics (may sound more distorted at extreme speeds).

## File Structure

```
/home/jenny/box-dj/
├── config.py           # Configuration settings
├── encoder_reader.py   # I2C communication and velocity smoothing
├── dj_mixer.py        # Main DJ mixer application
├── test_i2c.py        # I2C connectivity test
└── rpi/
    └── example-mp3/
        ├── song1.mp3
        └── song2.mp3
```

## Performance Tips

- **CPU Usage**: I2C polling at 50Hz is lightweight (~1-2% CPU)
- **Audio Buffer**: Default settings balance latency vs stability
- **Encoder Resolution**: Higher encoder PPR = better fine control

## Debug Mode

Enable detailed logging in `config.py`:

```python
DEBUG_PRINT_I2C = True      # Print all I2C reads
DEBUG_PRINT_RATE = True     # Print rate changes
DEBUG_PRINT_VOLUME = True   # Print volume changes
```

## Next Steps / Ideas

- [ ] Add crossfader control (second encoder or potentiometer)
- [ ] Implement EQ controls
- [ ] Add effects (reverb, delay, filter)
- [ ] Beat matching detection
- [ ] Loop functionality
- [ ] Record mixed output
- [ ] Web interface for control
- [ ] MIDI controller support

## License

Free to use and modify for your DJ project!

## Credits

Built for Jenny's Box-DJ project