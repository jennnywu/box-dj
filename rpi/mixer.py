#!/usr/bin/env python3

import gi
import sys
import os
import tty
import termios

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

HOME_PATH = "/home/jenny/box-dj/"


current_rate_1 = 1.0
current_rate_2 = 1.0

def on_pad_added(element, pad, target_element):
    """
    This function is called when the 'decodebin' element (our 'element')
    has figured out the audio format and created a new output 'pad'.
    We must now link this new 'pad' to the 'sink' pad of our
    'target_element' (which is our audioconvert).
    """
    print(f"Pad added to {element.get_name()}, linking to {target_element.get_name()}")
    
    # Get the 'sink' pad of the target_element (e.g., convert1)
    sink_pad = target_element.get_static_pad("sink")
    
    # Check if it's already linked
    if sink_pad.is_linked():
        print(f"Sink pad on {target_element.get_name()} is already linked.")
        return

    try:
        pad.link(sink_pad)
        print(f"Successfully linked {element.get_name()} to {target_element.get_name()}")
    except Gst.LinkError:
        print(f"!!! FAILED to link {element.get_name()} to {target_element.get_name()} !!!")


def on_key_press(source_fd, condition, rate_elements):
    """
    This function is called by the GLib.MainLoop whenever
    a key is pressed on the keyboard (sys.stdin).
    'rate_elements' is a tuple containing (rate1, rate2)
    """
    global current_rate_1, current_rate_2
    
    rate1, rate2 = rate_elements
    
    char = sys.stdin.read(1)
    
    if char == 'k':
        current_rate_2 += 0.05
        print(f"Speed 2: {current_rate_2:.2f}")
        rate2.set_property("rate", current_rate_2)
    elif char == 'j':
        current_rate_2 -= 0.05
        if current_rate_2 < 0.05:
            current_rate_2 = 0.05
        print(f"Speed 2: {current_rate_2:.2f}")
        rate2.set_property("rate", current_rate_2)
        
    elif char == 'f':
        current_rate_1 += 0.05
        print(f"Speed 1: {current_rate_1:.2f}")
        rate1.set_property("rate", current_rate_1)
    elif char == 'd':
        current_rate_1 -= 0.05
        if current_rate_1 < 0.05:
            current_rate_1 = 0.05
        print(f"Speed 1: {current_rate_1:.2f}")
        rate1.set_property("rate", current_rate_1)
    
    return True

def main():
    file_path1 = os.path.join(HOME_PATH, "rpi/example-mp3/chappell-roan-red-wine-supernova.mp3")
    file_path2 = os.path.join(HOME_PATH, "rpi/example-mp3/charli-xcx-365.mp3")

    Gst.init(None)
    pipeline = Gst.Pipeline.new("dj-pipeline")

    # --- Deck 1 Elements ---
    src1 = Gst.ElementFactory.make("filesrc", "src1")
    src1.set_property("location", file_path1)
    decode1 = Gst.ElementFactory.make("decodebin", "decode1")
    convert1 = Gst.ElementFactory.make("audioconvert", "convert1")
    rate1 = Gst.ElementFactory.make("pitch", "rate1") 

    # --- Deck 2 Elements ---
    src2 = Gst.ElementFactory.make("filesrc", "src2")
    src2.set_property("location", file_path2)
    decode2 = Gst.ElementFactory.make("decodebin", "decode2")
    convert2 = Gst.ElementFactory.make("audioconvert", "convert2")
    rate2 = Gst.ElementFactory.make("pitch", "rate2")

    # --- The Mixer Element ---
    mixer = Gst.ElementFactory.make("audiomixer", "mixer")

    # --- The Output Elements ---
    output_convert = Gst.ElementFactory.make("audioconvert", "output_convert_main")
    output_sink = Gst.ElementFactory.make("pulsesink", "output_sink")

    if not all([pipeline, src1, decode1, convert1, rate1, src2, decode2, convert2, rate2, mixer, output_convert, output_sink]):
        print("!!! Not all elements could be created. Missing a plugin?")
        return

    pipeline.add(src1)
    pipeline.add(decode1)
    pipeline.add(convert1)
    pipeline.add(rate1)
    pipeline.add(src2)
    pipeline.add(decode2)
    pipeline.add(convert2)
    pipeline.add(rate2)
    pipeline.add(mixer)
    pipeline.add(output_convert)
    pipeline.add(output_sink)

    # Deck 1: src -> decode
    src1.link(decode1)
    # Deck 1: decode -> convert -> rate -> mixer
    decode1.connect("pad-added", on_pad_added, convert1)
    convert1.link(rate1)
    
    src_pad_1 = rate1.get_static_pad("src") 
    sink_pad_1 = mixer.get_request_pad("sink_%u")
    print(f"Got mixer pad: {sink_pad_1.get_name()}")
    src_pad_1.link(sink_pad_1) 


    # Deck 2: src -> decode
    src2.link(decode2)
    # Deck 2: decode -> convert -> rate -> mixer
    decode2.connect("pad-added", on_pad_added, convert2)
    convert2.link(rate2)

    src_pad_2 = rate2.get_static_pad("src")
    sink_pad_2 = mixer.get_request_pad("sink_%u")
    print(f"Got mixer pad: {sink_pad_2.get_name()}")
    src_pad_2.link(sink_pad_2)


    mixer.link(output_convert)
    output_convert.link(output_sink)

    print("Starting pipeline...")
    pipeline.set_state(Gst.State.PLAYING)

    loop = GLib.MainLoop()

    print("Pipeline is running. Press Ctrl+C to stop.")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    print("\nPipeline is running.")
    print("  Deck 1: 'd' (slow) / 'f' (fast)")
    print("  Deck 2: 'j' (slow) / 'k' (fast)")
    print("Press Ctrl+C to stop.\n")
    
    try:
        # Set terminal to "cbreak" mode (no waiting for 'Enter')
        tty.setcbreak(sys.stdin.fileno())
        
        GLib.io_add_watch(fd, GLib.IO_IN, on_key_press, (rate1, rate2))
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping pipeline...")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        pipeline.set_state(Gst.State.NULL)
        loop.quit()

if __name__ == "__main__":
    main()