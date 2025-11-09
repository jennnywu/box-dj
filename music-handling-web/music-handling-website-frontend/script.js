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
let playlists = {'deck1': [], 'deck2': []}; // These will be updated by the server
let dropdownTimeout = null;

let activeDeck = 'deck1'; 


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


function connect() {
    console.log("Attempting Socket.IO connection to", WEBSOCKET_ADDRESS);
    
    ws = io(WEBSOCKET_ADDRESS, {
        transports: ['websocket'],
        secure: true,
    });

    ws.on('connect', () => {
        updateStatus("Connected");
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
        updateStatus(data.message); // Update the status bar with the message
    });
    
    ws.on('playlist_update', (data) => {
        // Updated: The server now sends data.playlists
        console.log("Received new playlists from Pi:", data.playlists); 
        // Overwrite the local playlists dictionary
        playlists = data.playlists || {'deck1': [], 'deck2': []}; 
        buildPlaylists(); // Re-render both tables with the new data
        updateStatus("Playlists synced with Pi");
    });
}


// utility functions
function updateStatus(msg) {
    const statusElem = document.getElementById("status");
    if (statusElem) statusElem.textContent = "Status: " + msg;
    else console.warn("No #status element found in DOM");
}


function setActiveDeck(deckId) {
    if (deckId === 'deck1' || deckId === 'deck2') {
        activeDeck = deckId;
        console.log(`Active deck set to: ${activeDeck}`);
        // Optionally update a UI element to show which deck is active
        const deck1Btn = document.getElementById('deck1Btn');
        const deck2Btn = document.getElementById('deck2Btn');
        if (deck1Btn) deck1Btn.classList.toggle('active', deckId === 'deck1');
        if (deck2Btn) deck2Btn.classList.toggle('active', deckId === 'deck2');
        updateStatus(`Active song queue: ${deckId.toUpperCase()}`);
    }
}


function msToMinutes(ms) {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, "0")}`;
}


function buildPlaylists() {
    buildPlaylist('deck1', playlists.deck1 || []);
    buildPlaylist('deck2', playlists.deck2 || []);
}


function buildPlaylist(deckId, songsList) { 
    const tbody = document.querySelector(`#${deckId}Table tbody`); // Use ID for specific table
    if (!tbody) {
        console.error(`Could not find tbody for ${deckId}`);
        return;
    }
    tbody.innerHTML = "";

    let totalDuration = 0;
    songsList.forEach((song, i) => {
        totalDuration += song.duration_ms || 0;
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${i + 1}</td>
          <td class="song-title">${song.title}</td>
          <td>${song.artist}</td>
          <td>${song.album}</td>
          <td>${song.duration}</td>
          <td><button class="play-btn" onclick='selectSong(${i}, "${deckId}")'>▶</button></td>
        `;
        tbody.appendChild(row);
    });

    // Update stats for the specific deck
    const songCountElem = document.getElementById(`${deckId}SongCount`);
    const songLengthElem = document.getElementById(`${deckId}SongLength`);

    const totalSongs = songsList.length;
    const totalMins = Math.floor(totalDuration / 60000);
    const hours = Math.floor(totalMins / 60);
    const minutes = totalMins % 60;

    if (songCountElem && songLengthElem) {
        songCountElem.textContent = `${totalSongs} ${totalSongs === 1 ? "song · " : "songs · "}`;
        songLengthElem.textContent = hours > 0 ? `${hours} hr ${minutes} min` : `${minutes} min`;
    }
}


function updatePlayPauseButton(deckId, isPlaying) {
    const btnId = `playPauseBtn${deckId.slice(-1)}`; // 'deck1' -> 'playPauseBtn1'
    const btn = document.getElementById(btnId);
    if (btn) {
        btn.textContent = isPlaying ? "⏸" : "▶";
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
              <div class="search-result">
                <span class="song-info">${t.name} — ${t.artists.map(a => a.name).join(", ")}</span>
                <button onclick="addSongFromSearch('${t.name.replace(/'/g, "\\'")}', 
                                                    '${t.artists.map(a => a.name).join(", ").replace(/'/g, "\\'")}', 
                                                    '${t.album.name.replace(/'/g, "\\'")}', 
                                                    '${t.uri}', ${t.duration_ms}, 'deck1')">
                    Add D1
                </button>
                <button onclick="addSongFromSearch('${t.name.replace(/'/g, "\\'")}', 
                                                    '${t.artists.map(a => a.name).join(", ").replace(/'/g, "\\'")}', 
                                                    '${t.album.name.replace(/'/g, "\\'")}', 
                                                    '${t.uri}', ${t.duration_ms}, 'deck2')">
                    Add D2
                </button>
              </div>`).join("");
            resultsDiv.style.display = "block";
        } catch (err) {
            console.error("Spotify search error:", err);
            resultsDiv.style.display = "none";
        }
    }, 300);
}


// add song to playlist
function addSongFromSearch(title, artist, album, uri, duration_ms, deckId) { 
    const resultsDiv = document.getElementById("searchResults");
    resultsDiv.style.display = "none";
    
    const newSong = {
        title,
        artist,
        album,
        duration: msToMinutes(duration_ms),
        duration_ms,
        spotify_uri: uri,
        action: ACTION.ADD_SONG, 
        deck_id: deckId 
    };
    
    sendSong(newSong);
    
    updateStatus(`Requesting RPI to add "${title}" to ${deckId.toUpperCase()}`);
}


// playback control
function selectSong(i, deckId) { 
    const songsList = playlists[deckId];
    if (!songsList) return;
    
    const song = songsList[i];
    currentSong = song.title;
    isPlaying = true;
    
    document.getElementById("currentSong").textContent = `${deckId.toUpperCase()}: ${song.title}`; 
    document.getElementById("artistName").textContent = song.artist;

    const payload = {
        title: song.title,
        artist: song.artist,
        action: ACTION.PLAY_SONG,
        deck_id: deckId 
    };
    sendSong(payload);
}


function sendSong(songInfo) {
    console.log("sendSong() called with:", songInfo);

    if (!ws?.connected) {
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
    if (ws?.connected) ws.emit("message", text);
}


// play / pause toggle
function togglePlay(deckId) {
    // If we only track the play state of the selected song, we use currentSong.
    // However, for a DJ setup, we need to track if the DECK is playing.
    
    deckPlayState[deckId] = !deckPlayState[deckId];
    const isPlaying = deckPlayState[deckId];
    
    // 1. Update the button icon
    updatePlayPauseButton(deckId, isPlaying);

    // 2. Determine the command string
    const command = isPlaying ? `resume_${deckId}` : `pause_${deckId}`;
    
    // 3. Send the deck-specific command
    sendRaw(command);
}


// initialize app
document.addEventListener("DOMContentLoaded", async () => {
    console.log("Page loaded; initializing app...");
    try {
        await getTokenFromServer();
        await new Promise(res => setTimeout(res, 1000)); // small delay before connecting
        connect();
        
        // Initial setup for UI (e.g., setting deck1 as active)
        setActiveDeck('deck1'); 
        
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