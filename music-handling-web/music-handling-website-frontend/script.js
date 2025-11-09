// configuration
const PI_IP = "172.20.10.8";
const PI_PORT = 8080;
const USE_FORWARDER = true; // Use ngrok to forward or not

const DOMAIN = USE_FORWARDER ? "5cb7be3d6edf.ngrok-free.app" : `${PI_IP}:${PI_PORT}`;
const BASE_URL = USE_FORWARDER ? `https://${DOMAIN}` : `http://${DOMAIN}`;
const WEBSOCKET_ADDRESS = USE_FORWARDER ? `wss://${DOMAIN}` : `ws://${DOMAIN}`; // Socket.IO uses the BASE_URL

const ACTION = {
    PLAY_SONG: "PLAY_SONG",
    ADD_SONG: "ADD_SONG",
}

let SPOTIFY_TOKEN = "";
let ws;
let isPlaying = false;
let currentSong = "";
let songs = [];
let dropdownTimeout = null;

// fetch spotify token from flask server 
async function getTokenFromServer() {
    try {
        console.log("Fetching Spotify token from:", `${BASE_URL}/token`);
        const res = await fetch(`${BASE_URL}/token`, {
          method: 'GET',
          headers: {
            // Add this header to tell ngrok to skip the warning page
            "ngrok-skip-browser-warning": "any-value" 
        }});
        const data = await res.json();
        SPOTIFY_TOKEN = data.access_token;
        console.log("Spotify token fetched successfully");
    } catch (err) {
        console.error("Failed to fetch Spotify token:", err);
    }
}

// connect to rpi websocket
function connect() {
    console.log("Attempting Socket.IO connection to", WEBSOCKET_ADDRESS);
    
    // The previous explicit options for `secure: true` are often still necessary
    // when tunneling through ngrok to ensure the WSS protocol is attempted.
    ws = io(WEBSOCKET_ADDRESS.replace("https://", "wss://"), {
        transports: ['websocket'],
        secure: true,
    });

    // ... (rest of the connection handlers remain the same) ...
    ws.on('connect', () => {
        updateStatus("Connected");
        // FIX: The `socket` object is undefined here, use the `ws` object defined globally
        console.log("Socket.IO connected. ID:", ws.id); 
    });

    ws.on('disconnect', () => {
        updateStatus("Disconnected");
        console.warn("Socket.IO disconnected.");
    });
    
    ws.on('connect_error', (error) => {
        console.error("Socket.IO connection error:", error.message);
        updateStatus("Error: " + error.message);
    });

    ws.on('message', (data) => {
        console.log("Message from Pi:", data);
    });

    ws.on('status_update', (data) => {
        console.log("Download Status:", data.message);
    });
}

// utility functions
function updateStatus(msg) {
    const statusElem = document.getElementById("status");
    if (statusElem) statusElem.textContent = "Status: " + msg;
    else console.warn("No #status element found in DOM");
}

function msToMinutes(ms) {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, "0")}`;
}

// build playlist table
function buildPlaylist() {
    const tbody = document.querySelector("#playlist tbody");
    tbody.innerHTML = "";

    let totalDuration = 0;
    songs.forEach((song, i) => {
        totalDuration += song.duration_ms || 0;
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${i + 1}</td>
          <td class="song-title">${song.title}</td>
          <td>${song.artist}</td>
          <td>${song.album}</td>
          <td>${song.duration}</td>
          <td><button class="play-btn" onclick='selectSong(${i})'>▶</button></td>
        `;
        tbody.appendChild(row);
    });

    const songCountElem = document.getElementById("songCount");
    const songLengthElem = document.getElementById("songLength");

    const totalSongs = songs.length;
    const totalMins = Math.floor(totalDuration / 60000);
    const hours = Math.floor(totalMins / 60);
    const minutes = totalMins % 60;

    if (songCountElem && songLengthElem) {
        songCountElem.textContent = `${totalSongs} ${totalSongs === 1 ? "song · " : "songs · "}`;
        songLengthElem.textContent = hours > 0 ? `${hours} hr ${minutes} min` : `${minutes} min`;
    }
}

