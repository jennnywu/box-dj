import os
import json
import eventlet 
import eventlet.wsgi
import time
import requests
import base64
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS 
import logging

logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')

logging.getLogger('socketio').setLevel(logging.INFO)
logging.getLogger('engineio').setLevel(logging.INFO)

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)

load_dotenv()
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Missing Spotify credentials in .env file")

DOWNLOAD_DIR = "/home/jenny/box-dj/rpi/dj_downloads"
PORT = 8080 # This is the main port for both HTTP and Socket.IO
TOKEN_CACHE = {"access_token": None, "expires_at": 0}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# --- Flask and SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'SUPER_SECRET_KEY'

CORS(app, resources={r"/*": {"origins": "*"}}) 

socketio = SocketIO(app, cors_allowed_origins="*")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


# Master playlist (frontend can request for this)
PLAYLIST = []

def get_spotify_token():
    now = time.time()
    if TOKEN_CACHE["access_token"] and now < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["access_token"]

    app.logger.info("Requesting new Spotify access token...")
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}

    r = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()
    token_data = r.json()

    TOKEN_CACHE["access_token"] = token_data["access_token"]
    TOKEN_CACHE["expires_at"] = now + token_data["expires_in"] - 60
    print("Token acquired; expires in 1 hour")

    return TOKEN_CACHE["access_token"]

@app.route("/token")
def token_endpoint():
    """HTTP endpoint accessible at http://0.0.0.0:8080/token"""
    
    # 🚨 CHANGE: Use the application logger instead of print()
    app.logger.info("HIT TOKEN ENDPOINT...")
    print("PLEASE PRINT")
    
    token = get_spotify_token()
    
    # Log only parts of the token for security
    app.logger.info(f"TOKEN FOUND (first 10 chars): {token[:10]}...") 
    
    return jsonify({"access_token": token})

# --- Utility to Broadcast Playlist State ---
def broadcast_playlist_update(client_sid=None):
    """Sends the current state of the PLAYLIST to a specific client or all."""
    # Send the master song list to the requesting client (or all)
    # The FE will overwrite its local `songs` list with this data
    if client_sid:
        app.logger.info(f"Emitting PLAYLIST to specific client: {client_sid}")
        socketio.emit('playlist_update', {'songs': PLAYLIST}, to=client_sid)
    else:
        app.logger.info("Broadcasting PLAYLIST to all clients.")
        socketio.emit('playlist_update', {'songs': PLAYLIST}, broadcast=True)

def download_song(song_data: dict):
    """
    Downloads a song using yt-dlp in a background task.
    """
    title = song_data.get("title")
    artist = song_data.get("artist")
    
    # Send initial update to *all* clients
    socketio.emit('status_update', 
                  {'message': f'Download started: {artist} - {title}'},
                  broadcast=True) 
    
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{DOWNLOAD_DIR}/%(title)s.%(ext)s'"
    app.logger.info(f"Executing: {download_command}")
    
    # ⚠️ This is the blocking I/O call that is now safely in the background
    os.system(download_command) 
    
    app.logger.info(f"Download complete for: {artist} - {title}")
    
    # Send final update to *all* clients once the download finishes
    socketio.emit('status_update', 
                  {'message': f'Download complete: {artist} - {title}'}, 
                  broadcast=True)

# --- Standard Flask HTTP Route ---
@app.route('/test')
def index():
    """Simple route to confirm the HTTP server is running."""
    app.logger.info("HIT INDEX ENDPOINT...")
    print("PLEASE PRINT")
    return render_template_string(
        f"<h1>RPi Download Server Running</h1><p>Listening on port {PORT}. File storage at: {DOWNLOAD_DIR}</p>"
        "<p>Access Spotify Token at: /token</p>"
    )

# --- SocketIO Event Handlers ---

    
@socketio.on('connect')
def handle_connect():
    """Called when a new client establishes a Socket.IO connection."""
    app.logger.info(f"Client connected via Socket.IO. SID: {request.sid}")
    # immediately send client the current playlist
    broadcast_playlist_update(client_sid=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Called when a client disconnects."""
    print("Client disconnected")
    
      

@socketio.on('message')
def handle_json_message(data):
    """Handles generic messages sent by the client."""
    app.logger.info(f"< Received message: {data}")

    try:
        if isinstance(data, dict):
            action = data.get("action")
            song_data = {
                'title': data.get("title"),
                'artist': data.get("artist"),
                'album': data.get("album"),
                'duration': data.get("duration"),
                'duration_ms': data.get("duration_ms"),
            }
            
            if action == "ADD_SONG":
                # 1. Update the master state and broadcast immediately (NON-BLOCKING)
                PLAYLIST.append(song_data)
                broadcast_playlist_update() 
                
                # 2. Start the download process in a separate background thread/greenlet
                # This function returns immediately, letting the server handle other traffic.
                socketio.start_background_task(download_song, song_data)  
                
            elif action == "PLAY_SONG":
                app.logger.info(f"PLAY_SONG: {song_data.get('title')} - Not Implemented (But logic is here)")
                # TODO: actually play the song on the RPI
            elif data == "resume" or data == "pause":
                app.logger.info(f"Playback control: {data} - Not Implemented")

            else:
                app.logger.warning(f"Unknown action: {action}")
        else:
            app.logger.warning("Received non-dictionary data, ignoring.")

    except Exception as e:
        app.logger.error(f"!!! An error occurred processing the message: {e}")
        emit('error', {'message': f'Server error: {e}'})

# --- Main Execution ---
if __name__ == "__main__":
    print(f"Starting RPi DJ server at http://0.0.0.0:{PORT} (HTTP and Socket.IO enabled)")
    print(f"Saving files to {DOWNLOAD_DIR}")
    if 'eventlet' in globals():
        print("Using eventlet server.")
        eventlet.wsgi.server(
            eventlet.listen(('0.0.0.0', PORT)), 
            app
        )
    else:
        print("Using default Flask-SocketIO runner.")
        socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)