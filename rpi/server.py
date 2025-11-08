import asyncio
import websockets
import json
import requests
import os

DOWNLOAD_DIR = "/home/jenny/box-dj/rpi/dj_downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_song(title: str, artist: str):
    """
    Downloads a song from a URL and saves it to the DOWNLOAD_DIR.
    """
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{DOWNLOAD_DIR}/%(title)s.%(ext)s'"
    os.system(download_command)
    return

async def handler(websocket):
    """
    Called when a new client connects (e.g., your laptop's browser).
    """
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            print(f"< Received message: {message}")
            try:
                data = json.loads(message)
                match data.get("action"):
                    case "ADD_SONG":
                        download_song(data.get("artist"), data.get("title"))
                    case "PLAY_SONG":
                        print("Not Implemented")
                    
            except json.JSONDecodeError:
                print("!!! Received invalid JSON")
                
    except websockets.exceptions.ConnectionClosed:
        print(f"Client disconnected: {websocket.remote_address}")
    except Exception as e:
        print(f"An error occurred: {e}")

async def main():
    PORT = 8080 

    print(f"Starting RPi download server at ws://0.0.0.0:{PORT}")
    print(f"Saving files to {DOWNLOAD_DIR}")
    await websockets.serve(handler, "0.0.0.0", PORT)
    await asyncio.Future() 

if __name__ == "__main__":
    asyncio.run(main())
