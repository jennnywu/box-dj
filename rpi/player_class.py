#!/usr/bin/env python3

"""
GStreamer Player Class with a dedicated background thread for the MainLoop.
Designed for server interaction via WebSockets.
"""

import gi
import sys
import os
import threading 
from typing import List, Optional

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Global Path Variable - USE ACTUAL PATHS ON YOUR SERVER
HOME_PATH = "/home/jenny/box-dj/" 

# --- Player Class Definition ---
class Player:
    """Manages the GStreamer pipeline and MainLoop in a background thread."""

    def __init__(self, playlist: List[str]):
        """
        Initializes the GStreamer environment and starts the background thread.
        :param playlist: A list of full file paths for the songs.
        """
        Gst.init(None)
        
        # Internal State
        self.pipeline: Optional[Gst.Pipeline] = None
        self.loop = GLib.MainLoop()
        
        self.playlist: List[str] = playlist
        self.current_song_index: int = 0
        self.active_deck: int = 1 # 1 or 2
        
        # GStreamer Elements for Control
        self.rate1: Optional[Gst.Element] = None
        self.rate2: Optional[Gst.Element] = None
        self.sink_pad_1: Optional[Gst.Pad] = None
        self.sink_pad_2: Optional[Gst.Pad] = None
        self.src1: Optional[Gst.Element] = None
        self.src2: Optional[Gst.Element] = None

        # 1. Start the GStreamer main loop in a separate thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("GStreamer MainLoop started in background thread.")

        # 2. Build the pipeline and load initial songs (safely executed on the GLib thread)
        GLib.idle_add(self._build_and_start_pipeline)

    def _run_loop(self):
        """Target function for the background thread."""
        try:
            self.loop.run()
        except Exception as e:
            print(f"GLib MainLoop Error: {e}")

    def _on_pad_added(self, element, pad, target_element):
        """Called by decodebin's 'pad-added' signal (runs on GLib thread)."""
        sink_pad = target_element.get_static_pad("sink")
        if sink_pad.is_linked():
            return
        try:
            pad.link(sink_pad)
        except Gst.LinkError:
            print(f"!!! FAILED to link {element.get_name()} to {target_element.get_name()} !!!")

    def _on_bus_message(self, bus, message):
        """Handle GStreamer Bus Messages (runs on GLib thread)."""
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End-Of-Stream reached on an element.")
            # Auto-advance to the next song in the playlist
            GLib.idle_add(self._load_next_song)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n!!! GStreamer Error: {err.message} (Debug: {debug}) !!!\n")
        return True
        
    def _build_and_start_pipeline(self):
        """Builds the complete pipeline (runs on GLib thread)."""
        self.pipeline = Gst.Pipeline.new("dj-pipeline")

        # --- Deck 1 Elements ---
        self.src1 = Gst.ElementFactory.make("filesrc", "src1") # Store for swapping files
        decode1 = Gst.ElementFactory.make("decodebin", "decode1")
        convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
        self.rate1 = Gst.ElementFactory.make("pitch", "rate1") # Store for control

        # --- Deck 2 Elements ---
        self.src2 = Gst.ElementFactory.make("filesrc", "src2") # Store for swapping files
        decode2 = Gst.ElementFactory.make("decodebin", "decode2")
        convert2 = Gst.ElementFactory.make("audioconvert", "convert2")
        self.rate2 = Gst.ElementFactory.make("pitch", "rate2") # Store for control

        # --- Mixer and Output ---
        mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        output_convert = Gst.ElementFactory.make("audioconvert", "output_convert_main")
        output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

        if not all([self.pipeline, self.src1, decode1, convert1, self.rate1, self.src2, decode2, convert2, self.rate2, mixer, output_convert, output_sink]):
            print("!!! Not all elements could be created. Missing a plugin? !!!")
            self.loop.quit()
            return False

        # Add elements to pipeline
        for element in [self.src1, decode1, convert1, self.rate1, self.src2, decode2, convert2, self.rate2, mixer, output_convert, output_sink]:
            self.pipeline.add(element)

        # Deck 1 Links
        self.src1.link(decode1)
        decode1.connect("pad-added", self._on_pad_added, convert1)
        convert1.link(self.rate1)
        src_pad_1 = self.rate1.get_static_pad("src") 
        self.sink_pad_1 = mixer.get_request_pad("sink_%u")
        src_pad_1.link(self.sink_pad_1)

        # Deck 2 Links
        self.src2.link(decode2)
        decode2.connect("pad-added", self._on_pad_added, convert2)
        convert2.link(self.rate2)
        src_pad_2 = self.rate2.get_static_pad("src")
        self.sink_pad_2 = mixer.get_request_pad("sink_%u")
        src_pad_2.link(self.sink_pad_2)

        # Output Links
        mixer.link(output_convert)
        output_convert.link(output_sink)

        # Add bus watch (CRITICAL for debugging/EOS)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        
        # Load initial files and set initial state
        self._load_file_on_deck(1, self.playlist[0])
        self._load_file_on_deck(2, self.playlist[1] if len(self.playlist) > 1 else self.playlist[0])
        
        # Set to PAUSED initially, ready to play
        self.pipeline.set_state(Gst.State.PAUSED)
        print("Pipeline built and initialized to PAUSED.")

        return False # Do not repeat the idle_add

    def _load_file_on_deck(self, deck_num: int, file_path: str):
        """Internal: Changes the file location for a specific deck (GLib thread)."""
        src = self.src1 if deck_num == 1 else self.src2
        if src and os.path.exists(file_path):
            # Must be in READY or NULL state to set a new filesrc location
            current_state = self.pipeline.get_state(Gst.CLOCK_TIME_NONE).state
            
            # Temporarily pause/stop to change source location
            if current_state == Gst.State.PLAYING:
                src.set_state(Gst.State.NULL)
            
            src.set_property("location", file_path)
            
            # Restore state
            if current_state == Gst.State.PLAYING:
                 src.set_state(Gst.State.PLAYING)
            elif current_state == Gst.State.PAUSED:
                src.set_state(Gst.State.PAUSED)

            print(f"Deck {deck_num} loaded: {os.path.basename(file_path)}")
            return True
        else:
            print(f"!!! Error: Deck {deck_num} source not found or file does not exist: {file_path}")
            return False

    def _load_next_song(self):
        """Internal: Loads the next song in the playlist onto the inactive deck (GLib thread)."""
        self.current_song_index = (self.current_song_index + 1) % len(self.playlist)
        next_song_path = self.playlist[self.current_song_index]
        inactive_deck = 2 if self.active_deck == 1 else 1
        
        self._load_file_on_deck(inactive_deck, next_song_path)
        print(f"Ready to transition to: {os.path.basename(next_song_path)}")
        return False

    def _set_pipeline_state(self, state: Gst.State):
        """Internal: Safely set the pipeline state (GLib thread)."""
        if self.pipeline:
            self.pipeline.set_state(state)
            print(f"Pipeline state set to: {state.value_nick.upper()}")
        return False

    def _set_pad_volume(self, deck_num: int, volume: float):
        """Internal: Safely set the volume on a mixer sink pad (GLib thread)."""
        pad = self.sink_pad_1 if deck_num == 1 else self.sink_pad_2
        if pad:
            pad.set_property("volume", volume)
            print(f"Deck {deck_num} volume set to: {volume:.2f}")
        return False

    # --- Public Methods for Server/Websocket Control ---

    def play_all(self):
        """Sets the entire pipeline to PLAYING."""
        GLib.idle_add(self._set_pipeline_state, Gst.State.PLAYING)

    def pause_all(self):
        """Sets the entire pipeline to PAUSED."""
        GLib.idle_add(self._set_pipeline_state, Gst.State.PAUSED)

    def play_deck(self, deck_num: int):
        """
        Transition control to a specific deck by setting its volume to 1.0 
        and the other's to 0.0. Also sets the pipeline to PLAYING if needed.
        """
        if deck_num not in (1, 2):
            print("Invalid deck number.")
            return

        print(f"\n*** Playing Deck {deck_num} ***")
        self.active_deck = deck_num
        inactive_deck = 2 if deck_num == 1 else 1
        
        # Set volumes (safely on GLib thread)
        GLib.idle_add(self._set_pad_volume, deck_num, 1.0)
        GLib.idle_add(self._set_pad_volume, inactive_deck, 0.0)
        
        # Ensure it's playing
        self.play_all()

    def play_mixed(self, vol1: float, vol2: float):
        """
        Play both decks simultaneously at specified volume levels.
        Volumes must be between 0.0 and 1.0.
        """
        v1 = max(0.0, min(1.0, vol1))
        v2 = max(0.0, min(1.0, vol2))
        
        print(f"\n*** Playing Mixed: Deck 1 ({v1:.2f}) & Deck 2 ({v2:.2f}) ***")
        
        # Set volumes (safely on GLib thread)
        GLib.idle_add(self._set_pad_volume, 1, v1)
        GLib.idle_add(self._set_pad_volume, 2, v2)
        
        # Ensure it's playing
        self.play_all()


    def play_next(self):
        """
        Transitions playback to the next song loaded on the inactive deck
        and immediately loads the next track into the now inactive deck.
        """
        new_active_deck = 2 if self.active_deck == 1 else 1
        
        # 1. Switch active deck and volumes
        self.play_deck(new_active_deck)
        
        # 2. Immediately load the next song into the newly inactive deck
        GLib.idle_add(self._load_next_song)
        
        print(f"Switched to Deck {new_active_deck}. Next song loading...")

    def set_volume(self, deck_num: int, volume: float):
        """Set the volume for a specific deck (0.0 to 1.0)."""
        v = max(0.0, min(1.0, volume))
        GLib.idle_add(self._set_pad_volume, deck_num, v)

    def cleanup(self):
        """Stop the pipeline and the main loop."""
        print("\nStopping pipeline...")
        if self.pipeline:
            # Send EOS before NULL to ensure clean shutdown (optional but good practice)
            self.pipeline.send_event(Gst.Event.new_eos())
            # Wait a moment for EOS to process (optional)
            Gst.StateChangeReturn.SUCCESS
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop.is_running():
            self.loop.quit()
        # Wait for the thread to finish
        self.thread.join(timeout=1.0)
        print("Cleanup complete.")

