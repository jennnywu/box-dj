#!/usr/bin/env python3

"""
GStreamer Player Class with a dedicated background thread for the MainLoop.
Includes a method to dynamically load new tracks onto decks.
"""

import gi
import sys
import os
import tty
import termios
import threading
import time # <-- Import time for the test

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

        # --- Element placeholders ---
        # These will be assigned in _build_and_start_pipeline
        self.src1 = None
        self.decode1 = None
        self.convert1 = None
        self.rate1 = None
        
        self.src2 = None
        self.decode2 = None
        self.convert2 = None
        self.rate2 = None
        
        self.mixer = None
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
        """
        Called by decodebin's 'pad-added' signal (runs on GLib thread).
        This is now robust to handle relinking when a track is changed.
        """
        print(f"Pad added to {element.get_name()}, linking to {target_element.get_name()}")
        sink_pad = target_element.get_static_pad("sink")
        
        # --- Critical: Handle Relinking ---
        # If the sink pad is already linked (e.g., from a previous track),
        # we must unlink it before linking the new pad.
        if sink_pad.is_linked():
            print(f"Sink pad on {target_element.get_name()} is already linked. Unlinking...")
            peer_pad = sink_pad.get_peer()
            if peer_pad:
                peer_pad.unlink(sink_pad)
                print("Successfully unlinked old pad.")
            else:
                print("...but could not get peer pad. This might be an issue.")

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
        return True # Keep the watch active
        
    def _build_and_start_pipeline(self):
        """Builds the pipeline and sets it to PLAYING (runs on GLib thread)."""
        self.pipeline = Gst.Pipeline.new("dj-pipeline")

        # --- Deck 1 Elements ---
        self.src1 = Gst.ElementFactory.make("filesrc", "src1")
        self.src1.set_property("location", self.file_path1)
        self.decode1 = Gst.ElementFactory.make("decodebin", "decode1")
        self.convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
        self.rate1 = Gst.ElementFactory.make("pitch", "rate1")

        # --- Deck 2 Elements ---
        self.src2 = Gst.ElementFactory.make("filesrc", "src2")
        self.src2.set_property("location", self.file_path2)
        self.decode2 = Gst.ElementFactory.make("decodebin", "decode2")
        self.convert2 = Gst.ElementFactory.make("audioconvert", "convert2")
        self.rate2 = Gst.ElementFactory.make("pitch", "rate2")

        # --- Mixer and Output ---
        self.mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        self.output_convert = Gst.ElementFactory.make("audioconvert", "output_convert_main")
        self.output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

        all_elements = [
            self.pipeline, self.src1, self.decode1, self.convert1, self.rate1,
            self.src2, self.decode2, self.convert2, self.rate2,
            self.mixer, self.output_convert, self.output_sink
        ]

        if not all(all_elements):
            print("!!! Not all elements could be created. Missing a plugin? !!!")
            self.loop.quit()
            return False

        # Add elements to pipeline (skip pipeline itself)
        for element in all_elements[1:]:
            self.pipeline.add(element)

        # --- Deck 1 Links ---
        self.src1.link(self.decode1)
        self.decode1.connect("pad-added", self._on_pad_added, self.convert1)
        self.convert1.link(self.rate1)

        src_pad_1 = self.rate1.get_static_pad("src") 
        self.sink_pad_1 = self.mixer.get_request_pad("sink_%u") # Store for volume control
        print(f"Got mixer pad 1: {self.sink_pad_1.get_name()}")
        src_pad_1.link(self.sink_pad_1)

        # --- Deck 2 Links ---
        self.src2.link(self.decode2)
        self.decode2.connect("pad-added", self._on_pad_added, self.convert2)
        self.convert2.link(self.rate2)

        src_pad_2 = self.rate2.get_static_pad("src")
        self.sink_pad_2 = self.mixer.get_request_pad("sink_%u") # Store for volume control
        print(f"Got mixer pad 2: {self.sink_pad_2.get_name()}")
        src_pad_2.link(self.sink_pad_2)

        # --- Output Links ---
        self.mixer.link(self.output_convert)
        self.output_convert.link(self.output_sink)

        # Add bus watch to catch errors
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

    # --- NEW METHOD ---
    def load_track(self, deck_number, new_file_path):
        """
        Public method to request a track change. 
        This is safe to call from any thread.
        """
        print(f"\n[Main Thread] Queuing track change for Deck {deck_number} to {new_file_path}")
        # Schedule the actual state-changing work to run on the GStreamer thread
        GLib.idle_add(self._load_track_on_glib_thread, deck_number, new_file_path)

    # --- NEW HELPER METHOD ---
    def _load_track_on_glib_thread(self, deck_number, new_file_path):
        """
        Performs the actual track change. MUST run on the GStreamer (GLib) thread.
        """
        print(f"[GStreamer Thread] Executing track change for Deck {deck_number}...")
        
        target_src = None
        target_decode = None

        if deck_number == 1:
            target_src = self.src1
            target_decode = self.decode1
        elif deck_number == 2:
            target_src = self.src2
            target_decode = self.decode2
        else:
            print(f"[GStreamer Thread] Error: Invalid deck number {deck_number}")
            return False # Do not repeat

        if not target_src or not target_decode:
            print("[GStreamer Thread] Error: Target elements not found.")
            return False # Do not repeat

        # 1. Stop the elements for this deck
        print(f"[GStreamer Thread] Setting Deck {deck_number} elements to NULL")
        target_src.set_state(Gst.State.NULL)
        target_decode.set_state(Gst.State.NULL) # This flushes the decodebin

        # 2. Change file location
        print(f"[GStreamer Thread] Setting new file location...")
        target_src.set_property("location", new_file_path)

        # 3. Restart the elements for this deck
        # This will trigger a new 'pad-added' signal on the decodebin
        print(f"[GStreamer Thread] Setting Deck {deck_number} elements to PLAYING")
        target_src.set_state(Gst.State.PLAYING)
        target_decode.set_state(Gst.State.PLAYING)
        
        print(f"[GStreamer Thread] Track change for Deck {deck_number} complete.")
        return False # Do not repeat

