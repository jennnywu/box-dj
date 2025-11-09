import os
import json
import eventlet 
import eventlet.wsgi
import time
import requests
import base64
import hashlib
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS 
import logging


# ============ LOGGING ============ #
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')

logging.getLogger('socketio').setLevel(logging.INFO)
logging.getLogger('engineio').setLevel(logging.INFO)

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)


# ============= CONFIG ============= #
load_dotenv()
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Missing Spotify credentials in .env file")

DOWNLOAD_DIR = "/home/jenny/box-dj/rpi/dj_downloads"
PORT = 8080 # This is the main port for both HTTP and Socket.IO
TOKEN_CACHE = {"access_token": None, "expires_at": 0}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ======== APPLICATION SETUP ======== #
app = Flask(__name__)
app.config['SECRET_KEY'] = 'SUPER_SECRET_KEY'

CORS(app, resources={r"/*": {"origins": "*"}}) 
socketio = SocketIO(app, cors_allowed_origins="*")

# Master playlist (frontend can request for this)
PLAYLIST = []
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


# ============ UTILS ============ #
def hash_uri(uri: str) -> str:
    """Generates a short, consistent hash from the Spotify URI for use as a unique ID."""
    return hashlib.sha1(uri.encode('utf-8')).hexdigest()[:10]


def update_song_in_playlist(song_id: str, update_data: dict):
    """Finds a song by ID in the master PLAYLIST and updates its fields."""
    for song in PLAYLIST:
        if song.get('id') == song_id:
            app.logger.info(f"Updating song ID {song_id} with data: {update_data.keys()}")
            song.update(update_data)
            return True
    app.logger.warning(f"Failed to find song with ID {song_id} to update.")
    return False


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
    app.logger.info("Token acquired; expires in 1 hour")

    return TOKEN_CACHE["access_token"]


# ========= HTTP ENDPOINTS ========= #
@app.route("/token")
def token_endpoint():
    """HTTP endpoint accessible at http://0.0.0.0:8080/token"""
    token = get_spotify_token()
    return jsonify({"access_token": token})


def broadcast_playlist_update(client_sid=None):
    """Sends the current state of the PLAYLIST to a specific client or all."""
    # Send the master song list to the requesting client (or all)
    if client_sid:
        app.logger.info(f"Emitting PLAYLIST to specific client: {client_sid}")
        socketio.emit('playlist_update', {'songs': PLAYLIST}, to=client_sid)
    else:
        app.logger.info(f"Broadcasting PLAYLIST to all clients. Total songs: {len(PLAYLIST)}")
        socketio.emit('playlist_update', {'songs': PLAYLIST}, broadcast=True)


def download_song(song_data: dict):
    """
    Downloads a song using yt-dlp in a background task and updates the master playlist.
    """
    song_id = song_data.get('id')
    title = song_data.get("title")
    artist = song_data.get("artist")
    
    filename_base = f"{song_id}_{artist.replace(' ', '_')}_{title.replace(' ', '_')}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{filename_base}.%(ext)s")
    
    socketio.emit('status_update', 
                  {'message': f'Download started: {artist} - {title}'},
                  broadcast=True) 
    
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{output_template}'"
    app.logger.info(f"Executing: {download_command}")
    
    os.system(download_command) 
    
    final_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}.mp3")

    app.logger.info(f"Download complete for: {artist} - {title}. Expected path: {final_path}")
    
    if update_song_in_playlist(song_id, {'download_path': final_path}):
       broadcast_playlist_update() 

    socketio.emit('status_update', 
                  {'message': f'Download complete: {artist} - {title}'}, 
                  broadcast=True)


# ========= SOCKET.IO EVENTS ========= #
@socketio.on('connect')
def handle_connect():
    """Called when a new client establishes a Socket.IO connection."""
    app.logger.info(f"Client connected via Socket.IO. SID: {request.sid}")
    broadcast_playlist_update(client_sid=request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    """Called when a client disconnects."""
    app.logger.info("Client disconnected")
    
    
@socketio.on('message')
def handle_json_message(data):
    """Handles generic messages sent by the client."""
    app.logger.info(f"< Received message: {data}")

    try:
        if isinstance(data, dict):
            action = data.get("action")
            
            spotify_uri = data.get("spotify_uri")
            
            song_data = {
                'id': hash_uri(spotify_uri) if spotify_uri else None, 
                'title': data.get("title"),
                'artist': data.get("artist"),
                'album': data.get("album"),
                'duration': data.get("duration"),
                'duration_ms': data.get("duration_ms"),
                'download_path': None 
            }
            
            if action == "ADD_SONG":
                if not song_data['id']:
                    app.logger.error("Cannot add song without a Spotify URI.")
                    return
                
                PLAYLIST.append(song_data)
                app.logger.info(f"Added song ID {song_data['id']} to master list.")
                broadcast_playlist_update() 
                
                socketio.start_background_task(download_song, song_data)
                
            elif action == "PLAY_SONG":
                app.logger.info(f"PLAY_SONG request for song ID: {song_data.get('id')}")
                
            elif data == "resume" or data == "pause":
                app.logger.info(f"Playback control: {data} - Not Implemented")

            else:
                app.logger.warning(f"Unknown action: {action}")
        else:
            app.logger.warning("Received non-dictionary data, ignoring.")

    except Exception as e:
        app.logger.error(f"!!! An error occurred processing the message: {e}")
        emit('error', {'message': f'Server error: {e}'})


# ============ RUN SERVER ============ #
if __name__ == "__main__":
    app.logger.info(f"Starting RPi DJ server at http://0.0.0.0:{PORT} (HTTP and Socket.IO enabled)")
    app.logger.info(f"Saving files to {DOWNLOAD_DIR}")
    if 'eventlet' in globals():
        app.logger.info("Using eventlet server.")
        eventlet.wsgi.server(
            eventlet.listen(('0.0.0.0', PORT)), 
            app
        )
    else:
        app.logger.info("Using default Flask-SocketIO runner.")
        socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)