#!/usr/bin/env python3
"""
DJ Mixer Application - Programmatic Control
"""

import gi
import os
import threading
import time

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# ============= CONFIG (Simplified for local use) ============= #
DEFAULT_VOLUME = 1.0
MIN_PLAYBACK_RATE = 0.0
MAX_PLAYBACK_RATE = 3.0
DEBUG_PRINT_RATE = True
DEBUG_PRINT_VOLUME = True

class PlaybackState:
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2

class DJDeck:
    """Represents a single DJ deck with its GStreamer elements"""

    def __init__(self, deck_id, pipeline):
        self.deck_id = deck_id
        self.pipeline = pipeline
        self.state = PlaybackState.STOPPED
        self.current_rate = 1.0
        self.current_volume = DEFAULT_VOLUME
        
        # GStreamer elements for this deck
        self.src = Gst.ElementFactory.make("filesrc", f"src{deck_id}")
        self.decode = Gst.ElementFactory.make("decodebin", f"decode{deck_id}")
        self.convert = Gst.ElementFactory.make("audioconvert", f"convert{deck_id}")
        self.rate = Gst.ElementFactory.make("pitch", f"rate{deck_id}")
        self.volume_pad = None # This will be the mixer sink pad

        # HACK: Set a default file location to allow the pipeline to preroll.
        # This prevents the "No file name specified for reading" error on startup.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dummy_path = os.path.join(script_dir, "example-mp3/charli-xcx-365.mp3")
        if os.path.exists(dummy_path):
            self.src.set_property("location", dummy_path)
        else:
            print(f"!!! WARNING: Dummy MP3 for Deck {self.deck_id} not found at {dummy_path}. Pipeline may fail to start.")

        if not all([self.src, self.decode, self.convert, self.rate]):
            raise RuntimeError(f"Failed to create GStreamer elements for Deck {deck_id}")

        # Add elements to the pipeline
        pipeline.add(self.src)
        pipeline.add(self.decode)
        pipeline.add(self.convert)
        pipeline.add(self.rate)

        # Link static elements
        self.src.link(self.decode)
        self.convert.link(self.rate)
        
        # decodebin's pad is created dynamically, so we connect to "pad-added"
        self.decode.connect("pad-added", self._on_pad_added)

    def _on_pad_added(self, element, pad):
        """Callback when decodebin creates a new pad"""
        sink_pad = self.convert.get_static_pad("sink")
        if sink_pad.is_linked():
            return
        try:
            pad.link(sink_pad)
            print(f"Linked {element.get_name()} -> {self.convert.get_name()}")
        except Exception as e:
            print(f"Failed to link decodebin for Deck {self.deck_id}: {e}")

    def load_song(self, file_path):
        """Loads a new song into the deck."""
        print(f"Deck {self.deck_id}: Loading song {file_path}")
        self.pipeline.set_state(Gst.State.READY)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE) # Block until state change is complete
        self.src.set_property("location", file_path)
        # Go to PAUSED to allow decodebin to discover the stream format (preroll).
        self.pipeline.set_state(Gst.State.PAUSED)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE) # Block until state change is complete
        self.state = PlaybackState.PAUSED # Ready to play
        print(f"Deck {self.deck_id}: State changed to PAUSED")

    def play(self):
        """Starts or resumes playback for this deck."""
        if self.state != PlaybackState.PLAYING:
            print(f"Deck {self.deck_id}: Setting to PLAYING at volume {self.current_volume:.2f}")
            self.pipeline.set_state(Gst.State.PLAYING)
            self.pipeline.get_state(Gst.CLOCK_TIME_NONE) # Block until state change is complete
            self.state = PlaybackState.PLAYING
        else:
            print(f"Deck {self.deck_id}: Already playing at volume {self.current_volume:.2f}")

    def pause(self):
        """Pauses playback for this deck."""
        if self.state == PlaybackState.PLAYING:
            print(f"Deck {self.deck_id}: Setting to PAUSED")
            self.pipeline.set_state(Gst.State.PAUSED)
            self.pipeline.get_state(Gst.CLOCK_TIME_NONE) # Block until state change is complete
            self.state = PlaybackState.PAUSED
        else:
            print(f"Deck {self.deck_id}: Not currently playing")

    def set_volume(self, volume):
        """Set deck volume (0.0 to 1.0)"""
        volume = max(0.0, min(1.0, volume))
        self.current_volume = volume
        if self.volume_pad:
            self.volume_pad.set_property("volume", volume)
            if DEBUG_PRINT_VOLUME:
                print(f"Deck {self.deck_id}: Volume set to {volume:.2f}")

