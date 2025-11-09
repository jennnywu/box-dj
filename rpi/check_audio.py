#!/usr/bin/env python3

"""
GStreamer Player Class with a dedicated background thread for the MainLoop.
"""

import gi
import sys
import os
import tty
import termios
import threading # <-- New import for threading

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

HOME_PATH = "/home/jenny/box-dj/"

# Global state variables (kept for simplicity with terminal control)
current_rate_1 = 1.0
current_rate_2 = 1.0
current_volume_1 = 1.0
current_volume_2 = 1.0

# --- Player Class Definition ---
class Player:
    """Manages the GStreamer pipeline and MainLoop in a background thread."""

    def __init__(self, file_path1, file_path2):
        Gst.init(None)
        self.pipeline = None
        self.loop = GLib.MainLoop()
        self.file_path1 = file_path1
        self.file_path2 = file_path2

        self.rate1 = None
        self.rate2 = None
        self.sink_pad_1 = None
        self.sink_pad_2 = None
        
        # 1. Start the GStreamer main loop in a separate thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("GStreamer MainLoop started in background thread.")

        # 2. Build the pipeline (safely executed on the GLib thread)
        GLib.idle_add(self._build_and_start_pipeline)

    def _run_loop(self):
        """Target function for the background thread."""
        try:
            self.loop.run()
        except Exception as e:
            print(f"GLib MainLoop Error: {e}")

    def _on_pad_added(self, element, pad, target_element):
        """Called by decodebin's 'pad-added' signal (runs on GLib thread)."""
        print(f"Pad added to {element.get_name()}, linking to {target_element.get_name()}")
        sink_pad = target_element.get_static_pad("sink")
        if sink_pad.is_linked():
            print(f"Sink pad on {target_element.get_name()} is already linked.")
            return

        try:
            pad.link(sink_pad)
            print(f"Successfully linked {element.get_name()} to {target_element.get_name()}")
        except Gst.LinkError:
            print(f"!!! FAILED to link {element.get_name()} to {target_element.get_name()} !!!")

    def _on_bus_message(self, bus, message):
        """Handle GStreamer Bus Messages (runs on GLib thread)."""
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End-Of-Stream reached.")
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n!!! GStreamer Error: {err.message} (Debug: {debug}) !!!\n")
            # You might want to shut down the loop here in a real application
        return True # Keep the watch active
        
    def _build_and_start_pipeline(self):
        """Builds the pipeline and sets it to PLAYING (runs on GLib thread)."""
        self.pipeline = Gst.Pipeline.new("dj-pipeline")

        # --- Deck 1 Elements ---
        src1 = Gst.ElementFactory.make("filesrc", "src1")
        src1.set_property("location", self.file_path1)
        decode1 = Gst.ElementFactory.make("decodebin", "decode1")
        convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
        self.rate1 = Gst.ElementFactory.make("pitch", "rate1") # Store for control

        # --- Deck 2 Elements ---
        src2 = Gst.ElementFactory.make("filesrc", "src2")
        src2.set_property("location", self.file_path2)
        decode2 = Gst.ElementFactory.make("decodebin", "decode2")
        convert2 = Gst.ElementFactory.make("audioconvert", "convert2")
        self.rate2 = Gst.ElementFactory.make("pitch", "rate2") # Store for control

        # --- Mixer and Output ---
        mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        output_convert = Gst.ElementFactory.make("audioconvert", "output_convert_main")
        output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

        if not all([self.pipeline, src1, decode1, convert1, self.rate1, src2, decode2, convert2, self.rate2, mixer, output_convert, output_sink]):
            print("!!! Not all elements could be created. Missing a plugin? !!!")
            self.loop.quit()
            return False

        # Add elements to pipeline
        for element in [src1, decode1, convert1, self.rate1, src2, decode2, convert2, self.rate2, mixer, output_convert, output_sink]:
            self.pipeline.add(element)

        # Deck 1 Links
        src1.link(decode1)
        decode1.connect("pad-added", self._on_pad_added, convert1)
        convert1.link(self.rate1)

        src_pad_1 = self.rate1.get_static_pad("src") 
        self.sink_pad_1 = mixer.get_request_pad("sink_%u") # Store for volume control
        print(f"Got mixer pad 1: {self.sink_pad_1.get_name()}")
        src_pad_1.link(self.sink_pad_1)

        # Deck 2 Links
        src2.link(decode2)
        decode2.connect("pad-added", self._on_pad_added, convert2)
        convert2.link(self.rate2)

        src_pad_2 = self.rate2.get_static_pad("src")
        self.sink_pad_2 = mixer.get_request_pad("sink_%u") # Store for volume control
        print(f"Got mixer pad 2: {self.sink_pad_2.get_name()}")
        src_pad_2.link(self.sink_pad_2)

        # Output Links
        mixer.link(output_convert)
        output_convert.link(output_sink)

        # Add bus watch to catch errors (CRITICAL for debugging)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        # Start Playback
        print("Starting pipeline...")
        self.pipeline.set_state(Gst.State.PLAYING)
        return False # Do not repeat the idle_add

    def cleanup(self):
        """Stop the pipeline and the main loop."""
        print("\nStopping pipeline...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop.is_running():
            self.loop.quit()

# --- Key Press Handler (now controls the Player instance) ---

def on_key_press(source_fd, condition, player):
    """
    Called by the main thread's GLib.MainLoop to handle keyboard input.
    Commands are marshalled to the GStreamer thread via GLib.idle_add().
    """
    global current_rate_1, current_rate_2, current_volume_1, current_volume_2

    char = sys.stdin.read(1)

    # Function to safely update a property on the GLib thread
    def update_property(element, prop_name, value):
        element.set_property(prop_name, value)
        return False # Do not repeat

    # --- Deck 2 Speed (j, k) ---
    if char == 'k':
        current_rate_2 += 0.05
        print(f"Speed 2: {current_rate_2:.2f}")
        GLib.idle_add(update_property, player.rate2, "rate", current_rate_2)
    elif char == 'j':
        current_rate_2 = max(0.05, current_rate_2 - 0.05)
        print(f"Speed 2: {current_rate_2:.2f}")
        GLib.idle_add(update_property, player.rate2, "rate", current_rate_2)

    # --- Deck 1 Speed (d, f) ---
    elif char == 'f':
        current_rate_1 += 0.05
        print(f"Speed 1: {current_rate_1:.2f}")
        GLib.idle_add(update_property, player.rate1, "rate", current_rate_1)
    elif char == 'd':
        current_rate_1 = max(0.05, current_rate_1 - 0.05)
        print(f"Speed 1: {current_rate_1:.2f}")
        GLib.idle_add(update_property, player.rate1, "rate", current_rate_1)

    # --- Deck 1 Volume (e, c) ---
    # Note: Volume property is set on the audiomixer sink pad
    elif char == 'e':
        current_volume_1 = min(1.0, current_volume_1 + 0.1)
        print(f"Volume 1: {current_volume_1:.1f}")
        GLib.idle_add(update_property, player.sink_pad_1, "volume", current_volume_1)
    elif char == 'c':
        current_volume_1 = max(0.0, current_volume_1 - 0.1)
        print(f"Volume 1: {current_volume_1:.1f}")
        GLib.idle_add(update_property, player.sink_pad_1, "volume", current_volume_1)

    # --- Deck 2 Volume (i, m) ---
    elif char == 'i':
        current_volume_2 = min(1.0, current_volume_2 + 0.1)
        print(f"Volume 2: {current_volume_2:.1f}")
        GLib.idle_add(update_property, player.sink_pad_2, "volume", current_volume_2)
    elif char == 'm':
        current_volume_2 = max(0.0, current_volume_2 - 0.1)
        print(f"Volume 2: {current_volume_2:.1f}")
        GLib.idle_add(update_property, player.sink_pad_2, "volume", current_volume_2)

    return True

# --- Main Console Loop ---

def main():
    file_path1 = os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3")
    file_path2 = os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3")

    # The main thread now runs its own GLib.MainLoop to handle terminal input
    main_loop = GLib.MainLoop() 
    
    # Initialize the player, which starts the GStreamer thread and pipeline
    player = Player(file_path1, file_path2) 

    # --- Terminal Setup ---
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    print("\nPipeline is running.")
    print("  Deck 1:")
    print("        'd' (slow) / 'f' (fast)")
    print("        'e' (volume up) / 'c' (volume down)")
    print("  Deck 2:")
    print("        'j' (slow) / 'k' (fast)")
    print("        'i' (volume up) / 'm' (volume down)")
    print("Press Ctrl+C to stop.\n")

    try:
        # Set terminal to "cbreak" mode (no waiting for 'Enter')
        tty.setcbreak(sys.stdin.fileno())

        # Add the keyboard watch to the main thread's GLib.MainLoop
        GLib.io_add_watch(fd, GLib.IO_IN, on_key_press, player)

        main_loop.run()
    except KeyboardInterrupt:
        print("\nMain loop interrupted.")
    finally:
        # Restore terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Clean up the GStreamer player
        player.cleanup()
        main_loop.quit()

if __name__ == "__main__":
    main()