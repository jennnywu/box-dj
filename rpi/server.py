import asyncio
import websockets
import json
import requests
import os

# --- Configuration ---
DOWNLOAD_DIR = "/home/jenny/rpi/dj_downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_song(url):
    """
    Downloads a song from a URL and saves it to the DOWNLOAD_DIR.
    """
    try:
        # Try to get a clean filename
        filename = url.split('/')[-1]
        if not filename:
            filename = f"downloaded_song_{hash(url)}.mp3"
        
        save_path = os.path.join(DOWNLOAD_DIR, filename)
        
        print(f"Downloading: {url}")
        r = requests.get(url, allow_redirects=True)
        r.raise_for_status() # Will stop if there's an HTTP error
        
        with open(save_path, 'wb') as f:
            f.write(r.content)
        print(f"Saved to: {save_path}")
        
    except requests.exceptions.RequestException as e:
        print(f"!!! Failed to download {url}: {e}")

async def handler(websocket):
    """
    Called when a new client connects (e.g., your laptop's browser).
    """
    print(f"Client connected: {websocket.remote_address}")
    print("ILKSDJKLFJSDKLJFKLSDJKLFKLSDJKLFJDSKLJFKLDSJ")
    async for message in websocket:
        print('MESSAGE')
        print(message)
    return True
    try:
        # Stay connected and listen for messages from this client
        async for message in websocket:
            print(f"< Received message: {message}")
            try:
                data = json.loads(message)
                
                # Check if the message is a new song notification
                if data.get("action") == "new_song" and data.get("url"):
                    download_song(data["url"])
                    
            except json.JSONDecodeError:
                print("!!! Received invalid JSON")
                
    except websockets.exceptions.ConnectionClosed:
        print(f"Client disconnected: {websocket.remote_address}")
    except Exception as e:
        print(f"An error occurred: {e}")

async def main():
    # Start the server on '0.0.0.0' which means "listen on all network interfaces"
    # This is CRITICAL so your laptop can find it.
    PORT = 8080 

    print(f"Starting RPi download server at ws://0.0.0.0:{PORT}")
    print(f"Saving files to {DOWNLOAD_DIR}")
    await websockets.serve(handler, "0.0.0.0", PORT)
    await asyncio.Future() # This keeps the server running forever

if __name__ == "__main__":
    asyncio.run(main())