# --- Key Press Handler (Unchanged, but now controls the Player instance) ---

def on_key_press(source_fd, condition, player):
    """
    Called by the main thread's GLib.MainLoop to handle keyboard input.
    Commands are marshalled to the GStreamer thread via GLib.idle_add().
    """
    global current_rate_1, current_rate_2, current_volume_1, current_volume_2

    char = sys.stdin.read(1)

    # Function to safely update a property on the GLib thread
    def update_property(element, prop_name, value):
        if element:
            element.set_property(prop_name, value)
        else:
            print(f"Warning: Element not ready for prop '{prop_name}'")
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

# --- NEW TEST FUNCTION ---

def main_test():
    """
    Automated test to load and switch tracks as requested.
    """
    
    # --- Define Songs ---
    # !! IMPORTANT: Update this path to the new song location !!
    SONGS = [
        os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"),
        os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3"),
        # The new track to load in the middle of the test
        "/home/jenny/dj_downloads/cec27c3cd9_Olivia_Dean_Baby_Steps.mp3",
    ]

    # Verify files exist before starting
    for f in SONGS:
        if not os.path.exists(f):
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"!!! TEST ERROR: Song file not found at: {f} !!!")
            print("!!! Please update the paths in main_test() to run the test. !!!")
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            return

    # This loop keeps the main thread alive
    main_loop = GLib.MainLoop()

    # 1. Initialize the player, which starts the GStreamer thread
    print(f"--- TEST: Loading Deck 1 ({os.path.basename(SONGS[0])}) and Deck 2 ({os.path.basename(SONGS[1])}) ---")
    player = Player(SONGS[0], SONGS[1])

    # Define the test sequence function to run in a separate thread
    def run_test_sequence():
        try:
            # 2. Play both for 5 seconds
            print("--- TEST: Playing both tracks for 5 seconds... ---")
            time.sleep(5)

            # 3. Load song 3 onto disk 1
            print(f"--- TEST: Loading Deck 1 with new track ({os.path.basename(SONGS[2])}) ---")
            # This call is thread-safe
            player.load_track(1, SONGS[2])
            
            print("--- TEST: Playing new Deck 1 and old Deck 2 for 10 more seconds... ---")
            time.sleep(10)
            
            print("--- TEST: Test complete. Shutting down. ---")

        except Exception as e:
            print(f"--- TEST ERROR: {e} ---")
        finally:
            # Stop the player and the main loop
            player.cleanup()
            main_loop.quit()

    # Start the test sequence in a separate thread
    # so it doesn't block the main_loop
    test_thread = threading.Thread(target=run_test_sequence, daemon=True)
    test_thread.start()

    # Run the main loop to keep the process alive
    try:
        main_loop.run()
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        player.cleanup()
        main_loop.quit()


if __name__ == "__main__":
    # main() # Comment out the original interactive main
    main_test() # Run the new automated test