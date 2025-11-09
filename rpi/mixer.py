#!/usr/bin/env python3
"""
DJ Mixer Application
Combines GStreamer audio processing with I2C encoder control
"""

import gi
import sys
import os
import smbus2

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

from i2c import EncoderReader, EncoderSmoother
from config import (
    HOME_PATH, MUSIC_PATH_1, MUSIC_PATH_2, DUAL_DECK_MODE,
    I2C_BUS, ESP32_DECK1_ADDR, ESP32_DECK2_ADDR,
    I2C_POLL_RATE_MS, DEFAULT_VOLUME, NORMAL_SPEED_MAX, NORMAL_SPEED_MIN,
    VELOCITY_SCALE, MIN_PLAYBACK_RATE, MAX_PLAYBACK_RATE,
    DECK1_CONTROL_MODE, DECK2_CONTROL_MODE,
    CONTROL_MODE_VELOCITY, CONTROL_MODE_POSITION, CONTROL_MODE_TURNTABLE,
    NORMAL_SPEED_COUNTS_PER_SEC, STOP_THRESHOLD_COUNTS_PER_SEC, ALLOW_REVERSE_PLAYBACK,
    VELOCITY_PREDICTION, VELOCITY_CHANGE_THRESHOLD, ENCODER_PPR,
    DEBUG_PRINT_RATE, DEBUG_PRINT_VOLUME
)
import enum
from collections import deque


class TurntableState(enum.Enum):
    """States for the Turntable Speed Controller"""
    CALIBRATING = 0
    NORMAL_SPEED = 1
    MODULATING_SPEED = 2



class DJDeck:
    """Represents a single DJ deck with its encoder and GStreamer elements"""

    def __init__(self, deck_id, encoder_reader, rate_element, volume_pad, control_mode, pipeline):
        self.deck_id = deck_id
        self.encoder = encoder_reader
        self.rate_element = rate_element
        self.volume_pad = volume_pad
        self.control_mode = control_mode
        self.pipeline = pipeline
        
        self.state = TurntableState.NORMAL_SPEED

        self.current_rate = 1.0
        self.current_volume = DEFAULT_VOLUME
        
        self.encoder_read_history = deque(maxlen=100)
        
    def set_control_mode(self, mode):
        """Switch between control modes"""
        if mode in [CONTROL_MODE_VELOCITY, CONTROL_MODE_POSITION, CONTROL_MODE_TURNTABLE]:
            self.control_mode = mode
            print(f"Deck {self.deck_id}: Control mode set to {mode}")

    def update_from_encoder(self):
        """Read encoder and update playback rate/volume"""
        data = self.encoder.read()

        if data is None:
            return

        self.encoder_read_history.append(data)

        # Update playback rate based on control mode
        self._update_state_turntable()
        self._update_rate()

    def _update_state_turntable(self):
        prev_velocities = [entry['enc1_velocity'] for entry in self.encoder_read_history]

        if not self.encoder_read_history:
            return
        avg_recent_velocity = sum(prev_velocities) / len(prev_velocities)
        print("AVG RECENT VEL", avg_recent_velocity)
        if NORMAL_SPEED_MIN < avg_recent_velocity < NORMAL_SPEED_MAX:
            self.state = TurntableState.NORMAL_SPEED
        else:
            self.state = TurntableState.MODULATING_SPEED
        
        print("STATE:", self.state)
        print()
        
    
    def _update_rate(self):
        match self.state:
            case TurntableState.CALIBRATING:
                # Not sure if even to go with this
                print("Still calibrating...")
            case TurntableState.NORMAL_SPEED:
                print("At normal speed, reset rate to 1.0x")
                self.current_rate = 1.0
            case TurntableState.MODULATING_SPEED:
                print("Modulating speed...")
                """Update playback rate based on encoder velocity (scratching)"""
                velocity = self.encoder_read_history[-1]['enc1_velocity']
                rate_change = velocity / VELOCITY_SCALE
                new_rate = 1.0 + rate_change

                # Clamp to allowed range
                new_rate = max(max(MIN_PLAYBACK_RATE, new_rate), min(MAX_PLAYBACK_RATE, new_rate))

                if abs(new_rate - self.current_rate) > 0.01:  # Only update if significant change
                    self.current_rate = new_rate
                    self.rate_element.set_property("rate", max(0.01, self.current_rate))

                    if DEBUG_PRINT_RATE:
                        print(f"State: {self.state}\tDeck {self.deck_id}: Velocity {velocity:6.1f}\tRate: {self.current_rate:.2f}x")

    def set_volume(self, volume):
        """Set deck volume (0.0 to 1.0)"""
        volume = max(0.0, min(1.0, volume))
        self.current_volume = volume

        # Only set volume if we have a mixer pad (dual deck mode)
        if self.volume_pad is not None:
            self.volume_pad.set_property("volume", volume)

            if DEBUG_PRINT_VOLUME:
                print(f"Deck {self.deck_id}: Volume {volume:.2f}")
        elif DEBUG_PRINT_VOLUME:
            print(f"Deck {self.deck_id}: Volume control not available in single deck mode")

    def adjust_volume(self, delta):
        """Adjust volume by delta"""
        self.set_volume(self.current_volume + delta)


