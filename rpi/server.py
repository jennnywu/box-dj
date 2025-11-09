import os
import json
import eventlet 
import eventlet.wsgi
import time
import requests
import base64
import hashlib
import atexit
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS 
import logging

from play_song import Player


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

# Use an absolute path for downloads on a Raspberry Pi
DOWNLOAD_DIR = "/home/jenny/dj_downloads"
PORT = 8080 
TOKEN_CACHE = {"access_token": None, "expires_at": 0}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ======== APPLICATION SETUP ======== #
app = Flask(__name__)
app.config['SECRET_KEY'] = 'SUPER_SECRET_KEY'

CORS(app, resources={r"/*": {"origins": "*"}}) 
socketio = SocketIO(app, cors_allowed_origins="*")

# Master playlists for Deck 1 and Deck 2
PLAYLISTS = {'deck1': [], 'deck2': []}
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# ======== PLAYER SETUP ======== #
player = Player()

# Graceful shutdown for the player
def stop_player():
    print("Shutting down player...")
    player.stop()
atexit.register(stop_player)


# ============ UTILS ============ #
def hash_uri(uri: str) -> str:
    """Generates a short, consistent hash from the Spotify URI for use as a unique ID."""
    return hashlib.sha1(uri.encode('utf-8')).hexdigest()[:10]


def find_song_by_id(song_id: str, deck_id: str) -> dict | None:
    """Finds a song by its ID in the specified deck's playlist."""
    target_playlist = PLAYLISTS.get(deck_id)
    if not target_playlist:
        return None
    for song in target_playlist:
        if song.get('id') == song_id:
            return song
    return None


def update_song_in_playlist(song_id: str, deck_id: str, update_data: dict):
    """Finds a song by ID in the specified deck's playlist and updates its fields."""
    
    song = find_song_by_id(song_id, deck_id)
    if song:
        app.logger.info(f"Updating song ID {song_id} in {deck_id} with data: {update_data.keys()}")
        song.update(update_data)
        return True
    
    app.logger.warning(f"Failed to find song with ID {song_id} in {deck_id} to update.")
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
    """Sends the current state of the PLAYLISTS dictionary to a specific client or all."""
    
    if client_sid:
        app.logger.info(f"Emitting PLAYLISTS to specific client: {client_sid}")
        socketio.emit('playlist_update', {'playlists': PLAYLISTS}, to=client_sid) 
    else:
        app.logger.info(f"Broadcasting PLAYLISTS to all clients. Total songs (D1+D2): {len(PLAYLISTS['deck1']) + len(PLAYLISTS['deck2'])}")
        socketio.emit('playlist_update', {'playlists': PLAYLISTS})


def download_song(song_data: dict, deck_id: str): 
    """
    Downloads a song using yt-dlp in a background task and updates the master playlist.
    """
    song_id = song_data.get('id')
    title = song_data.get("title")
    artist = song_data.get("artist")
    
    # Sanitize for filesystem
    safe_artist = artist.replace(' ', '_').replace('/', '_')
    safe_title = title.replace(' ', '_').replace('/', '_')
    
    filename_base = f"{song_id}_{safe_artist}_{safe_title}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{filename_base}.%(ext)s")
    final_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}.mp3")

    # Skip download if file already exists
    if os.path.exists(final_path):
        app.logger.info(f"Song '{title}' already downloaded. Skipping.")
        if update_song_in_playlist(song_id, deck_id, {'download_path': final_path}):
            broadcast_playlist_update()
        socketio.emit('status_update', {'message': f'Already downloaded: {artist} - {title}'})
        return

    socketio.emit('status_update', 
                  {'message': f'Download started for {deck_id}: {artist} - {title}'},
                  ) 
    
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{output_template}'"
    app.logger.info(f"Executing: {download_command}")
    
    os.system(download_command) 
    
    app.logger.info(f"Download complete for {deck_id}: {artist} - {title}. Expected path: {final_path}")
    
    if update_song_in_playlist(song_id, deck_id, {'download_path': final_path}): 
       broadcast_playlist_update() 

    socketio.emit('status_update', 
                  {'message': f'Download complete for {deck_id}: {artist} - {title}'}, 
                  )

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
        # Handle dictionary-based messages (for adding/playing songs)
        if isinstance(data, dict):
            action = data.get("action")
            deck_id = data.get("deck_id") 
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
                if not song_data['id'] or deck_id not in PLAYLISTS:
                    app.logger.error("Cannot add song: Missing Spotify URI or invalid deck_id.")
                    return
                
                PLAYLISTS[deck_id].append(song_data) 
                app.logger.info(f"Added song ID {song_data['id']} to master list for {deck_id}.")
                broadcast_playlist_update() 
                
                socketio.start_background_task(download_song, song_data, deck_id)

            elif action == "PLAY_SONG":
                title_to_play = data.get('title')
                app.logger.info(f"Received PLAY_SONG request for '{title_to_play}' on {deck_id}")
                
                # Find the song in the playlist
                song_to_play = next((s for s in PLAYLISTS[deck_id] if s['title'] == title_to_play), None)

                if song_to_play:
                    path = song_to_play.get('download_path')
                    if path and os.path.exists(path):
                        app.logger.info(f"--> Found song at path: '{path}'. Playing now.")
                        player.play_song(path)
                    else:
                        app.logger.warning(f"--> WARNING: Song '{title_to_play}' is not downloaded yet.")
                else:
                    app.logger.error(f"--> ERROR: Could not find song '{title_to_play}' in the playlist for {deck_id}.")

            else:
                app.logger.warning(f"Unknown action: {action}")

        # Handle simple string-based commands (for playback control)
        elif isinstance(data, str):
            if data.startswith('pause_'):
                app.logger.info(f"Pausing player")
                player.pause()
            elif data.startswith('resume_'):
                app.logger.info(f"Resuming player")
                player.resume()
            else:
                app.logger.warning(f"Unknown string command: {data}")

    except Exception as e:
        app.logger.error(f"!!! An error occurred processing the message: {e}", exc_info=True)
        emit('error', {'message': f'Server error: {e}'})


# ============ RUN SERVER ============ #
if __name__ == "__main__":
    app.logger.info(f"Starting RPi DJ server at http://0.0.0.0:{PORT} (HTTP and Socket.IO enabled)")
    app.logger.info(f"Saving files to {os.path.abspath(DOWNLOAD_DIR)}")
    
    # The new Player class starts its own loop, so we don't need to call it here.
    # mixer.run()
    
    if 'eventlet' in globals():
        app.logger.info("Using eventlet server.")
        eventlet.wsgi.server(
            eventlet.listen(('0.0.0.0', PORT)), 
            app
        )
    else:
        app.logger.info("Using default Flask-SocketIO runner.")
        socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)