class DJMixer:
    """Main DJ mixer application, controlled programmatically."""

    def __init__(self):
        Gst.init(None)
        self.pipeline = Gst.Pipeline.new("dj-pipeline")
        self.loop = GLib.MainLoop()
        self.decks = {}

        self._build_pipeline()
        
        # Run the GStreamer main loop in a separate thread
        self.thread = threading.Thread(target=self.loop.run, daemon=True)

        # Add a bus watcher to receive messages from the pipeline
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus_message)

    def on_bus_message(self, bus, message):
        """Catches messages from the GStreamer bus and prints them."""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            print(f"!!! Pipeline ERROR: {message.src.get_name()} -> {err.message}")
            if dbg:
                print(f"    Debug info: {dbg}")
        elif t == Gst.MessageType.WARNING:
            err, dbg = message.parse_warning()
            print(f"!!! Pipeline WARNING: {message.src.get_name()} -> {err.message}")
            if dbg:
                print(f"    Debug info: {dbg}")
        elif t == Gst.MessageType.EOS:
            print(f"--- End-of-Stream from {message.src.get_name()} ---")
        elif t == Gst.MessageType.STATE_CHANGED:
            # Filter for messages from the pipeline itself
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"--- Pipeline state changed from {old_state.value_nick.upper()} to {new_state.value_nick.upper()} ---")

    def _build_pipeline(self):
        """Build the GStreamer audio pipeline for two decks."""
        print("Building DUAL DECK pipeline for programmatic control...")

        # --- Create shared output elements ---
        mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        output_convert = Gst.ElementFactory.make("audioconvert", "output_convert")
        output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

        if not all([mixer, output_convert, output_sink]):
            raise RuntimeError("Failed to create mixer or output elements.")

        self.pipeline.add(mixer)
        self.pipeline.add(output_convert)
        self.pipeline.add(output_sink)

        # --- Create Decks ---
        self.decks['deck1'] = DJDeck(1, self.pipeline)
        self.decks['deck2'] = DJDeck(2, self.pipeline)

        # --- Link Decks to Mixer ---
        for i, deck in self.decks.items():
            src_pad = deck.rate.get_static_pad("src")
            sink_pad = mixer.get_request_pad(f"sink_{deck.deck_id}")
            if not sink_pad:
                raise RuntimeError(f"Could not get sink pad for {i} from mixer")
            src_pad.link(sink_pad)
            deck.volume_pad = sink_pad # Store the mixer pad for volume control
            deck.set_volume(DEFAULT_VOLUME) # Set initial volume

        # --- Link Mixer to Output ---
        mixer.link(output_convert)
        output_convert.link(output_sink)

        print("GStreamer pipeline built successfully")

    def run(self):
        """Start the DJ mixer's GStreamer loop in a background thread."""
        print("Starting GStreamer main loop in background thread...")
        self.thread.start()
        # Initial state to PAUSED allows loading but doesn't start playback immediately
        self.pipeline.set_state(Gst.State.PAUSED)
        print("DJ Mixer is running.")

    def stop(self):
        """Stop the DJ mixer and cleanup."""
        print("Stopping DJ mixer...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        print("DJ mixer stopped.")

    def get_deck(self, deck_id):
        """Get a deck object by its ID string (e.g., 'deck1')."""
        deck = self.decks.get(deck_id)
        if not deck:
            raise ValueError(f"Invalid deck_id: {deck_id}. Must be 'deck1' or 'deck2'.")
        return deck

    def load_song(self, deck_id, file_path):
        """Load a song into the specified deck."""
        if not os.path.exists(file_path):
            print(f"Error: File not found: {file_path}")
            return
        deck = self.get_deck(deck_id)
        deck.load_song(file_path)

    def play(self, deck_id):
        """Play the specified deck."""
        deck = self.get_deck(deck_id)
        deck.play()

    def pause(self, deck_id):
        """Pause the specified deck."""
        deck = self.get_deck(deck_id)
        deck.pause()

    def toggle_play(self, deck_id):
        """Toggle play/pause for the specified deck."""
        deck = self.get_deck(deck_id)
        if deck.state == PlaybackState.PLAYING:
            deck.pause()
        else:
            deck.play()

    def set_volume(self, deck_id, volume):
        """Set the volume for the specified deck."""
        deck = self.get_deck(deck_id)
        deck.set_volume(volume)


def main():
    """Example usage for testing the refactored mixer."""
    print("--- DJ Mixer Test ---")
    
    # Find some example MP3s
    script_dir = os.path.dirname(os.path.abspath(__file__))
    song1_path = os.path.join(script_dir, "example-mp3/chappell-roan-red-wine-supernova.mp3")
    song2_path = os.path.join(script_dir, "example-mp3/charli-xcx-365.mp3")

    if not os.path.exists(song1_path) or not os.path.exists(song2_path):
        print("Error: Example MP3 files not found. Make sure they are in rpi/example-mp3/")
        return

    mixer = DJMixer()
    mixer.run()

    try:
        print("\nCommands: load1, load2, play1, pause1, play2, pause2, vol1 [0-1], vol2 [0-1], toggle1, toggle2, stop, exit")
        
        # Load songs initially
        mixer.load_song('deck1', song1_path)
        mixer.load_song('deck2', song2_path)
        print("Songs loaded into Deck 1 and Deck 2.")

        while True:
            cmd_input = input("> ").strip().lower().split()
            if not cmd_input:
                continue
            
            command = cmd_input[0]

            if command == "exit":
                break
            elif command == "stop":
                mixer.stop()
            elif command == "load1":
                mixer.load_song('deck1', song1_path)
            elif command == "load2":
                mixer.load_song('deck2', song2_path)
            elif command == "play1":
                mixer.play('deck1')
            elif command == "pause1":
                mixer.pause('deck1')
            elif command == "toggle1":
                mixer.toggle_play('deck1')
            elif command == "play2":
                mixer.play('deck2')
            elif command == "pause2":
                mixer.pause('deck2')
            elif command == "toggle2":
                mixer.toggle_play('deck2')
            elif command == "vol1" and len(cmd_input) > 1:
                try:
                    mixer.set_volume('deck1', float(cmd_input[1]))
                except ValueError:
                    print("Invalid volume. Must be a number between 0.0 and 1.0")
            elif command == "vol2" and len(cmd_input) > 1:
                try:
                    mixer.set_volume('deck2', float(cmd_input[1]))
                except ValueError:
                    print("Invalid volume. Must be a number between 0.0 and 1.0")
            else:
                print("Unknown command")

    except KeyboardInterrupt:
        print("\nCtrl+C detected.")
    finally:
        mixer.stop()
        print("Test finished.")


if __name__ == "__main__":
    main()
