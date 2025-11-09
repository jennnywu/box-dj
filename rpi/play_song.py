#!/usr/bin/env python3
"""
GStreamer Player Class
"""

import gi
import os
import threading
import time

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

class Player:
    """A simple GStreamer player to play one song at a time."""

    def __init__(self):
        Gst.init(None)
        self.pipeline = None
        self.loop = GLib.MainLoop()
        
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        print("GStreamer MainLoop started in background thread.")

    def _on_bus_message(self, bus, message):
        """Catches and prints messages from the GStreamer bus."""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            print(f"!!! Player ERROR: {message.src} -> {err.message}")
            if dbg:
                print(f"    Debug info: {dbg}")
        elif t == Gst.MessageType.EOS:
            print(f"--- Player: End-of-Stream reached. Stopping pipeline. ---")
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
        # elif t == Gst.MessageType.STATE_CHANGED:
        #     old, new, pending = message.parse_state_changed()
        #     if message.src == self.pipeline:
        #         # FIX: Use Gst.State.get_name() passing the state value (old or new) 
        #         # as the argument, instead of calling get_name() on the value itself.
        #         old_name = Gst.State.get_name(old)
        #         new_name = Gst.State.get_name(new)
        #         print(f"Pipeline state changed from {old_name} to {new_name}")


    def play_song(self, song_path):
        """Stops any currently playing song and starts a new one."""
        
        # NOTE: The os.path.exists check here should use the absolute path 
        # passed from main()
        if not os.path.exists(song_path):
            print(f"Error: File not found (Python check): {song_path}")
            return

        # 1. Stop and destroy the old pipeline if it exists
        if self.pipeline:
            print("Stopping existing pipeline...")
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        # 2. Build a new pipeline using 'playbin' (Recommended robust approach)
        print(f"Building new pipeline for: {song_path}")
        
        # Use playbin for automatic handling of decoding and sink selection
        self.pipeline = Gst.ElementFactory.make("playbin", "player") 
        if not self.pipeline:
             print("ERROR: Could not create playbin element. Is GStreamer installed?")
             return

        # Convert the absolute file path to a URI (required for playbin)
        uri = Gst.filename_to_uri(song_path)
        self.pipeline.set_property("uri", uri)
        
        # 3. Add a bus watcher to the new pipeline
        bus = self.pipeline.get_bus()
        bus.add_signal_watch() 
        bus.connect("message", self._on_bus_message)

        # 4. Start playing
        print("Setting pipeline to PLAYING...")
        self.pipeline.set_state(Gst.State.PLAYING)

    def pause(self):
        """Pauses the currently playing song."""
        if self.pipeline and self.pipeline.get_state(Gst.CLOCK_TIME_NONE).state == Gst.State.PLAYING:
            print("Pausing pipeline...")
            self.pipeline.set_state(Gst.State.PAUSED)

    def resume(self):
        """Resumes a paused song."""
        if self.pipeline and self.pipeline.get_state(Gst.CLOCK_TIME_NONE).state == Gst.State.PAUSED:
            print("Resuming pipeline...")
            self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        """Stops playback completely and quits the main loop."""
        print("Stopping player...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self.loop.is_running():
            self.loop.quit()


# --- Test Block (with fixed absolute paths) ---
def main():
    """Main function to test the Player class."""
    
    # Define the base user directory
    HOME_PATH = os.path.expanduser("~") 
    HOME_PATH = "/home/jenny/box-dj/"

    file_path1 = os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3")
    file_path2 = os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3")

    # Sanity check for the test files (MUST USE ABSOLUTE PATHS NOW)
    if not (os.path.exists(file_path1) and os.path.exists(file_path2)):
        print("\n*** 🛑 TEST SETUP ERROR 🛑 ***")
        print("Please verify your directory structure. Expected files at:")
        print(f"Path 1: {file_path1}")
        print(f"Path 2: {file_path2}")
        print("The test cannot proceed without valid, absolute paths.")
        return

    print("\n--- Starting Player Test ---")
    player = Player()
    
    # --- Test Sequence ---
    print("\n[STEP 1/5] Playing Song 1...")
    player.play_song(file_path1)
    time.sleep(4) 

    print("\n[STEP 2/5] Pausing...")
    player.pause()
    time.sleep(2) 

    print("\n[STEP 3/5] Resuming...")
    player.resume()
    time.sleep(4) 

    print("\n[STEP 4/5] Switching to Song 2...")
    player.play_song(file_path2)
    time.sleep(6) 

    print("\n[STEP 5/5] Stopping and exiting...")
    player.stop()

    if player.thread.is_alive():
        player.thread.join(timeout=1) 
    
    print("--- Player Test Finished ---")


if __name__ == "__main__":
    main()