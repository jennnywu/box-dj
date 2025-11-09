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

    def __init__(self, playlist: Optional[List[str]] = None):
        """
        Initializes the GStreamer environment and starts the background thread.
        :param playlist: A list of full file paths for the songs.
        """
        Gst.init(None)
        
        self.active_deck: int = 1
        
        # Internal State
        self.pipeline: Optional[Gst.Pipeline] = None
        self.loop = GLib.MainLoop()
        
        self.playlist: List[str] = playlist or []
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
    
    def _perform_pending_seek(self, deck_num: int):
        """Internal: Performs a *targeted* flush-seek on a specific src element."""
        if not self.pipeline:
            return False # Do not repeat

        src_element_name = f"src{deck_num}"
        src = self.pipeline.get_by_name(src_element_name)
        
        if src:
            print(f"--- PENDING_SEEK: Performing TARGETED seek to 0 on {src_element_name} now. ---")
            # Seek the element, not the whole pipeline
            src.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                0 # Seek to 0 time
            )
        else:
            print(f"--- PENDING_SEEK: ERROR! Could not find {src_element_name} to seek.")
            
        return False # Do not repeat

    def _on_pad_added(self, element, pad, target_element):
        """Called by decodebin's 'pad-added' signal (runs on GLib thread)."""
        print(f"\n+++ PAD_ADDED: Signal from '{element.get_name()}' for target '{target_element.get_name()}'")
        sink_pad = target_element.get_static_pad("sink")
        
        if sink_pad.is_linked():
            # This can still happen on rare occasions, so we'll just log it.
            # The *real* fix was unlinking in _load_file_on_deck
            print(f"!!! PAD_ADDED: Target '{target_element.get_name()}' sink was already linked. This is unusual.")
            return

        print(f"+++ PAD_ADDED: Linking new pad from '{element.get_name()}' to '{target_element.get_name()}'")
        try:
            pad.link(sink_pad)
        except Gst.LinkError:
            print(f"!!! FAILED to link {element.get_name()} to {target_element.get_name()} !!!")
            return
        
        # Check if this link was triggered by a reload and needs a seek.
        element_name = element.get_name()
        deck_num = -1
        
        if element_name == "decode1" and self.seek_pending_on_deck_1:
            deck_num = 1
            self.seek_pending_on_deck_1 = False
        elif element_name == "decode2" and self.seek_pending_on_deck_2:
            deck_num = 2
            self.seek_pending_on_deck_2 = False
            
        if deck_num != -1:
            print(f"+++ PAD_ADDED: Link complete. Queueing PENDING TARGETED SEEK for Deck {deck_num}...")
            # Pass deck_num as an argument
            GLib.idle_add(lambda: self._perform_pending_seek(deck_num))

    def _on_bus_message(self, bus, message):
        """Handle GStreamer Bus Messages (runs on GLib thread)."""
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End-Of-Stream reached on an element.")
            # Auto-advance to the next song in the playlist
            if self.playlist:
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
        self.src1.set_property("location", os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"))
        decode1 = Gst.ElementFactory.make("decodebin", "decode1")
        convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
        self.rate1 = Gst.ElementFactory.make("pitch", "rate1") # Store for control

        # --- Deck 2 Elements ---
        self.src2 = Gst.ElementFactory.make("filesrc", "src2") # Store for swapping files
        self.src2.set_property("location", os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3"))
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
        self.sink_pad_1 = mixer.request_pad_simple("sink_%u")
        src_pad_1.link(self.sink_pad_1)

        

        # Deck 2 Links
        self.src2.link(decode2)
        decode2.connect("pad-added", self._on_pad_added, convert2)
        convert2.link(self.rate2)
        src_pad_2 = self.rate2.get_static_pad("src")
        self.sink_pad_2 = mixer.request_pad_simple("sink_%u")
        src_pad_2.link(self.sink_pad_2)

        # Output Links
        mixer.link(output_convert)
        output_convert.link(output_sink)

        # Add bus watch (CRITICAL for debugging/EOS)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        
        # Load initial files and set initial state
        if self.playlist:
            self._load_file_on_deck(1, self.playlist[0])
            if len(self.playlist) > 1:
                self._load_file_on_deck(2, self.playlist[1])
            else:
                self._load_file_on_deck(2, self.playlist[0])
        
        # Set to PAUSED initially, ready to play
        # self.pipeline.set_state(Gst.State.PLAYING)
        # print("Pipeline built and initialized to PLAYING.")
        self.pipeline.set_state(Gst.State.PAUSED)
        print("Pipeline built and initialized to PAUSED.")

        return False # Do not repeat the idle_add

    def _load_file_on_deck(self, deck_num: int, file_path: str):
        """
        Internal: Changes the file location by replacing filesrc and decodebin.
        (Runs on GLib thread). This is the "Element Swap" method.
        """
        print(f"--- LOAD_DECK {deck_num} (Element Swap): Starting load for {os.path.basename(file_path)}")
        if not self.pipeline:
            print("!!! Error: Pipeline is not yet initialized.")
            return False

        # 1. Define element names
        old_src_name = f"src{deck_num}"
        old_decode_name = f"decode{deck_num}"
        convert_name = f"convert{deck_num}"
        
        # 2. Get elements
        old_src = self.pipeline.get_by_name(old_src_name)
        old_decode = self.pipeline.get_by_name(old_decode_name)
        convert = self.pipeline.get_by_name(convert_name) # This is our link target
            
        if not all([old_src, old_decode, convert]) or not os.path.exists(file_path):
            print(f"!!! Error: Deck {deck_num} element(s) not found or file does not exist: {file_path}")
            return False
        
        # 3. Get current pipeline state and set to PAUSED (critical for a smooth swap)
        current_pipeline_state = self.pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.pipeline.set_state(Gst.State.PAUSED)

        # 4. Unlink the old decodebin from convert
        # This is the *only* link we need to manually break.
        print(f"--- LOAD_DECK {deck_num}: Unlinking {old_decode_name} from {convert_name}...")
        convert_sink_pad = convert.get_static_pad("sink")
        if convert_sink_pad.is_linked():
            old_decode_src_pad = convert_sink_pad.get_peer()
            print(f"--- LOAD_DECK {deck_num}: Unlinking {old_decode_src_pad.get_name()} from {convert_sink_pad.get_name()}")
            old_decode_src_pad.unlink(convert_sink_pad)

        # 5. Set old elements to NULL (this breaks all internal links)
        print(f"--- LOAD_DECK {deck_num}: Setting old elements to NULL...")
        old_src.set_state(Gst.State.NULL)
        old_decode.set_state(Gst.State.NULL)
        
        # 6. Remove from pipeline
        print(f"--- LOAD_DECK {deck_num}: Removing old elements...")
        self.pipeline.remove(old_src)
        self.pipeline.remove(old_decode)

        # 7. Create NEW Elements (Give them the same name)
        print(f"--- LOAD_DECK {deck_num}: Creating new elements...")
        new_src = Gst.ElementFactory.make("filesrc", old_src_name)
        new_decode = Gst.ElementFactory.make("decodebin", old_decode_name)
        
        new_src.set_property("location", file_path)

        # 8. Add to pipeline and link
        print(f"--- LOAD_DECK {deck_num}: Adding and linking new elements...")
        self.pipeline.add(new_src)
        self.pipeline.add(new_decode)

        new_src.link(new_decode)
        # CRITICAL: Reconnect the pad-added signal for the new decodebin!
        new_decode.connect("pad-added", self._on_pad_added, convert)

        # 9. Update self references (so we can remove them next time)
        if deck_num == 1:
            self.src1 = new_src
        else:
            self.src2 = new_src
        
        # 10. Set state on new elements (Sync to parent's state, which is PAUSED)
        print(f"--- LOAD_DECK {deck_num}: Syncing new element states...")
        new_src.sync_state_with_parent()
        new_decode.sync_state_with_parent()
        
        # 11. Restore the overall pipeline state (e.g., back to PLAYING)
        print(f"--- LOAD_DECK {deck_num}: Restoring pipeline state to {current_pipeline_state.value_nick.upper()}...")
        self.pipeline.set_state(current_pipeline_state)
        
        # 12. Send a seek *after* restoring state.
        # This flushes the whole pipeline and ensures the new track
        # is the one that starts playing from 0.
        print(f"--- LOAD_DECK {deck_num}: Sending FLUSH_SEEK to 0...")
        self.pipeline.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            0 # Seek to 0 time
        )
        
        print(f"Deck {deck_num} (Element Swap) load complete: {os.path.basename(file_path)}")
        return True
    
    
if __name__ == "__main__":
    import time
    SONGS = [
        os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3"),
        os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3"),
        # The new track to load in the middle of the test
        "/home/jenny/dj_downloads/cec27c3cd9_Olivia_Dean_Baby_Steps.mp3",
    ]
    
    # The dedicated track to be loaded in the test
    NEW_TRACK_DECK1 = SONGS[2]

    # Filter out non-existent files for safety (highly recommended)
    working_playlist = [s for s in SONGS if os.path.exists(s)]
    player = Player(working_playlist)

    # Give GStreamer a moment to builkkd the pipeline and set initial state (PAUSED)
    time.sleep(1.5) 

    try:
        print("\n--- TEST: 1. Initial Play (Deck 1) for 5 seconds ---")
        player.play_deck(1) # Sets Deck 1 volume to 1.0, Deck 2 to 0.0, starts pipeline.
        time.sleep(5) # Play for 10 seconds

        print("\n--- TEST: 2. Load NEW Track on Deck 1 ---")
        # Load the new song onto Deck 1. This must be a full file path.
        player.load_song_on_deck(1, NEW_TRACK_DECK1)
        # Give GStreamer a moment to process the load command on the GLib thread
        time.sleep(1) 
        
        print("\n--- TEST: 3. Start playing NEW Track on Deck 1 ---")
        # Since the new track was loaded on the current active deck (1), 
        # setting the pipeline to PLAYING again will start the new track from the beginning.
        # Alternatively, we could just re-call play_deck(1) which ensures volume is 1.0 and state is PLAYING.
        player.play_deck(1)
        time.sleep(10) # Play the new track for 5 seconds
        
        print("\n--- TEST: 4. Final Cleanup ---")

    except Exception as e:
        print(f"\nTest Script Error: {e}")
    finally:
        # Clean up the GStreamer player
        player.cleanup()