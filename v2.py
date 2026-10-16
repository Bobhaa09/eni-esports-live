from flask import Flask, request, jsonify, render_template_string
import json
import os
import time
from threading import Lock
from werkzeug.utils import secure_filename

app = Flask(__name__)
file_lock = Lock()

DATA_FILE = "teams.json"
CONFIG_FILE = "config.json"
UPLOAD_FOLDER = "static/logos"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

PLACEMENT = {1: 10, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1, 8: 1}

def placement_points(position):
    try: return PLACEMENT.get(int(position), 0)
    except (ValueError, TypeError): return 0

def calculate_points(team):
    kills = max(0, int(team.get("kills", 0)))
    place = placement_points(team.get("position", 0))
    return kills, place, (kills + place)

def recalculate_all(teams):
    for team in teams:
        k, p, tot = calculate_points(team)
        team["kills"] = k
        team["placement_points"] = p
        team["points"] = tot
    return teams

def save(teams):
    recalculate_all(teams)
    with file_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(teams, f, indent=2)

def load():
    if not os.path.exists(DATA_FILE): return []
    with file_lock:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return recalculate_all(json.load(f))
        except Exception: return []

def load_config():
    default_cfg = {"tournament": "ENI ESPORTS CHAMPIONSHIP", "match": "MATCH 1", "map": "ERANGEL"}
    if not os.path.exists(CONFIG_FILE): return default_cfg
    with file_lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**default_cfg, **json.load(f)}
        except Exception: return default_cfg

def save_config(config):
    with file_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

# =========================================================
# PREMIUM ADMIN PAGE (MOBILE OPTIMIZED & ZERO LAG)
# =========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>ENI PRODUCTION | ESPORTS DASHBOARD</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Teko:wght@500;600;700&family=Rajdhani:wght@500;600;700;800&display=swap');

:root {
    --bg-main: #050914;
    --card-bg: rgba(13, 22, 38, 0.65);
    --gold: #f2c400;
    --cyan: #00e5ff;
    --red: #ff2a55;
    --green: #00ff66;
    --glass-border: rgba(255,255,255,0.08);
}

* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    margin: 0; padding: 0;
    background: radial-gradient(circle at top, #0a1122 0%, var(--bg-main) 100%);
    color: #ffffff;
    font-family: 'Rajdhani', sans-serif;
    min-height: 100vh;
    padding-bottom: 80px;
}

/* STICKY HEADER FOR MOBILE */
.sticky-header {
    position: sticky;
    top: 0;
    z-index: 1000;
    background: rgba(5, 9, 20, 0.85);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--glass-border);
    padding: 12px 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}

.brand h1 {
    margin: 0; font-size: 26px;
    font-family: 'Teko', sans-serif;
    color: var(--gold);
    letter-spacing: 1.5px;
    text-shadow: 0 0 10px rgba(242,196,0,0.4);
    line-height: 1;
}
.brand span { font-size: 11px; color: var(--cyan); font-weight: 700; letter-spacing: 2px; }

.live-stats { display: flex; gap: 8px; }
.stat-badge {
    background: rgba(0, 229, 255, 0.1);
    border: 1px solid rgba(0, 229, 255, 0.3);
    padding: 4px 10px;
    border-radius: 6px;
    display: flex; flex-direction: column; align-items: center;
    min-width: 60px;
}
.stat-badge span { font-size: 9px; color: #9da9b8; font-weight: 700; text-transform: uppercase; }
.stat-badge strong { font-size: 16px; color: var(--cyan); font-weight: 800; line-height: 1.1; }
.stat-badge.players strong { color: var(--green); }
.stat-badge.players { background: rgba(0, 255, 102, 0.1); border-color: rgba(0, 255, 102, 0.3); }

.container { padding: 15px; max-width: 1400px; margin: 0 auto; }

/* GLASSMORPHISM CARDS */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid var(--glass-border);
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 15px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.links-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px;
}
.obs-link {
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--glass-border);
    padding: 10px; border-radius: 8px;
    text-align: center; text-decoration: none;
    color: #b0c4de; font-size: 12px; font-weight: 700;
    transition: 0.2s;
}
.obs-link:hover { background: rgba(0,229,255,0.15); border-color: var(--cyan); color: white; }

input, select, textarea {
    background: rgba(0,0,0,0.4);
    color: white; border: 1px solid rgba(255,255,255,0.15);
    padding: 12px; border-radius: 8px;
    font-size: 14px; font-family: 'Rajdhani', sans-serif; font-weight: 700;
    width: 100%; outline: none; transition: 0.2s;
}
input:focus, select:focus, textarea:focus { border-color: var(--cyan); box-shadow: 0 0 10px rgba(0,229,255,0.2); }

