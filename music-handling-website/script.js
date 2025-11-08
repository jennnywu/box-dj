// CONFIG
const PI_IP = "172.20.10.2";   // replace with your Raspberry Pi IP
const PI_PORT = 12345;

let SPOTIFY_TOKEN = "";
let ws;
let isPlaying = false;
let currentSong = "";
let songs = [];
let dropdownTimeout = null;

// --- Fetch Spotify token from Flask server ---
async function getTokenFromServer() {
  try {
    console.log("Fetching Spotify token...");
    const res = await fetch("http://localhost:6060/token"); // match your Flask port
    const data = await res.json();
    SPOTIFY_TOKEN = data.access_token;
    console.log("Spotify token fetched successfully");
  } catch (err) {
    console.error("Failed to fetch Spotify token:", err);
  }
}

// --- Connect to Raspberry Pi WebSocket ---
function connect() {
  console.log("Attempting WebSocket connection to", `ws://${PI_IP}:${PI_PORT}`);
  ws = new WebSocket(`ws://${PI_IP}:${PI_PORT}`);

  ws.onopen = () => {
    updateStatus("Connected");
    console.log("WebSocket connected");
  };

  ws.onclose = () => {
    updateStatus("Disconnected");
    console.warn("WebSocket disconnected. Reconnecting in 5 seconds...");
    setTimeout(connect, 5000); // auto-reconnect
  };

  ws.onerror = (e) => {
    console.error("WebSocket error:", e.message);
    updateStatus("Error: " + e.message);
  };

  ws.onmessage = (e) => {
    console.log("Message from Pi:", e.data);
  };
}

// --- Utility functions ---
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

// --- Build playlist table ---
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

// --- Spotify live search ---
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

// --- Add song to playlist ---
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
}

// --- Playback control ---
function selectSong(i) {
  const song = songs[i];
  currentSong = song.title;
  isPlaying = true;
  document.getElementById("currentSong").textContent = song.title;
  document.getElementById("artistName").textContent = song.artist;

  const payload = {
    command: "play_track",
    title: song.title,
    artist: song.artist,
    spotify_uri: song.spotify_uri,
  };
  sendSong(payload);
}

// --- Send JSON payload to Pi ---
function sendSong(songInfo) {
  console.log("sendSong() called with:", songInfo);

  if (!ws) {
    console.warn("No WebSocket instance found");
    updateStatus("Not connected to Pi");
    return;
  }

  if (ws.readyState === WebSocket.CONNECTING) {
    console.log("WebSocket still connecting, delaying send...");
    setTimeout(() => sendSong(songInfo), 500);
    return;
  }

  if (ws.readyState === WebSocket.OPEN) {
    console.log("Sending to Pi:", songInfo);
    ws.send(JSON.stringify(songInfo));
    updateStatus(`Sent "${songInfo.title}" to Pi`);
  } else {
    console.warn("WebSocket not open; state:", ws.readyState);
    updateStatus("Not connected to Pi");
  }
}

// --- Raw message helper ---
function sendRaw(text) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(text);
}

// --- Play / Pause toggle ---
function togglePlay() {
  if (!currentSong) return;
  isPlaying = !isPlaying;
  document.getElementById("playPauseBtn").textContent = isPlaying ? "⏸" : "▶";
  sendRaw(isPlaying ? "resume" : "pause");
}

// --- Initialize app ---
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