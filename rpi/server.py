import os
import json
import eventlet 
import eventlet.wsgi
import time
import requests
import base64
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string
from flask_socketio import SocketIO, emit
from flask_cors import CORS # Required for the token endpoint to work locally
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


# @app.route("/token")
# def token_endpoint():
#     """HTTP endpoint accessible at http://0.0.0.0:8080/token"""
#     print("GETTING TOKEN")
#     print("HIT TOKEN ENDPOINT...")
#     token = get_spotify_token()
#     print("TOKEN FOUND", token)
#     return jsonify({"access_token": token})

# --- Song Download Logic (Integrated) ---

def download_song(title: str, artist: str):
    """
    Downloads a song using yt-dlp.
    NOTE: Should be run in a background task in a production app.
    """
    download_command = f"yt-dlp -x --audio-format mp3 --no-playlist 'ytsearch:{artist} {title}' -o '{DOWNLOAD_DIR}/%(title)s.%(ext)s'"
    print(f"Executing: {download_command}")
    os.system(download_command)
    print(f"Download complete for: {artist} - {title}")
    emit('status_update', {'message': f'Download complete: {artist} - {title}'})
    return

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
    app.logger.info("Client connected via Socket.IO")
    print("Client connected via Socket.IO")

@socketio.on('disconnect')
def handle_disconnect():
    """Called when a client disconnects."""
    print("Client disconnected")

@socketio.on('message')
def handle_json_message(data):
    """Handles generic messages sent by the client."""
    print(f"< Received message: {data}")

    try:
        if isinstance(data, dict):
            action = data.get("action")
            
            if action == "ADD_SONG":
                # Calls the blocking function
                download_song(data.get("title"), data.get("artist"))
            
            elif action == "PLAY_SONG":
                print("PLAY_SONG: Not Implemented")
            
            else:
                print(f"Unknown action: {action}")
        else:
            print("Received non-dictionary data, ignoring.")

    except Exception as e:
        print(f"!!! An error occurred processing the message: {e}")
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