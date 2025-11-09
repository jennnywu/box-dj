import os
import json
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

DOWNLOAD_DIR = "/home/jenny/box-dj/rpi/dj_downloads"
PORT = 8080

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'SUPER_SECRET_KEY'
socketio = SocketIO(app, cors_allowed_origins="*")

def download_song(title: str, artist: str):
    # Requires yt-dlp to be installed on system: https://github.com/yt-dlp/yt-dlp
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{DOWNLOAD_DIR}/%(title)s.%(ext)s'"
    print(f"Executing: {download_command}")
    os.system(download_command)
    print(f"Download complete for: {artist} - {title}")
    emit('status_update', {'message': f'Download complete: {artist} - {title}'})
    return

# --- Standard Flask HTTP Route (Optional but Recommended) ---
@app.route('/')
def index():
    """Simple route to confirm the HTTP server is running."""
    return render_template_string(
        f"<h1>RPi Download Server Running</h1><p>Listening on port {PORT}. File storage at: {DOWNLOAD_DIR}</p>"
        "<p>Connect via Socket.IO for download commands.</p>"
    )

# --- SocketIO Event Handlers ---

@socketio.on('connect')
def handle_connect():
    """Called when a new client establishes a Socket.IO connection."""
    print("Client connected via Socket.IO")

@socketio.on('disconnect')
def handle_disconnect():
    """Called when a client disconnects."""
    print("Client disconnected")

@socketio.on('message')
def handle_json_message(data):
    """
    Handles generic messages sent by the client.
    In your original code, the entire message was a JSON string, which is mapped
    here to a generic 'message' event.
    """
    print(f"< Received message: {data}")

    try:
        # data is already the parsed JSON object if sent correctly by the client
        # as a JSON object, or a string/dict if sent via socket.send(data)

        # Assuming client sends a dict/JSON object directly:
        if isinstance(data, dict):
            action = data.get("action")
            
            if action == "ADD_SONG":
                # In a real app, use socketio.start_background_task here
                # to prevent the download from blocking the main server loop.
                # For this simple example, we call it directly:
                download_song(data.get("title"), data.get("artist"))
            
            elif action == "PLAY_SONG":
                print("PLAY_SONG: Not Implemented")
            
            else:
                print(f"Unknown action: {action}")
        else:
            print("Received non-dictionary data, ignoring.")

    except Exception as e:
        # Note: JSON parsing errors are often handled client-side by Socket.IO
        # if the message is sent as a structured object.
        print(f"!!! An error occurred processing the message: {e}")
        emit('error', {'message': f'Server error: {e}'})

# --- Main Execution ---
if __name__ == "__main__":
    print(f"Starting RPi download server at http://0.0.0.0:{PORT} (Socket.IO enabled)")
    print(f"Saving files to {DOWNLOAD_DIR}")
    # Use socketio.run instead of app.run
    # The allow_unsafe_werkzeug parameter is often necessary when running on non-localhost IPs
    socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)