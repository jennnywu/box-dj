from flask import Flask, jsonify
from flask_cors import CORS
import requests, base64, os, time
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Missing Spotify credentials in .env file")

TOKEN_CACHE = {"access_token": None, "expires_at": 0}

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # allow all origins for local dev

def get_spotify_token():
    now = time.time()
    if TOKEN_CACHE["access_token"] and now < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["access_token"]

    print("Requesting new Spotify access token...")
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}

    r = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    r.raise_for_status()
    token_data = r.json()

    TOKEN_CACHE["access_token"] = token_data["access_token"]
    TOKEN_CACHE["expires_at"] = now + token_data["expires_in"] - 60
    print("Token acquired; expires in 1 hour")

    return TOKEN_CACHE["access_token"]

@app.route("/token")
def token_endpoint():
    token = get_spotify_token()
    return jsonify({"access_token": token})

if __name__ == "__main__":
    print("Spotify token server running on http://0.0.0.0:6060/token")
    app.run(host="0.0.0.0", port=6060)