class DJMixer:
    """Main DJ mixer application"""

    def __init__(self, file_path1, file_path2=None, use_dual_encoders=False):
        """
        Initialize DJ Mixer

        Args:
            file_path1: Path to audio file for deck 1
            file_path2: Path to audio file for deck 2 (None for single deck mode)
            use_dual_encoders: If True, use two separate ESP32s for each deck
        """
        Gst.init(None)

        self.pipeline = None
        self.loop = None
        self.i2c_bus = None
        self.deck1 = None
        self.deck2 = None
        self.dual_deck_mode = file_path2 is not None
        self.use_dual_encoders = use_dual_encoders

        # Build GStreamer pipeline
        self._build_pipeline(file_path1, file_path2)

        # Initialize I2C and encoders
        self._init_encoders()

    def _build_pipeline(self, file_path1, file_path2):
        """Build the GStreamer audio pipeline"""
        self.pipeline = Gst.Pipeline.new("dj-pipeline")

        # === Deck 1 Elements (Always created) ===
        src1 = Gst.ElementFactory.make("filesrc", "src1")
        src1.set_property("location", file_path1)
        decode1 = Gst.ElementFactory.make("decodebin", "decode1")
        convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
        rate1 = Gst.ElementFactory.make("pitch", "rate1")

        # === Output Elements ===
        output_convert = Gst.ElementFactory.make("audioconvert", "output_convert")
        output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

        # Check essential elements
        if not all([src1, decode1, convert1, rate1, output_convert, output_sink]):
            raise RuntimeError("Failed to create essential GStreamer elements. Check plugins.")

        # Add deck 1 elements to pipeline
        self.pipeline.add(src1)
        self.pipeline.add(decode1)
        self.pipeline.add(convert1)
        self.pipeline.add(rate1)
        self.pipeline.add(output_convert)
        self.pipeline.add(output_sink)

        if self.dual_deck_mode:
            # === Dual Deck Mode ===
            print("Building DUAL DECK pipeline...")

            # Create deck 2 elements
            src2 = Gst.ElementFactory.make("filesrc", "src2")
            src2.set_property("location", file_path2)
            decode2 = Gst.ElementFactory.make("decodebin", "decode2")
            convert2 = Gst.ElementFactory.make("audioconvert", "convert2")
            rate2 = Gst.ElementFactory.make("pitch", "rate2")
            mixer = Gst.ElementFactory.make("audiomixer", "mixer")

            if not all([src2, decode2, convert2, rate2, mixer]):
                raise RuntimeError("Failed to create deck 2 GStreamer elements.")

            # Add deck 2 and mixer to pipeline
            self.pipeline.add(src2)
            self.pipeline.add(decode2)
            self.pipeline.add(convert2)
            self.pipeline.add(rate2)
            self.pipeline.add(mixer)

            # Link Deck 1: src → decode → convert → rate → mixer
            src1.link(decode1)
            decode1.connect("pad-added", self._on_pad_added, convert1)
            convert1.link(rate1)

            src_pad_1 = rate1.get_static_pad("src")
            sink_pad_1 = mixer.get_request_pad("sink_%u")
            src_pad_1.link(sink_pad_1)

            # Link Deck 2: src → decode → convert → rate → mixer
            src2.link(decode2)
            decode2.connect("pad-added", self._on_pad_added, convert2)
            convert2.link(rate2)

            src_pad_2 = rate2.get_static_pad("src")
            sink_pad_2 = mixer.get_request_pad("sink_%u")
            src_pad_2.link(sink_pad_2)

            # Link mixer to output
            mixer.link(output_convert)
            output_convert.link(output_sink)

            # Store elements for control
            self._rate1 = rate1
            self._rate2 = rate2
            self._sink_pad_1 = sink_pad_1
            self._sink_pad_2 = sink_pad_2

        else:
            # === Single Deck Mode ===
            print("Building SINGLE DECK pipeline...")

            # Link Deck 1: src → decode → convert → rate → output
            src1.link(decode1)
            decode1.connect("pad-added", self._on_pad_added, convert1)
            convert1.link(rate1)
            rate1.link(output_convert)
            output_convert.link(output_sink)

            # Store elements for control
            self._rate1 = rate1
            self._rate2 = None
            self._sink_pad_1 = None  # No mixer pad in single mode
            self._sink_pad_2 = None

        print("GStreamer pipeline built successfully")

    def _on_pad_added(self, element, pad, target_element):
        """Callback when decodebin creates a new pad"""
        sink_pad = target_element.get_static_pad("sink")

        if sink_pad.is_linked():
            return

        try:
            pad.link(sink_pad)
            print(f"Linked {element.get_name()} → {target_element.get_name()}")
        except Exception as e:
            print(f"Failed to link {element.get_name()}: {e}")

    def _init_encoders(self):
        """Initialize I2C bus and encoder readers"""
        self.i2c_bus = smbus2.SMBus(I2C_BUS)

        if self.dual_deck_mode:
            # Dual deck mode
            if self.use_dual_encoders:
                # Two separate ESP32s for independent deck control
                encoder1 = EncoderReader(self.i2c_bus, ESP32_DECK1_ADDR, EncoderSmoother())
                encoder2 = EncoderReader(self.i2c_bus, ESP32_DECK2_ADDR, EncoderSmoother())
                print(f"Dual encoder mode: Deck1@0x{ESP32_DECK1_ADDR:02X}, Deck2@0x{ESP32_DECK2_ADDR:02X}")
            else:
                # Single ESP32 controls both decks (same modulation)
                encoder1 = EncoderReader(self.i2c_bus, ESP32_DECK1_ADDR, EncoderSmoother())
                encoder2 = encoder1  # Both decks use same encoder
                print(f"Single encoder mode: Both decks@0x{ESP32_DECK1_ADDR:02X}")

            self.deck1 = DJDeck(1, encoder1, self._rate1, self._sink_pad_1, DECK1_CONTROL_MODE, self.pipeline)
            self.deck2 = DJDeck(2, encoder2, self._rate2, self._sink_pad_2, DECK2_CONTROL_MODE, self.pipeline)
        else:
            encoder1 = EncoderReader(self.i2c_bus, ESP32_DECK1_ADDR, EncoderSmoother())
            print(f"Single deck mode: Encoder@0x{ESP32_DECK1_ADDR:02X}")

            self.deck1 = DJDeck(1, encoder1, self._rate1, None, DECK1_CONTROL_MODE, self.pipeline)
            self.deck2 = None

    def _on_i2c_update(self):
        """Called periodically to read encoders and update playback"""
        try:
            self.deck1.update_from_encoder()
            
            if self.deck2 is not None:
                if self.use_dual_encoders:
                    self.deck2.update_from_encoder()

        except Exception as e:
            raise e
            print(f"Error in I2C update: {e}")

        return True  # Keep timer running

    def run(self):
        """Start the DJ mixer"""
        print("\n" + "="*70)
        print(f"DJ MIXER RUNNING - {'DUAL DECK' if self.dual_deck_mode else 'SINGLE DECK'} MODE")
        print("="*70)
        print(f"Deck 1: {DECK1_CONTROL_MODE} mode")
        if self.dual_deck_mode:
            print(f"Deck 2: {DECK2_CONTROL_MODE} mode")

        if DECK1_CONTROL_MODE == CONTROL_MODE_TURNTABLE or (self.dual_deck_mode and DECK2_CONTROL_MODE == CONTROL_MODE_TURNTABLE):
            print(f"\nTurntable Settings:")
            print(f"  Encoder PPR: {ENCODER_PPR}")
            print(f"  Normal speed: {NORMAL_SPEED_COUNTS_PER_SEC:.1f} counts/s = 1.0x playback")
            print(f"  Stop threshold: {STOP_THRESHOLD_COUNTS_PER_SEC:.1f} counts/s")
            if VELOCITY_PREDICTION:
                print(f"  Predictive velocity: ENABLED (smooth playback between clicks)")
                print(f"  Velocity change threshold: {VELOCITY_CHANGE_THRESHOLD:.1%}")
            print(f"  Reverse playback: {'Enabled' if ALLOW_REVERSE_PLAYBACK else 'Disabled'}")

        print(f"\nI2C Poll Rate: {I2C_POLL_RATE_MS}ms")
        print("\nPress Ctrl+C to stop")
        print("="*70 + "\n")

        # Start pipeline
        self.pipeline.set_state(Gst.State.PLAYING)

        # Create main loop
        self.loop = GLib.MainLoop()

        # Add I2C polling timer
        GLib.timeout_add(I2C_POLL_RATE_MS, self._on_i2c_update)

        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n\nStopping DJ mixer...")
            self.stop()

    def stop(self):
        """Stop the DJ mixer and cleanup"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        if self.i2c_bus:
            self.i2c_bus.close()

        if self.loop:
            self.loop.quit()

        print("DJ mixer stopped")


def main():
    """Main entry point"""
    file_path1 = os.path.join(HOME_PATH, MUSIC_PATH_1)

    if not os.path.exists(file_path1):
        print(f"Error: File not found: {file_path1}")
        sys.exit(1)

    # Handle dual deck mode
    file_path2 = None
    if DUAL_DECK_MODE:
        file_path2 = os.path.join(HOME_PATH, MUSIC_PATH_2)
        if not os.path.exists(file_path2):
            print(f"Error: File not found: {file_path2}")
            print(f"Set DUAL_DECK_MODE = False in config.py for single deck mode")
            sys.exit(1)

    mixer = DJMixer(file_path1, file_path2, use_dual_encoders=False)
    mixer.run()


if __name__ == "__main__":
    main()