.btn {
    border: none; border-radius: 8px;
    padding: 12px 15px; cursor: pointer;
    font-weight: 800; font-size: 14px; font-family: 'Rajdhani', sans-serif;
    letter-spacing: 1px; text-transform: uppercase;
    transition: transform 0.1s, filter 0.2s;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
}
.btn:active { transform: scale(0.95); }
.btn-primary { background: linear-gradient(135deg, #00bfff, #0077b6); color: #fff; }
.btn-gold { background: linear-gradient(135deg, var(--gold), #c89d00); color: #040911; }
.btn-green { background: linear-gradient(135deg, var(--green), #00994d); color: #040911; }
.btn-danger { background: linear-gradient(135deg, var(--red), #8a0014); color: white; }

.search-bar { border-color: var(--gold) !important; font-size:16px; margin-bottom: 15px; }

/* TEAM CARDS - ESPORTS STYLE */
.teams-grid {
    display: grid; grid-template-columns: 1fr; gap: 15px;
}
@media(min-width: 768px) { .teams-grid { grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); } }

.team-card {
    background: linear-gradient(160deg, rgba(16,28,48,0.9), rgba(6,12,24,0.95));
    border: 1px solid var(--glass-border);
    border-left: 4px solid var(--cyan);
    border-radius: 10px;
    padding: 14px;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    position: relative;
    overflow: hidden;
}
.team-card.eliminated {
    border-left-color: var(--red);
    background: linear-gradient(160deg, rgba(30,12,18,0.85), rgba(10,5,8,0.95));
    opacity: 0.85;
}

.tc-header { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.tc-slot {
    background: rgba(255,255,255,0.08); padding: 4px 8px;
    border-radius: 4px; font-weight: 800; color: #9da9b8; font-size: 12px;
}
.tc-name { flex: 1; border: none; background: transparent; padding: 0; font-size: 18px; color: var(--gold); text-transform: uppercase; }
.tc-name:focus { border: none; box-shadow: none; border-bottom: 1px solid var(--gold); border-radius: 0; }
.btn-elim { background: rgba(255, 42, 85, 0.15); border: 1px solid var(--red); color: var(--red); padding: 6px 12px; }

.tc-players {
    display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px;
    background: rgba(0,0,0,0.25); padding: 8px; border-radius: 8px;
}
.player-node {
    flex: 1; height: 42px; border-radius: 6px;
    background: linear-gradient(135deg, var(--green), #00b347);
    display: flex; align-items: center; justify-content: center;
    color: #000; font-weight: 800; font-size: 15px; cursor: pointer;
    box-shadow: 0 0 10px rgba(0,255,102,0.2);
    transition: 0.2s; border: 1px solid rgba(255,255,255,0.4);
}
.player-node.dead {
    background: rgba(255,255,255,0.05); color: #5a6678;
    border-color: rgba(255,255,255,0.1); box-shadow: none;
}

.tc-controls { display: flex; gap: 8px; margin-bottom: 12px; align-items:center; }
.tc-controls select { padding: 10px 6px; font-size: 13px; }
.btn-icon {
    width: 44px; height: 44px; padding: 0; display: flex; align-items: center; justify-content: center;
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: white; font-size: 20px;
}
.btn-icon.plus { background: rgba(0, 255, 102, 0.15); border-color: rgba(0, 255, 102, 0.3); color: var(--green); }

.tc-stats {
    display: flex; justify-content: space-between;
    background: rgba(0,0,0,0.4); border-radius: 8px; padding: 8px 15px;
    border: 1px solid rgba(255,255,255,0.05);
}
.tc-stat-box { text-align: center; }
.tc-stat-box span { display: block; font-size: 10px; color: #7a8a9e; font-weight: 700; text-transform: uppercase; }
.tc-stat-box strong { font-size: 18px; font-weight: 800; }
.tc-stat-box.fin strong { color: var(--green); }
.tc-stat-box.pts strong { color: var(--cyan); }
.tc-stat-box.tot strong { color: var(--gold); font-size: 20px; }

/* LOGO UPLOAD AREA */
.logo-row {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    font-size: 11px; background: rgba(255,255,255,0.03); padding: 6px; border-radius: 6px; margin-top: 10px;
}
.logo-row img { width: 24px; height: 24px; object-fit: contain; border-radius: 4px; }
.logo-row input[type="file"] { padding: 4px; font-size: 10px; border:none; background:transparent; }

.toast {
    position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(20px);
    background: var(--gold); color: #000; padding: 12px 24px; border-radius: 30px;
    font-weight: 800; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;
    box-shadow: 0 10px 30px rgba(242, 196, 0, 0.4); opacity: 0; visibility: hidden;
    transition: all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55); z-index: 9999;
}
.toast.show { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>

<div class="sticky-header">
    <div class="brand">
        <h1>ENI PRO</h1>
        <span>LIVE BROADCAST</span>
    </div>
    <div class="live-stats">
        <div class="stat-badge"><span>Teams</span><strong id="topTeams">0</strong></div>
        <div class="stat-badge players"><span>Players</span><strong id="topPlayers">0</strong></div>
    </div>
</div>

<div class="container">
    <div class="glass-card">
        <div class="links-grid">
            <a href="/overlay/pt" target="_blank" class="obs-link">📊 POINTS TABLE</a>
            <a href="/overlay/elimination" target="_blank" class="obs-link">💀 ELIMINATION</a>
            <a href="/overlay/match" target="_blank" class="obs-link">🗺️ MATCH INFO</a>
            <a href="/overlay/standings" target="_blank" class="obs-link">🏆 STANDINGS</a>
        </div>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px,1fr)); gap:15px; margin-bottom:15px;">
        <div class="glass-card" style="margin:0;">
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div style="flex:1"><label style="font-size:11px; color:var(--gold); font-weight:700;">TOURNAMENT</label>
                <input id="tourneyName" type="text" value="ENI ESPORTS"></div>
                <div style="width:100px"><label style="font-size:11px; color:var(--gold); font-weight:700;">MATCH</label>
                <input id="matchName" type="text" value="MATCH 1"></div>
            </div>
            <div style="margin-bottom:10px;">
                <label style="font-size:11px; color:var(--gold); font-weight:700;">MAP</label>
                <select id="mapName">
                    <option>ERANGEL</option><option>MIRAMAR</option><option>RONDO</option>
                </select>
            </div>
            <button class="btn btn-gold" style="width:100%" onclick="updateConfig()">SAVE MATCH INFO</button>
        </div>

        <div class="glass-card" style="margin:0;">
            <label style="font-size:12px; font-weight:800; color:var(--cyan); margin-bottom:5px; display:block;">📋 DISCORD SLOT LIST</label>
            <textarea id="slotInput" style="height:85px; margin-bottom:10px;" placeholder="Paste Discord slots here..."></textarea>
            <button class="btn btn-primary" style="width:100%" onclick="importSlots()">IMPORT TEAMS</button>
        </div>
    </div>

    <div class="glass-card" style="display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between;">
        <div style="display:flex; gap:10px; flex:1; min-width:280px;">
            <button class="btn btn-green" style="flex:1;" onclick="resetMatchState()">🔄 NEW MATCH</button>
            <button class="btn btn-danger" onclick="resetTeams()">🗑️ DELETE ALL</button>
        </div>
    </div>

    <input type="text" id="searchInput" class="search-bar" placeholder="🔍 Search Team Name or Slot..." oninput="filterTeams()">

    <div id="teamsContainer" class="teams-grid"></div>
</div>

<div id="toast" class="toast">Action Successful</div>

<script>
let teamsData = [];

function showToast(msg) {
    const t = document.getElementById("toast");
    t.innerText = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2000);
}

// ----------------------------------------------------
// OPTIMISTIC UI LOGIC (ZERO LAG)
// ----------------------------------------------------
function updateTopCounters() {
    let aTeams = 0, aPlayers = 0;
    teamsData.forEach(t => {
        let alive = t.players.filter(p => p === 1).length;
        if(alive > 0) aTeams++;
        aPlayers += alive;
    });
    document.getElementById("topTeams").innerText = aTeams;
    document.getElementById("topPlayers").innerText = aPlayers;
}

// Handles local DOM update BEFORE server responds
function uiChangeKills(id, amount) {
    const team = teamsData.find(t => t.id === id);
    if(team) {
        team.kills = Math.max(0, team.kills + amount);
        team.points = team.kills + team.placement_points;
        document.getElementById(`kills-${id}`).innerText = team.kills;
        document.getElementById(`pts-${id}`).innerText = team.points;
        
        // Background sync
        fetch("/api/update", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: id, kills_change: amount})
        });
    }
}

function uiTogglePlayer(id, pIndex) {
    const team = teamsData.find(t => t.id === id);
    if(team) {
        team.players[pIndex] = team.players[pIndex] ? 0 : 1;
        const btn = document.getElementById(`pbtn-${id}-${pIndex}`);
        if(team.players[pIndex]) btn.classList.remove("dead");
        else btn.classList.add("dead");

        const aliveCount = team.players.filter(p=>p===1).length;
        const card = document.getElementById(`card-${id}`);
        
        // Auto elim visual update
        if(aliveCount === 0 && team.position === 0) {
            card.classList.add("eliminated");
        } else {
            card.classList.remove("eliminated");
        }
        updateTopCounters();

        fetch("/api/update", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: id, player: pIndex})
        }).then(res => loadTeamsSilent()); // Sync rank if auto-eliminated
    }
}

function uiUpdatePos(id, pos) {
    pos = parseInt(pos) || 0;
    fetch("/api/update", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id, position: pos})
    }).then(res => loadTeams());
}