async function liveSpotifySearch() {
    const input = document.getElementById("songSearch");
    const q = input.value.trim();
    const resultsDiv = document.getElementById("searchResults");

    if (!q) {
        resultsDiv.style.display = "none";
        return;
    }

    clearTimeout(dropdownTimeout);
    dropdownTimeout = setTimeout(async () => {
        try {
            const res = await fetch(
                // `https://api.spotify.com/v1/search?q=$${encodeURIComponent(q)}&type=track&limit=5`,
                `https://api.spotify.com/v1/search?q=${encodeURIComponent(q)}&type=track&limit=5`,
                { headers: { Authorization: `Bearer ${SPOTIFY_TOKEN}` } }
            );
            console.log("Spotify search response status:", res.status);
            const data = await res.json();
            const tracks = data.tracks?.items || [];
            if (!tracks.length) {
                resultsDiv.style.display = "none";
                return;
            }

            resultsDiv.innerHTML = tracks.map(t => `
              <div class="search-result"
                  onclick="addSongFromSearch('${t.name.replace(/'/g, "\\'")}',
                                            '${t.artists.map(a => a.name).join(", ").replace(/'/g, "\\'")}',
                                            '${t.album.name.replace(/'/g, "\\'")}',
                                            '${t.uri}', ${t.duration_ms})">
                ${t.name} — ${t.artists.map(a => a.name).join(", ")}
              </div>`).join("");
            resultsDiv.style.display = "block";
        } catch (err) {
            console.error("Spotify search error:", err);
            resultsDiv.style.display = "none";
        }
    }, 300);
}

// add song to playlist
function addSongFromSearch(title, artist, album, uri, duration_ms) {
    const resultsDiv = document.getElementById("searchResults");
    resultsDiv.style.display = "none";
    const newSong = {
        title,
        artist,
        album,
        duration: msToMinutes(duration_ms),
        duration_ms,
        spotify_uri: uri,
    };
    songs.push(newSong);
    buildPlaylist();
    updateStatus(`Added "${title}" from Spotify`);

    const payload = {
        title: title,
        artist: artist,
        action: ACTION.ADD_SONG 
    };
    sendSong(payload);
}

// playback control
function selectSong(i) {
    const song = songs[i];
    currentSong = song.title;
    isPlaying = true;
    document.getElementById("currentSong").textContent = song.title;
    document.getElementById("artistName").textContent = song.artist;

    const payload = {
        title: song.title,
        artist: song.artist,
        action: ACTION.PLAY_SONG
    };
    sendSong(payload);
}

function sendSong(songInfo) {
    console.log("sendSong() called with:", songInfo);

    if (!ws || !ws.connected) {
        console.warn("Socket.IO not connected; skipping send.");
        updateStatus("Not connected to Pi");
        return;
    }

    // This section is now clean Socket.IO logic
    console.log("Sending to Pi:", songInfo);
    ws.emit('message', songInfo); 
    updateStatus(`Sent "${songInfo.title}" to Pi`);
}

// raw message helper
function sendRaw(text) {
    if (ws && ws.connected) ws.emit("message", text);
}

// play / pause toggle
function togglePlay() {
    if (!currentSong) return;
    isPlaying = !isPlaying;
    document.getElementById("playPauseBtn").textContent = isPlaying ? "⏸" : "▶";
    sendRaw(isPlaying ? "resume" : "pause");
}

// initialize app
document.addEventListener("DOMContentLoaded", async () => {
    console.log("Page loaded; initializing app...");
    try {
        await getTokenFromServer();
        await new Promise(res => setTimeout(res, 1000)); // small delay before connecting
        connect();
        const searchInput = document.getElementById("songSearch");
        if (searchInput) {
            searchInput.addEventListener("input", liveSpotifySearch);
            console.log("Search bar ready");
        } else {
            console.warn("No search input element found");
        }
    } catch (err) {
        console.error("Initialization failed:", err);
    }
});