if __name__ == "__main__":
    import time

    # --- Setup ---
    # NOTE: You MUST replace these with actual, working MP3 paths on your server
    SONGS = [
        os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"),
        os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3"),
        os.path.join(HOME_PATH, "rpi/example-mp3/another-track.mp3"), # Third track for "play_next"
        os.path.join(HOME_PATH, "rpi/example-mp3/yet-another.mp3"),    # Fourth track
    ]

    # Filter out non-existent files for safety (highly recommended)
    working_playlist = [s for s in SONGS if os.path.exists(s)]
    if len(working_playlist) < 2:
         print(f"!!! ERROR: Need at least 2 working MP3 files. Please check the paths defined in SONGS and HOME_PATH: {HOME_PATH}")
         # Attempting to create dummy files if they don't exist to allow the script to run
         for path in SONGS:
             if not os.path.exists(path):
                 print(f"   (Creating dummy file at: {path})")
                 os.makedirs(os.path.dirname(path), exist_ok=True)
                 with open(path, 'w') as f:
                     f.write("This is a dummy file for testing, replace with an actual MP3.")
         # If dummy creation fails or is insufficient, exit
         if len(working_playlist) < 2:
             sys.exit(1)
         
    # Use the working playlist or the full list if we created dummies
    playlist_to_use = working_playlist if working_playlist else SONGS 
    
    # Initialize the player
    player = Player(playlist_to_use) 

    # Give GStreamer a moment to build the pipeline and set initial state
    time.sleep(1) 

    try:
        print("\n--- TEST: 1. Initial Play (Deck 1) ---")
        player.play_deck(1)
        time.sleep(5) # Play for 5 seconds

        print("\n--- TEST: 2. Pause ---")
        player.pause_all()
        time.sleep(2) # Paused for 2 seconds

        print("\n--- TEST: 3. Play Next (Switch to Deck 2, loading song 3) ---")
        player.play_next()
        time.sleep(5) # Play for 5 seconds

        print("\n--- TEST: 4. Mixed Play (Crossfade) ---")
        # Gradual crossfade from Deck 2 (Song 2) to Deck 1 (Song 3)
        # Your server logic would send these commands over time
        
        # Start mixed play (Deck 2 full, Deck 1 muted)
        player.play_mixed(vol1=0.0, vol2=1.0)
        time.sleep(2) 
        
        # Crossfade: Deck 2 (0.5), Deck 1 (0.5)
        player.play_mixed(vol1=0.5, vol2=0.5)
        time.sleep(2)
        
        # Finish crossfade: Deck 1 (1.0), Deck 2 (0.0) - Deck 1 is now effectively the active deck
        player.play_mixed(vol1=1.0, vol2=0.0)
        player.active_deck = 1 # Manually set the internal state for next 'play_next'
        time.sleep(5)

        print("\n--- TEST: 5. Final Cleanup ---")

    except Exception as e:
        print(f"\nTest Script Error: {e}")
    finally:
        # Clean up the GStreamer player
        player.cleanup()