function uiEliminate(id) {
    document.getElementById(`card-${id}`).classList.add("eliminated");
    for(let i=0; i<4; i++){
        document.getElementById(`pbtn-${id}-${i}`).classList.add("dead");
    }
    fetch("/api/eliminate", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id})
    }).then(res => loadTeamsSilent());
    updateTopCounters();
    showToast("Team Eliminated");
}

function uiUpdateName(id, val) {
    fetch("/api/update", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id, name: val})
    });
}
// ----------------------------------------------------

async function loadConfigData() {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    document.getElementById("tourneyName").value = cfg.tournament || "ENI ESPORTS";
    document.getElementById("matchName").value = cfg.match || "MATCH 1";
    document.getElementById("mapName").value = cfg.map || "ERANGEL";
}

async function updateConfig() {
    const tournament = document.getElementById("tourneyName").value;
    const match = document.getElementById("matchName").value;
    const map = document.getElementById("mapName").value;
    await fetch("/api/config", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({tournament, match, map})
    });
    showToast("Match Saved!");
}

// Renders the entire grid initially or on big resets
function renderAllTeams() {
    const container = document.getElementById("teamsContainer");
    let html = "";
    const totalTeams = teamsData.length;

    teamsData.forEach(team => {
        const aliveCount = team.players.filter(p => p === 1).length;
        const isDead = aliveCount === 0;

        let pHTML = "";
        team.players.forEach((a, idx) => {
            pHTML += `<div id="pbtn-${team.id}-${idx}" class="player-node ${a ? '' : 'dead'}" onclick="uiTogglePlayer(${team.id}, ${idx})">P${idx+1}</div>`;
        });

        let posOpts = `<option value="0" ${team.position==0?'selected':''}>POS 0 (Alive)</option>`;
        for(let i = totalTeams; i >= 1; i--){
            posOpts += `<option value="${i}" ${team.position==i?'selected':''}>RANK #${i}</option>`;
        }

        let logoImg = team.logo ? `<img src="${team.logo}">` : `<span>No Logo</span>`;

        html += `
            <div id="card-${team.id}" class="team-card searchable ${isDead ? 'eliminated' : ''}" data-name="${team.name.toLowerCase()}" data-slot="${team.id}">
                <div class="tc-header">
                    <span class="tc-slot">#${team.id}</span>
                    <input class="tc-name" value="${team.name}" onblur="uiUpdateName(${team.id}, this.value)">
                    <button class="btn btn-elim" onclick="uiEliminate(${team.id})">WIPE</button>
                </div>
                <div class="tc-players">${pHTML}</div>
                <div class="tc-controls">
                    <select onchange="uiUpdatePos(${team.id}, this.value)">${posOpts}</select>
                    <button class="btn btn-icon" onclick="uiChangeKills(${team.id}, -1)">-</button>
                    <button class="btn btn-icon plus" onclick="uiChangeKills(${team.id}, 1)">+1</button>
                </div>
                <div class="tc-stats">
                    <div class="tc-stat-box fin"><span>Finishes</span><strong id="kills-${team.id}">${team.kills}</strong></div>
                    <div class="tc-stat-box pts"><span>Place Pts</span><strong>${team.placement_points}</strong></div>
                    <div class="tc-stat-box tot"><span>Total Pts</span><strong id="pts-${team.id}">${team.points}</strong></div>
                </div>
                <div class="logo-row">
                    ${logoImg}
                    <input type="file" accept="image/*" onchange="uploadLogo(${team.id}, this)">
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
    filterTeams(); 
}

function filterTeams() {
    const query = document.getElementById("searchInput").value.toLowerCase().trim();
    const cards = document.querySelectorAll(".searchable");
    cards.forEach(c => {
        if(query === "" || c.dataset.name.includes(query) || c.dataset.slot === query) {
            c.style.display = "block";
        } else {
            c.style.display = "none";
        }
    });
}

async function loadTeams() {
    const res = await fetch("/api/teams");
    teamsData = await res.json();
    updateTopCounters();
    renderAllTeams();
}

async function loadTeamsSilent() {
    const res = await fetch("/api/teams");
    teamsData = await res.json();
    // Doesn't redraw DOM, just syncs data array and top counters
    updateTopCounters();
}

async function importSlots() {
    const rawText = document.getElementById("slotInput").value;
    if(!rawText.trim()) return alert("Please paste the slot list first!");
    
    const lines = rawText.split('\n');
    let names = [];
    
    lines.forEach(line => {
        let c = line.trim();
        
        // 1. Ignore headers like "Group" or "Slot List"
        if(!c || c.toUpperCase().includes("GROUP") || c.toUpperCase().includes("SLOT LIST")) return;
        
        // 2. Remove Discord mentions (e.g., <@123456789>)
        c = c.replace(/<@!?\d+>/g, '').trim();
        
        // 3. Core logic: If the line contains "Team", extract ONLY what comes after it
        let teamMatch = c.match(/team\s+(.*)/i);
        
        if(teamMatch) {
            // Captures the text after "Team "
            c = teamMatch[1].trim();
        } else {
            // If the word "Team" isn't used, strip the standard "Slot 1 -" prefixes
            c = c.replace(/^(?:slot\s*#?\d+[\s\-\→\:\.\|]*|\#?\d+[\.\-\)\:\|]+\s*)/i, '').trim();
        }
        
        // 4. Clean up any leftover special characters at the start or end
        c = c.replace(/^[\*\_\`\~\s\-\→\:\|\>]+/g, '').trim();
        c = c.replace(/[\*\_\`\~\s]+$/g, '').trim();
        
        if(c.length > 0) names.push(c);
    });
    
    if(names.length === 0) return alert("No valid team names found!");
    
    await fetch("/api/import_slots", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({names}) 
    });
    
    showToast(`Imported ${names.length} Teams`);
    loadTeams();
}
async function resetMatchState() {
    if(!confirm("Start New Match? Kills & Alive status will reset, Teams & Logos stay.")) return;
    await fetch("/api/reset_match", { method: "POST" });
    showToast("Match Reset!");
    loadTeams();
}
async function resetTeams() {
    if(!confirm("DELETE ALL TEAMS?")) return;
    await fetch("/api/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count: 0}) });
    loadTeams();
}
async function uploadLogo(id, fileInput) {
    if(fileInput.files && fileInput.files[0]){
        const fd = new FormData();
        fd.append("id", id); fd.append("logo", fileInput.files[0]);
        await fetch("/api/upload_logo", { method: "POST", body: fd });
        showToast("Logo Uploaded!");
        loadTeams();
    }
}

// Initial load
loadConfigData();
loadTeams();
</script>
</body>
</html>
"""

# =========================================================
# OBS OVERLAY 1: LIVE POINTS TABLE (/overlay/pt)
# =========================================================

PT_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');
*{box-sizing:border-box;}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}

#pt{
    position:fixed;
    top:40px;
    right:15px;
    width:285px;
    color:white;
    box-shadow: 0 12px 35px rgba(0,0,0,0.65);
    border-radius: 6px;
    overflow: hidden;
}

.top-status-bar{
    display:flex;
    justify-content:space-between;
    align-items:center;
    background: linear-gradient(90deg, #061326, #0d274c);
    border-top: 3px solid #f2c400;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.8px;
}
.top-status-bar span strong{
    color: #00ff66;
    font-size: 13px;
    margin-left: 3px;
}

.header{
    height:26px;
    display:grid;
    grid-template-columns:26px 1fr 48px 34px 36px;
    align-items:center;
    background: linear-gradient(90deg, #f2c400, #d4a900);
    color:#050b14;
    font-weight:800;
    font-size:11px;
    padding:0 6px;
    letter-spacing:0.5px;
}
.header div{text-align:center;}
.header div:nth-child(2){text-align:left;padding-left:4px;}

.row{
    height:28px;
    display:grid;
    grid-template-columns:26px 1fr 48px 34px 36px;
    align-items:center;
    background:linear-gradient(90deg, rgba(6, 20, 39, 0.94), rgba(11, 34, 62, 0.94));
    border-bottom:1px solid rgba(255,255,255,0.08);
    padding:0 6px;
    transition: background 0.25s ease;
}
.row:nth-child(even){
    background:linear-gradient(90deg, rgba(8, 25, 48, 0.94), rgba(14, 40, 72, 0.94));
}
.row.dead-team{
    background:linear-gradient(90deg, rgba(22, 12, 20, 0.88), rgba(12, 12, 18, 0.88));
    opacity: 0.62;
}
.rank-cell{
    text-align:center;
    color:#f2c400;
    font-weight:800;
    font-size:12px;
}
.team-name-area{
    text-align:left;
    padding-left:4px;
    font-size:12px;
    font-weight:800;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
    display:flex;
    align-items:center;
    gap:6px;
}
.team-logo{
    width:17px;
    height:17px;
    object-fit:contain;
    border-radius:2px;
    flex-shrink:0;
}
.players{
    display:flex;
    justify-content:center;
    align-items:center;
    gap:3px;
}
.player{
    width:5px;
    height:14px;
    background:#00ff66;
    border-radius:1px;
    box-shadow: 0 0 5px rgba(0,255,102,0.5);
}
.player.dead{
    background:#3d4b5c;
    box-shadow:none;
    opacity:0.5;
}
.elim-badge{
    font-size:10px;
    font-weight:800;
    color:#ff4d6d;
    background:rgba(255, 46, 77, 0.15);
    padding:1px 5px;
    border-radius:3px;
}
.kills{
    text-align:center;
    font-weight:700;
    font-size:12px;
    color:#00e5ff;
}
.pts{
    text-align:center;
    font-weight:800;
    font-size:13px;
    color:#f2c400;
    background:rgba(242, 196, 0, 0.1);
    height:100%;
    display:flex;
    align-items:center;
    justify-content:center;
}
</style>
</head>
<body>
<div id="pt">
    <div class="top-status-bar">
        <span>TEAMS <strong id="ptAliveTeams">0</strong></span>
        <span>ALIVE <strong id="ptAlivePlayers">0</strong></span>
    </div>
    <div class="header">
        <div>#</div>
        <div>TEAM</div>
        <div>ALIVE</div>
        <div>FIN</div>
        <div>PTS</div>
    </div>
    <div id="rows"></div>
</div>
<script>
async function loadPT(){
    try{
        const res = await fetch("/api/teams");
        const data = await res.json();
        const rows = document.getElementById("rows");

        let aliveTeams = 0;
        let alivePlayers = 0;
        data.forEach(t => {
            const a = t.players.filter(p => p === 1).length;
            if(a > 0) aliveTeams++;
            alivePlayers += a;
        });
        document.getElementById("ptAliveTeams").innerText = aliveTeams;
        document.getElementById("ptAlivePlayers").innerText = alivePlayers;

        const sorted = [...data].sort((a,b) => {
            if(b.points !== a.points) return b.points - a.points;
            if(b.kills !== a.kills) return b.kills - a.kills;
            const aAlive = a.players.filter(p => p === 1).length;
            const bAlive = b.players.filter(p => p === 1).length;
            return bAlive - aAlive;
        });

        let html = "";
        sorted.forEach((team, index) => {
            const aliveCount = team.players.filter(p => p === 1).length;
            const isDead = aliveCount === 0;

            let statusHTML = "";
            if(isDead){
                statusHTML = `<span class="elim-badge">${team.position > 0 ? '#' + team.position : 'OUT'}</span>`;
            } else {
                team.players.forEach(a => {
                    statusHTML += `<div class="player ${a ? "" : "dead"}"></div>`;
                });
            }

            let logoHTML = team.logo ? `<img class="team-logo" src="${escapeHtml(team.logo)}">` : '';
            html += `
                <div class="row ${isDead ? "dead-team" : ""}">
                    <div class="rank-cell">${index + 1}</div>
                    <div class="team-name-area">${logoHTML}<span style="overflow:hidden; text-overflow:ellipsis;">${escapeHtml(team.name)}</span></div>
                    <div class="players">${statusHTML}</div>
                    <div class="kills">${team.kills}</div>
                    <div class="pts">${team.points}</div>
                </div>`;
        });
        rows.innerHTML = html;
    }catch(e){}
}
function escapeHtml(t){const d=document.createElement("div");d.innerText=t||"";return d.innerHTML;}
loadPT();
setInterval(loadPT, 1000);
</script>
</body>
</html>
"""

# =========================================================
# OBS OVERLAY 2: ELIMINATION CARD (/overlay/elimination)
# =========================================================

ELIM_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');
*{box-sizing:border-box;}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}

#elimination{
    position:fixed;
    left:50%;
    top:16%;
    width:420px;
    transform:translate(-50%,-50%) scale(0.85);
    opacity:0;
    pointer-events:none;
    background:linear-gradient(135deg, rgba(6, 20, 39, 0.96), rgba(14, 34, 60, 0.98));
    border:1px solid rgba(255, 46, 77, 0.55);
    border-top:4px solid #ff2e4d;
    border-bottom:3px solid #f2c400;
    border-radius:12px;
    padding:16px 22px;
    text-align:center;
    box-shadow:0 18px 50px rgba(0,0,0,0.8);
    z-index:999;
}

#elimination.show{
    animation:elimShow 3.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes elimShow{
    0%{opacity:0;transform:translate(-50%,-65%) scale(0.75);}
    12%{opacity:1;transform:translate(-50%,-50%) scale(0.95);}
    82%{opacity:1;transform:translate(-50%,-50%) scale(0.95);}
    100%{opacity:0;transform:translate(-50%,-40%) scale(0.85);}
}

.elim-banner{
    display:inline-block;
    background: rgba(255, 46, 77, 0.2);
    border: 1px solid rgba(255, 46, 77, 0.5);
    color:#ff4d6d;
    font-size:11px;
    font-weight:800;
    letter-spacing:3px;
    padding:3px 12px;
    border-radius:4px;
    margin-bottom:8px;
}

.elim-team-row{
    display:flex;
    align-items:center;
    justify-content:center;
    gap:14px;
    margin-bottom:14px;
}
.elim-logo{
    width:48px;
    height:48px;
    object-fit:contain;
    border-radius:8px;
    background:rgba(255,255,255,0.07);
    padding:4px;
    border:1px solid rgba(242,196,0,0.4);
}
.elim-team{
    color:#ffffff;
    font-family:'Teko', sans-serif;
    font-size:36px;
    font-weight:700;
    letter-spacing:1.5px;
    line-height:1;
    text-transform:uppercase;
    text-shadow: 0 2px 10px rgba(0,0,0,0.6);
}

.elim-info{
    display:grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap:10px;
}
.info-box{
    padding:7px 6px;
    border:1px solid rgba(255,255,255,0.14);
    border-radius:8px;
    background:rgba(0,0,0,0.35);
}
.info-label{
    color:#9da9b8;
    font-size:10px;
    font-weight:800;
    letter-spacing:1px;
}
.info-value{
    color:white;
    font-size:21px;
    font-weight:800;
}
.info-value.gold{ color:#f2c400; }
.info-value.cyan{ color:#00e5ff; }
</style>
</head>
<body>
<div id="elimination">
    <div class="elim-banner">SQUAD ELIMINATED</div>
    <div class="elim-team-row">
        <img id="elimLogo" class="elim-logo" src="" style="display:none;" onerror="this.style.display='none'">
        <div class="elim-team" id="elimTeam">TEAM NAME</div>
    </div>
    <div class="elim-info">
        <div class="info-box"><div class="info-label">RANK</div><div class="info-value gold" id="elimRank">#0</div></div>
        <div class="info-box"><div class="info-label">FINISHES</div><div class="info-value cyan" id="elimKills">0</div></div>
        <div class="info-box"><div class="info-label">TOTAL PTS</div><div class="info-value" id="elimPts">0</div></div>
    </div>
</div>
<script>
let lastTeamState = {};
let lastElimTs = {};
let elimQueue = [];
let isPlaying = false;

async function checkElimination(){
    try{
        const res = await fetch("/api/teams?t=" + new Date().getTime());
        const data = await res.json();
        data.forEach(team => {
            const oldAlive = lastTeamState[team.id];
            const currentAlive = team.players.filter(p => p === 1).length;
            const currentTs = team.elim_ts || 0;
            const oldTs = lastElimTs[team.id];

            const newlyWiped = (oldAlive !== undefined && oldAlive > 0 && currentAlive === 0);
            const manualTriggered = (oldTs !== undefined && currentTs > oldTs);

            if((newlyWiped || manualTriggered) && team.position > 0){
                elimQueue.push(team);
                processQueue();
            }

            lastTeamState[team.id] = currentAlive;
            lastElimTs[team.id] = currentTs;
        });
    }catch(e){}
}

function processQueue(){
    if(isPlaying || elimQueue.length === 0) return;
    isPlaying = true;
    const team = elimQueue.shift();
    showElimination(team);
    setTimeout(() => {
        isPlaying = false;
        processQueue();
    }, 3600);
}

function showElimination(team){
    const card = document.getElementById("elimination");
    document.getElementById("elimTeam").innerText = team.name;
    document.getElementById("elimKills").innerText = team.kills;
    document.getElementById("elimRank").innerText = "#" + team.position;
    document.getElementById("elimPts").innerText = team.points;

    const logoImg = document.getElementById("elimLogo");
    if(team.logo && team.logo.trim() !== ""){
        logoImg.src = team.logo;
        logoImg.style.display = "inline-block";
    } else {
        logoImg.style.display = "none";
    }

    card.classList.remove("show");
    void card.offsetWidth;
    card.classList.add("show");
}

setInterval(checkElimination, 1000);
</script>
</body>
</html>
"""

# =========================================================
# OBS OVERLAY 3: MATCH & MAP WIDGET (/overlay/match)
# =========================================================

MATCH_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');
*{box-sizing:border-box;}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}

#match-info{
    position:fixed;
    bottom:18px;
    left:18px;
    min-width:240px;
    background:linear-gradient(135deg, rgba(6, 20, 39, 0.95), rgba(12, 34, 62, 0.95));
    border:1px solid rgba(242,196,0,0.4);
    border-left:4px solid #f2c400;
    border-radius:8px;
    padding:8px 14px;
    color:white;
    box-shadow:0 8px 25px rgba(0,0,0,0.65);
}
.mi-tourney{
    font-size:10px;
    font-weight:800;
    color:#00e5ff;
    letter-spacing:1.5px;
    text-transform:uppercase;
}
.mi-row{
    display:flex;
    align-items:baseline;
    gap:10px;
    margin-top:2px;
}
.mi-match{
    font-family:'Teko', sans-serif;
    font-size:24px;
    font-weight:700;
    color:#f2c400;
    letter-spacing:1px;
    line-height:1;
}
.mi-map{
    font-family:'Teko', sans-serif;
    font-size:24px;
    font-weight:700;
    color:white;
    letter-spacing:1px;
    line-height:1;
}
</style>
</head>
<body>
<div id="match-info">
    <div class="mi-tourney" id="displayTourney">ENI ESPORTS CHAMPIONSHIP</div>
    <div class="mi-row">
        <div class="mi-match" id="displayMatch">MATCH 1</div>
        <div style="color:rgba(255,255,255,0.3);">|</div>
        <div class="mi-map" id="displayMap">ERANGEL</div>
    </div>
</div>
<script>
async function loadConfig(){
    try{
        const res = await fetch("/api/config");
        const config = await res.json();
        document.getElementById("displayTourney").innerText = config.tournament || "ENI ESPORTS CHAMPIONSHIP";
        document.getElementById("displayMatch").innerText = config.match || "MATCH 1";
        document.getElementById("displayMap").innerText = config.map || "ERANGEL";
    }catch(e){}
}
loadConfig();
setInterval(loadConfig, 1000);
</script>
</body>
</html>
"""

# =========================================================
# OBS OVERLAY 4: FULL-SCREEN STANDINGS (/overlay/standings)
# =========================================================

STANDINGS_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');
*{box-sizing:border-box;}
html,body{
    margin:0;padding:0;width:100%;height:100%;overflow:hidden;
    background: radial-gradient(circle at center, rgba(10, 28, 54, 0.94) 0%, rgba(3, 8, 17, 0.98) 100%);
    font-family:'Rajdhani',sans-serif;
    color:white;
}

.board-wrapper{
    max-width: 1320px;
    margin: 35px auto;
    padding: 0 25px;
}

.board-header{
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    border-bottom: 3px solid #f2c400;
    padding-bottom: 10px;
    margin-bottom: 22px;
}
.bh-title{
    font-family:'Teko', sans-serif;
    font-size: 48px;
    color: #f2c400;
    line-height: 0.95;
    letter-spacing: 2px;
    text-transform: uppercase;
}
.bh-sub{
    font-size: 16px;
    font-weight: 800;
    color: #00e5ff;
    letter-spacing: 3px;
}

.standings-grid{
    display:grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px 28px;
}

.st-table{
    width:100%;
    border-collapse: separate;
    border-spacing: 0 6px;
}
.st-head{
    background: #f2c400;
    color: #040811;
    font-weight: 800;
    font-size: 13px;
    letter-spacing: 1px;
}
.st-head th{ padding: 7px 10px; text-align:center; }
.st-head th:nth-child(2){ text-align:left; }

.st-row{
    background: linear-gradient(90deg, rgba(9, 28, 54, 0.95), rgba(14, 40, 74, 0.9));
    transition: 0.2s;
}
.st-row.top1{
    background: linear-gradient(90deg, rgba(242, 196, 0, 0.28), rgba(16, 42, 76, 0.95));
    outline: 1px solid #f2c400;
}
.st-row td{
    padding: 8px 10px;
    text-align:center;
    font-weight: 800;
    font-size: 16px;
}
.st-row td:first-child{
    color: #f2c400;
    font-weight: 800;
    width: 45px;
}
.st-team{
    display:flex;
    align-items:center;
    gap: 10px;
    text-align:left;
}
.st-logo{
    width: 26px;
    height: 26px;
    object-fit: contain;
    border-radius: 4px;
}
.st-pts{
    color: #f2c400;
    font-size: 18px;
    background: rgba(242, 196, 0, 0.12);
}
</style>
</head>
<body>
<div class="board-wrapper">
    <div class="board-header">
        <div>
            <div class="bh-sub" id="stTourney">ENI ESPORTS CHAMPIONSHIP</div>
            <div class="bh-title">MATCH STANDINGS</div>
        </div>
        <div class="bh-title" style="font-size:34px; color:white;" id="stMatchMap">MATCH 1 - ERANGEL</div>
    </div>

    <div class="standings-grid">
        <table class="st-table">
            <thead>
                <tr class="st-head"><th>#</th><th>TEAM</th><th>PLACE PTS</th><th>FIN</th><th>TOTAL</th></tr>
            </thead>
            <tbody id="colLeft"></tbody>
        </table>
        <table class="st-table">
            <thead>
                <tr class="st-head"><th>#</th><th>TEAM</th><th>PLACE PTS</th><th>FIN</th><th>TOTAL</th></tr>
            </thead>
            <tbody id="colRight"></tbody>
        </table>
    </div>
</div>

<script>
async function loadStandings(){
    try{
        const [cfgRes, teamRes] = await Promise.all([fetch("/api/config"), fetch("/api/teams")]);
        const cfg = await cfgRes.json();
        const data = await teamRes.json();

        document.getElementById("stTourney").innerText = cfg.tournament || "ENI ESPORTS CHAMPIONSHIP";
        document.getElementById("stMatchMap").innerText = `${cfg.match || "MATCH 1"} • ${cfg.map || "ERANGEL"}`;

        const sorted = [...data].sort((a,b) => {
            if(b.points !== a.points) return b.points - a.points;
            return b.kills - a.kills;
        });

        const mid = Math.ceil(sorted.length / 2);
        const leftTeams = sorted.slice(0, mid);
        const rightTeams = sorted.slice(mid);

        document.getElementById("colLeft").innerHTML = renderRows(leftTeams, 0);
        document.getElementById("colRight").innerHTML = renderRows(rightTeams, mid);
    }catch(e){}
}

function renderRows(list, offset){
    return list.map((t, idx) => {
        const rank = offset + idx + 1;
        const logo = t.logo ? `<img class="st-logo" src="${escapeHtml(t.logo)}">` : "";
        return `
            <tr class="st-row ${rank === 1 ? 'top1' : ''}">
                <td>#${rank}</td>
                <td><div class="st-team">${logo}<span>${escapeHtml(t.name)}</span></div></td>
                <td style="color:#00bfff;">${t.placement_points}</td>
                <td style="color:#00ff66;">${t.kills}</td>
                <td class="st-pts">${t.points}</td>
            </tr>
        `;
    }).join("");
}
function escapeHtml(t){const d=document.createElement("div");d.innerText=t||"";return d.innerHTML;}
loadStandings();
setInterval(loadStandings, 1500);
</script>
</body>
</html>
"""

# =========================================================
# ROUTES & API
# =========================================================

@app.route("/")
def admin(): return render_template_string(ADMIN_HTML)

@app.route("/overlay/pt")
def overlay_pt(): return render_template_string(PT_HTML)

@app.route("/overlay/elimination")
def overlay_elimination(): return render_template_string(ELIM_HTML)

@app.route("/overlay/match")
def overlay_match(): return render_template_string(MATCH_HTML)

@app.route("/overlay/standings")
def overlay_standings(): return render_template_string(STANDINGS_HTML)

@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = load_config()
        if "tournament" in data: cfg["tournament"] = data["tournament"]
        if "match" in data: cfg["match"] = data["match"]
        if "map" in data: cfg["map"] = data["map"]
        save_config(cfg)
        return jsonify({"success": True})
    return jsonify(load_config())

@app.route("/api/teams")
def api_teams():
    # Safe read-only GET (no disk write race condition)
    teams = load()
    return jsonify(teams)

@app.route("/api/upload_logo", methods=["POST"])
def upload_logo():
    team_id = request.form.get("id")
    if "logo" not in request.files:
        return jsonify({"success": False})
    file = request.files["logo"]
    if file.filename == "":
        return jsonify({"success": False})

    filename = secure_filename(f"team_{team_id}_{int(time.time())}_{file.filename}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    teams = load()
    for team in teams:
        if str(team["id"]) == str(team_id):
            team["logo"] = f"/static/logos/{filename}"
            break
    save(teams)
    return jsonify({"success": True})

@app.route("/api/import_slots", methods=["POST"])
def import_slots():
    data = request.get_json() or {}
    names = data.get("names", [])
    if not names:
        return jsonify({"success": False})

    existing_teams = load()
    logo_map = {t["name"].upper(): t.get("logo", "") for t in existing_teams}

    teams = []
    for i, name in enumerate(names, start=1):
        teams.append({
            "id": i,
            "name": name,
            "logo": logo_map.get(name.upper(), ""),
            "kills": 0,
            "position": 0,
            "points": 0,
            "placement_points": 0,
            "players": [1, 1, 1, 1],
            "elim_ts": 0
        })
    save(teams)
    return jsonify({"success": True})

@app.route("/api/reset_match", methods=["POST"])
def reset_match():
    teams = load()
    for team in teams:
        team["kills"] = 0
        team["position"] = 0
        team["points"] = 0
        team["placement_points"] = 0
        team["players"] = [1, 1, 1, 1]
        team["elim_ts"] = 0
    save(teams)
    return jsonify({"success": True})

@app.route("/api/create", methods=["POST"])
def create():
    data = request.get_json() or {}
    count = int(data.get("count", 0))
    if count <= 0:
        save([])
        return jsonify({"success": True})
    count = min(count, 50)
    existing_teams = load()
    logo_map = {t["id"]: t.get("logo", "") for t in existing_teams}

    teams = []
    for i in range(1, count + 1):
        teams.append({
            "id": i,
            "name": f"TEAM {i}",
            "logo": logo_map.get(i, ""),
            "kills": 0,
            "position": 0,
            "points": 0,
            "placement_points": 0,
            "players": [1, 1, 1, 1],
            "elim_ts": 0
        })
    save(teams)
    return jsonify({"success": True})

@app.route("/api/update", methods=["POST"])
def update():
    data = request.get_json() or {}
    teams = load()
    team_id = int(data.get("id", 0))
    total_teams = len(teams)

    for team in teams:
        if team["id"] != team_id:
            continue
        if "name" in data:
            team["name"] = data["name"]
        if "player" in data:
            player = int(data["player"])
            if 0 <= player < 4:
                was_dead = (sum(team["players"]) == 0)
                team["players"][player] = 0 if team["players"][player] else 1
                now_alive = sum(team["players"])

                # All 4 players died -> Auto-assign next available rank
                if now_alive == 0 and team.get("position", 0) == 0:
                    assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                    for p in range(total_teams, 0, -1):
                        if p not in assigned_positions:
                            team["position"] = p
                            break
                    team["elim_ts"] = time.time()

                # Revived a player from a dead team -> Reset position to 0
                elif was_dead and now_alive > 0:
                    team["position"] = 0

        if "kills_change" in data:
            team["kills"] = max(0, team.get("kills", 0) + int(data["kills_change"]))
        if "position" in data:
            team["position"] = int(data["position"])

    save(teams)
    return jsonify({"success": True})

@app.route("/api/eliminate", methods=["POST"])
def eliminate():
    data = request.get_json() or {}
    teams = load()
    team_id = int(data.get("id", 0))
    total_teams = len(teams)

    for team in teams:
        if team["id"] == team_id:
            team["players"] = [0, 0, 0, 0]
            if team.get("position", 0) == 0:
                assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                for p in range(total_teams, 0, -1):
                    if p not in assigned_positions:
                        team["position"] = p
                        break
            team["elim_ts"] = time.time()
            break

    save(teams)
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)