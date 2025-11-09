#!/usr/bin/env python3
"""
GStreamer Player Class
"""

import gi
import os
import threading

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

class Player:
    """A simple GStreamer player to play one song at a time."""

    def __init__(self):
        Gst.init(None)
        self.pipeline = None
        self.loop = GLib.MainLoop()
        
        # Run the GStreamer main loop in a separate thread
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        print("GStreamer MainLoop started in background thread.")

    def _on_bus_message(self, bus, message):
        """Catches and prints messages from the GStreamer bus."""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            print(f"!!! Player ERROR: {message.src.get_name()} -> {err.message}")
            if dbg:
                print(f"    Debug info: {dbg}")
        elif t == Gst.MessageType.EOS:
            print(f"--- Player: End-of-Stream reached. Stopping pipeline. ---")
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None

    def play_song(self, song_path):
        """Stops any currently playing song and starts a new one."""
        if not os.path.exists(song_path):
            print(f"Error: File not found: {song_path}")
            return

        # 1. Stop and destroy the old pipeline if it exists
        if self.pipeline:
            print("Stopping existing pipeline...")
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        # 2. Build a new pipeline using Gst.parse_launch for simplicity
        print(f"Building new pipeline for: {song_path}")
        # Note: Using single quotes around the path is important for Gst.parse_launch
        self.pipeline = Gst.parse_launch(
            f"filesrc location='{song_path}' ! decodebin ! audioconvert ! audioresample ! pulsesink"
        )

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
