from flask import Flask, request, jsonify, render_template_string
import json
import os
import time
import copy
from threading import Lock
from werkzeug.utils import secure_filename

app = Flask(__name__)
file_lock = Lock()

DATA_FILE = "teams.json"
CONFIG_FILE = "config.json"
HISTORY_FILE = "match_history.json"
UPLOAD_FOLDER = "static/logos"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Undo/Redo System Stacks
MAX_HISTORY = 20
undo_stack = []
redo_stack = []

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
        if 'absent' not in team: team['absent'] = False
        if 'overall_kills' not in team: team['overall_kills'] = 0
        if 'overall_pts' not in team: team['overall_pts'] = 0
        if 'overall_place_pts' not in team: team['overall_place_pts'] = 0
        if 'matches_played' not in team: team['matches_played'] = 0
        
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

def save_state_for_undo():
    global undo_stack, redo_stack
    current_state = load()
    undo_stack.append(copy.deepcopy(current_state))
    if len(undo_stack) > MAX_HISTORY:
        undo_stack.pop(0)
    redo_stack.clear()

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
# PREMIUM ADMIN PAGE (WITH DYNAMIC PLAYERS COUNT & STATIC SORT)
# =========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>ENI PRODUCTION | ESPORTS DASHBOARD</title>
<!-- CHART.JS INTEGRATION -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Teko:wght@500;600;700&family=Rajdhani:wght@500;600;700;800&display=swap');

:root {
    --bg-main: #03060f;
    --card-bg: rgba(13, 22, 38, 0.7);
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

.sticky-header {
    position: sticky; top: 0; z-index: 1000;
    background: rgba(5, 9, 20, 0.85); backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--glass-border); padding: 12px 15px;
    display: flex; justify-content: space-between; align-items: center;
    box-shadow: 0 6px 25px rgba(0,0,0,0.6);
}

.menu-dots-btn {
    background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border);
    color: var(--gold); padding: 6px 12px; border-radius: 8px; cursor: pointer;
    font-size: 18px; font-weight: 800; margin-right: 12px; transition: all 0.3s ease;
}
.menu-dots-btn:hover { background: rgba(242,196,0,0.15); border-color: var(--gold); box-shadow: 0 0 10px rgba(242,196,0,0.3); }

.brand-container { display: flex; align-items: center; }
.brand h1 { margin: 0; font-size: 28px; font-family: 'Teko', sans-serif; color: var(--gold); letter-spacing: 1.5px; text-shadow: 0 0 12px rgba(242,196,0,0.5); line-height: 1; }
.brand span { font-size: 11px; color: var(--cyan); font-weight: 700; letter-spacing: 2px; }

/* LIVE SYNC STATUS INDICATOR */
.sync-status {
    display: flex; align-items: center; gap: 6px; margin-left: 15px; font-size: 11px; font-weight: 800; letter-spacing: 1px;
    padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.3); transition: 0.3s;
}
.sync-dot { width: 8px; height: 8px; border-radius: 50%; }
.sync-live { color: var(--green); border-color: rgba(0, 255, 102, 0.3); }
.sync-live .sync-dot { background: var(--green); box-shadow: 0 0 8px var(--green); animation: pulse-sync 1.5s infinite; }
.sync-offline { color: var(--red); border-color: rgba(255, 42, 85, 0.3); }
.sync-offline .sync-dot { background: var(--red); box-shadow: 0 0 8px var(--red); }
@keyframes pulse-sync { 0% { opacity: 1; transform:scale(1); } 50% { opacity: 0.5; transform:scale(0.8); } 100% { opacity: 1; transform:scale(1); } }

.live-stats { display: flex; gap: 8px; align-items: center; }
.history-controls { display: flex; gap: 5px; margin-right: 15px; border-right: 1px solid rgba(255,255,255,0.1); padding-right: 15px; }
.btn-undo-redo { 
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.2); 
    color: white; border-radius: 6px; width: 36px; height: 36px; 
    display: flex; align-items: center; justify-content: center; font-size: 18px; 
    cursor: pointer; transition: 0.2s; 
}
.btn-undo-redo:hover { background: rgba(0,229,255,0.2); border-color: var(--cyan); }
.btn-undo-redo:active { transform: scale(0.9); }

.stat-badge {
    background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.2);
    padding: 4px 12px; border-radius: 6px; display: flex; flex-direction: column; align-items: center; min-width: 65px; box-shadow: inset 0 0 10px rgba(0, 229, 255, 0.05);
}
.stat-badge span { font-size: 9px; color: #9da9b8; font-weight: 700; text-transform: uppercase; }
.stat-badge strong { font-size: 16px; color: var(--cyan); font-weight: 800; line-height: 1.1; }
.stat-badge.players strong { color: var(--green); }
.stat-badge.players { background: rgba(0, 255, 102, 0.08); border-color: rgba(0, 255, 102, 0.2); box-shadow: inset 0 0 10px rgba(0, 255, 102, 0.05); }

.container { padding: 15px; max-width: 1400px; margin: 0 auto; }

.glass-card {
    background: var(--card-bg); backdrop-filter: blur(12px); border: 1px solid var(--glass-border);
    border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.4);
}

.links-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
.obs-link {
    background: linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)); border: 1px solid var(--glass-border);
    padding: 12px; border-radius: 8px; text-align: center; text-decoration: none; color: #b0c4de; font-size: 13px; font-weight: 700;
    transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.obs-link:hover { background: rgba(0,229,255,0.1); border-color: var(--cyan); color: white; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,229,255,0.2); }

input, select, textarea {
    background: rgba(0,0,0,0.5); color: white; border: 1px solid rgba(255,255,255,0.15); padding: 12px; border-radius: 8px;
    font-size: 14px; font-family: 'Rajdhani', sans-serif; font-weight: 700; width: 100%; outline: none; transition: all 0.3s ease;
}
input:focus, select:focus, textarea:focus { border-color: var(--cyan); box-shadow: 0 0 12px rgba(0,229,255,0.3); background: rgba(0,0,0,0.7); }

.btn {
    border: none; border-radius: 8px; padding: 12px 16px; cursor: pointer; font-weight: 800; font-size: 14px; font-family: 'Rajdhani', sans-serif;
    letter-spacing: 1px; text-transform: uppercase; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    display: inline-flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}
.btn:hover { transform: translateY(-2px); filter: brightness(1.15); box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
.btn:active { transform: scale(0.96) translateY(0); }
.btn-primary { background: linear-gradient(135deg, #0077b6, #00bfff); color: #fff; border: 1px solid #00bfff; }
.btn-gold { background: linear-gradient(135deg, #c89d00, var(--gold)); color: #040911; }
.btn-green { background: linear-gradient(135deg, #00994d, var(--green)); color: #040911; }
.btn-danger { background: linear-gradient(135deg, #8a0014, var(--red)); color: white; border: 1px solid var(--red); }
.btn-orange { background: linear-gradient(135deg, #cc7a00, #ff9900); color: white; border: 1px solid #ff9900; }
.btn-purple { background: linear-gradient(135deg, #7b2cbf, #9d4edd); color: white; border: 1px solid #c77dff; }

.search-bar { border-color: rgba(242,196,0,0.4) !important; font-size:16px; margin-bottom: 15px; }
.search-bar:focus { border-color: var(--gold) !important; box-shadow: 0 0 15px rgba(242,196,0,0.3); }

/* Compact Mode Styles */
.teams-grid { display: grid; grid-template-columns: 1fr; gap: 16px; transition: 0.3s; }
@media(min-width: 768px) { .teams-grid { grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); } }
.teams-grid.compact-mode { grid-template-columns: 1fr; gap: 8px; }
@media(min-width: 768px) { .teams-grid.compact-mode { grid-template-columns: repeat(auto-fill, minmax(450px, 1fr)); } }

.team-card {
    background: linear-gradient(160deg, rgba(16,28,48,0.95), rgba(6,12,24,0.98)); border: 1px solid var(--glass-border);
    border-left: 4px solid var(--cyan); border-radius: 12px; padding: 16px; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    position: relative; overflow: hidden; box-shadow: 0 6px 20px rgba(0,0,0,0.4);
}
.team-card:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(0,0,0,0.6); border-left-width: 6px; }
.team-card.eliminated { border-left-color: var(--red); background: linear-gradient(160deg, rgba(30,12,18,0.85), rgba(10,5,8,0.95)); opacity: 0.85; }
.team-card.not-present { border-left-color: #555; background: linear-gradient(160deg, rgba(20,20,20,0.9), rgba(10,10,10,0.95)); opacity: 0.4; }
.team-card.winner { border: 2px solid var(--gold); background: linear-gradient(160deg, rgba(40,30,10,0.95), rgba(20,15,5,0.98)); box-shadow: 0 0 20px rgba(242, 196, 0, 0.4); }

.tc-header { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.tc-slot { background: rgba(255,255,255,0.08); padding: 4px 8px; border-radius: 6px; font-weight: 800; color: #9da9b8; font-size: 13px; }
.tc-name { flex: 1; border: none; background: transparent; padding: 0; font-size: 19px; color: var(--gold); text-transform: uppercase; font-weight: 800; min-width: 120px; }
.btn-elim, .btn-not-present { padding: 6px 12px; font-size:11px; font-weight: 800; border-radius: 6px; cursor: pointer; transition: 0.3s; }
.btn-elim { background: rgba(255, 42, 85, 0.1); border: 1px solid var(--red); color: var(--red); }
.btn-elim:hover { background: var(--red); color: white; }
.btn-not-present { background: rgba(255, 42, 85, 0.15); border: 1px solid var(--red); color: var(--red); }
.btn-not-present:hover { background: var(--red); color: white; }
.btn-not-present.is-present { background: rgba(0, 255, 102, 0.15); border-color: var(--green); color: var(--green); }
.btn-not-present.is-present:hover { background: var(--green); color: black; }

/* DYNAMIC PLAYER DROPDOWN */
.player-count-select {
    background: rgba(0, 229, 255, 0.1); color: var(--cyan); border: 1px solid rgba(0, 229, 255, 0.3);
    border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 800; cursor: pointer; outline: none;
    font-family: 'Rajdhani', sans-serif; transition: 0.3s;
}
.player-count-select:hover { background: rgba(0, 229, 255, 0.2); }
.player-count-select option { background: #03060f; color: white; }

.tc-players { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 14px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.03); }
.player-node { flex: 1; height: 44px; border-radius: 6px; background: linear-gradient(135deg, var(--green), #00b347); display: flex; align-items: center; justify-content: center; color: #000; font-weight: 800; font-size: 15px; cursor: pointer; box-shadow: 0 0 12px rgba(0,255,102,0.3); transition: all 0.2s ease; border: 1px solid rgba(255,255,255,0.5); }
.player-node:hover { filter: brightness(1.2); transform: scale(1.05); }
.player-node.dead { background: rgba(255,255,255,0.05); color: #5a6678; border-color: rgba(255,255,255,0.1); box-shadow: none; }
.player-node.dead:hover { background: rgba(255, 42, 85, 0.2); border-color: var(--red); color: var(--red); }

.tc-controls { display: flex; gap: 8px; margin-bottom: 14px; align-items:center; }
.tc-controls select { padding: 10px 8px; font-size: 13px; }
.btn-icon { width: 46px; height: 46px; padding: 0; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.15); color: white; font-size: 22px; font-weight:bold; border-radius: 8px; transition: 0.3s; cursor: pointer; }
.btn-icon:hover { background: rgba(255,255,255,0.15); }
.btn-icon.plus { background: rgba(0, 255, 102, 0.1); border-color: rgba(0, 255, 102, 0.4); color: var(--green); }
.btn-icon.plus:hover { background: var(--green); color: black; box-shadow: 0 0 15px rgba(0,255,102,0.4); }

.tc-stats { display: flex; justify-content: space-between; background: rgba(0,0,0,0.5); border-radius: 8px; padding: 10px; border: 1px solid rgba(255,255,255,0.05); box-shadow: inset 0 2px 10px rgba(0,0,0,0.5); }
.tc-stat-box { text-align: center; flex: 1; }
.tc-stat-box span { display: block; font-size: 9px; color: #7a8a9e; font-weight: 700; text-transform: uppercase; margin-bottom:2px;}
.tc-stat-box strong { font-size: 17px; font-weight: 800; }
.tc-stat-box.fin strong { color: var(--green); }
.tc-stat-box.pts strong { color: var(--cyan); }
.tc-stat-box.tot strong { color: var(--gold); font-size: 20px; text-shadow: 0 0 10px rgba(242,196,0,0.3);}
.tc-stat-box.overall strong { color: #bf55ec; font-size: 20px; }
.logo-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 11px; background: rgba(255,255,255,0.03); padding: 8px; border-radius: 8px; margin-top: 12px; }
.logo-row img { width: 26px; height: 26px; object-fit: contain; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); }
.logo-row input[type="file"] { padding: 4px; font-size: 11px; border:none; background:transparent; cursor: pointer; color:#b0c4de;}

/* COMPACT MODE OVERRIDES */
.compact-mode .team-card { padding: 10px 12px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.compact-mode .tc-header { margin: 0; flex: 1; min-width: 150px; }
.compact-mode .tc-stats, .compact-mode .logo-row, .compact-mode .btn-elim, .compact-mode .btn-not-present, .compact-mode .tc-controls select, .compact-mode .player-count-select { display: none; }
.compact-mode .tc-players { margin: 0; padding: 4px; gap: 4px; flex: 1; background: transparent; border: none; min-width: 120px; }
.compact-mode .player-node { height: 28px; font-size: 12px; border-radius: 4px; }
.compact-mode .tc-controls { margin: 0; flex: 0; justify-content: flex-end; }
.compact-mode .btn-icon { width: 34px; height: 34px; font-size: 18px; }
.compact-mode .tc-name { font-size: 16px; }

/* Sidebar Overlay */
.sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(5px); z-index: 1500; display: none; }
.sidebar-overlay.show { display: block; }
.sidebar-menu { position: fixed; top: 0; left: -280px; width: 280px; height: 100%; background: linear-gradient(180deg, #070e1c, #03060f); border-right: 1px solid var(--glass-border); z-index: 2000; transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 5px 0 30px rgba(0,0,0,0.8); display: flex; flex-direction: column; padding: 20px; }
.sidebar-menu.open { left: 0; }
.sidebar-link { padding: 14px 15px; color: #b0c4de; text-decoration: none; font-weight: 700; font-size: 15px; border-radius: 8px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); margin-bottom: 12px; display: flex; align-items: center; gap:10px; transition: all 0.3s ease; }
.sidebar-link:hover { background: rgba(242,196,0,0.1); border-color: var(--gold); color: white; transform:translateX(5px); }
.sidebar-link.danger-link:hover { background: rgba(255,42,85,0.15); border-color: var(--red); color: white; }
.sidebar-link.analytics-link { color: var(--cyan); border-color: rgba(0,229,255,0.2); }
.sidebar-link.analytics-link:hover { background: rgba(0,229,255,0.15); border-color: var(--cyan); color: white; }

/* Modal General */
.modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(8px); z-index: 3000; display: none; align-items: center; justify-content: center; padding: 20px; }
.modal.show { display: flex; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from{opacity:0; transform:scale(0.95);} to{opacity:1; transform:scale(1);} }
.modal-content { background: linear-gradient(135deg, #0d1626, #070e1c); border: 1px solid var(--gold); border-radius: 12px; width: 100%; max-width: 700px; max-height: 85vh; overflow-y: auto; padding: 25px; box-shadow: 0 15px 50px rgba(0,0,0,0.8); }

/* Graph Canvas Container */
.chart-container { position: relative; height: 350px; width: 100%; margin-top: 15px; background: rgba(0,0,0,0.4); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); padding: 10px; }

.toast { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(20px); background: linear-gradient(135deg, var(--gold), #c89d00); color: #000; padding: 12px 30px; border-radius: 30px; font-weight: 800; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 10px 30px rgba(242, 196, 0, 0.4); opacity: 0; visibility: hidden; transition: all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55); z-index: 9999; }
.toast.show { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>

<!-- Sidebar Menu (3 Dots) -->
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleMenu()"></div>
<div class="sidebar-menu" id="sidebarMenu">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px; padding-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1);">
        <h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:28px;">OPTIONS</h2>
        <button class="menu-dots-btn" style="margin:0; padding:4px 12px;" onclick="toggleMenu()">✕</button>
    </div>
    
    <!-- GRAPH ANALYTICS BUTTON -->
    <a href="#" class="sidebar-link analytics-link" onclick="toggleMenu(); openAnalyticsModal();">
        <span style="font-size:20px;">📊</span> Match Analytics (Graph)
    </a>

    <a href="#" class="sidebar-link" onclick="toggleMenu(); openHistoryModal();">
        <span style="font-size:20px;">📚</span> View Match Archive
    </a>
    <a href="#" class="sidebar-link danger-link" style="margin-top:auto;" onclick="toggleMenu(); clearMatchHistory();">
        <span style="font-size:18px;">🗑️</span> Clear Entire History
    </a>
</div>

<!-- History Archive Modal -->
<div class="modal" id="historyModal">
    <div class="modal-content">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:15px;">
            <h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:32px;">MATCH ARCHIVE</h2>
            <div style="display:flex; gap:10px;">
                <button class="btn btn-danger" style="padding:6px 12px; font-size:12px;" onclick="clearMatchHistory()">🗑️ CLEAR ALL</button>
                <button class="btn" style="background:rgba(255,255,255,0.1); color:white; padding:6px 12px; font-size:12px;" onclick="closeModal('historyModal')">✕ CLOSE</button>
            </div>
        </div>
        <div id="historyListContainer">Loading archive...</div>
    </div>
</div>

<!-- Analytics Graph Modal -->
<div class="modal" id="analyticsModal">
    <div class="modal-content" style="max-width: 800px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:15px;">
            <div>
                <h2 style="margin:0; font-family:'Teko'; color:var(--cyan); font-size:32px; letter-spacing:1px;">TEAM PERFORMANCE</h2>
                <span style="color:#9da9b8; font-size:12px; font-weight:800; text-transform:uppercase;">Live Total Points Tracker</span>
            </div>
            <button class="btn" style="background:rgba(255,255,255,0.1); color:white; padding:6px 12px; font-size:12px;" onclick="closeModal('analyticsModal')">✕ CLOSE</button>
        </div>
        <div class="chart-container">
            <canvas id="pointsChart"></canvas>
        </div>
    </div>
</div>

<div class="sticky-header">
    <div class="brand-container">
        <button class="menu-dots-btn" onclick="toggleMenu()">⋮</button>
        <div class="brand">
            <h1>ENI PRO</h1>
            <span>LIVE BROADCAST</span>
        </div>
        
        <!-- LIVE SYNC STATUS INDICATOR -->
        <div id="syncIndicator" class="sync-status sync-live">
            <div class="sync-dot"></div>
            <span id="syncText">LIVE</span>
        </div>
    </div>
    
    <div class="live-stats">
        <div class="history-controls">
            <button class="btn-undo-redo" onclick="uiUndo()" title="Undo Action">↩️</button>
            <button class="btn-undo-redo" onclick="uiRedo()" title="Redo Action">↪️</button>
        </div>
        <div class="stat-badge"><span>Teams</span><strong id="topTeams">0</strong></div>
        <div class="stat-badge players"><span>Players</span><strong id="topPlayers">0</strong></div>
    </div>
</div>

<div class="container">
    <div class="glass-card" style="padding:10px;">
        <div class="links-grid">
            <a href="/overlay/pt" target="_blank" class="obs-link">📊 POINTS TABLE</a>
            <a href="/overlay/elimination" target="_blank" class="obs-link">💀 ELIMINATION</a>
            <a href="/overlay/match" target="_blank" class="obs-link">🗺️ MATCH INFO</a>
            <a href="/overlay/standings" target="_blank" class="obs-link">🏆 STANDINGS</a>
        </div>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px,1fr)); gap:15px; margin-bottom:15px;">
        <div class="glass-card" style="margin:0;">
            <div style="display:flex; gap:10px; margin-bottom:12px;">
                <div style="flex:1"><label style="font-size:11px; color:var(--gold); font-weight:700;">TOURNAMENT</label>
                <input id="tourneyName" type="text" value="ENI ESPORTS"></div>
                <div style="width:100px"><label style="font-size:11px; color:var(--gold); font-weight:700;">MATCH</label>
                <input id="matchName" type="text" value="MATCH 1"></div>
            </div>
            <div style="margin-bottom:15px;">
                <label style="font-size:11px; color:var(--gold); font-weight:700;">MAP</label>
                <select id="mapName">
                    <option>ERANGEL</option><option>MIRAMAR</option><option>RONDO</option>
                </select>
            </div>
            <button class="btn btn-gold" style="width:100%" onclick="updateConfig()">SAVE MATCH INFO</button>
        </div>

        <div class="glass-card" style="margin:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <label style="font-size:13px; font-weight:800; color:var(--cyan);">📋 DISCORD SLOT LIST</label>
                <div style="display:flex; gap:6px;">
                    <button class="btn btn-gold" style="padding:4px 10px; font-size:12px;" onclick="adjustSlots(1)">➕ Slot</button>
                    <button class="btn btn-danger" style="padding:4px 10px; font-size:12px;" onclick="adjustSlots(-1)">➖ Slot</button>
                </div>
            </div>
            <textarea id="slotInput" style="height:65px; margin-bottom:12px;" placeholder="Paste Discord slots here..."></textarea>
            <button class="btn btn-primary" style="width:100%" onclick="importSlots()">IMPORT TEAMS</button>
        </div>
    </div>

    <!-- CONTROLS & DELETE ALL -->
    <div class="glass-card" style="display:flex; flex-wrap:wrap; gap:12px; justify-content:space-between; align-items:center;">
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button id="btnCompact" class="btn btn-primary" style="background:transparent; border:1px solid var(--cyan); color:var(--cyan);" onclick="toggleCompactMode()">📋 COMPACT VIEW</button>
        </div>
        <div style="display:flex; gap:12px; flex:1; justify-content:flex-end; flex-wrap:wrap;">
            <button class="btn btn-danger" onclick="resetTeams()">🗑️ DELETE ALL</button>
            <button class="btn btn-green" onclick="resetMatchState()">🔄 NEW MATCH</button>
            <button class="btn btn-orange" onclick="saveMatchOverall()">💾 SAVE MATCH & NEXT</button>
        </div>
    </div>

    <input type="text" id="searchInput" class="search-bar" placeholder="🔍 Search Team Name or Slot..." oninput="filterTeams()">

    <div id="teamsContainer" class="teams-grid"></div>
</div>

<div id="toast" class="toast">Action Successful</div>

<script>
let teamsData = [];
let historyData = [];
let isCompactMode = false;
let analyticsChartInstance = null; 

// CHECK LIVE SYNC STATUS EVERY 3 SECONDS
async function checkSync() {
    try {
        const res = await fetch("/api/ping");
        if (res.ok) {
            document.getElementById("syncIndicator").className = "sync-status sync-live";
            document.getElementById("syncText").innerText = "LIVE";
        } else { throw new Error("Offline"); }
    } catch (e) {
        document.getElementById("syncIndicator").className = "sync-status sync-offline";
        document.getElementById("syncText").innerText = "OFFLINE";
    }
}
setInterval(checkSync, 3000);

function toggleMenu() { document.getElementById("sidebarMenu").classList.toggle("open"); document.getElementById("sidebarOverlay").classList.toggle("show"); }
function closeModal(id) { document.getElementById(id).classList.remove("show"); }

function toggleCompactMode() {
    isCompactMode = !isCompactMode;
    const container = document.getElementById("teamsContainer");
    const btn = document.getElementById("btnCompact");
    if(isCompactMode) {
        container.classList.add("compact-mode");
        btn.innerText = "🗂️ NORMAL VIEW";
        btn.style.background = "var(--cyan)";
        btn.style.color = "black";
    } else {
        container.classList.remove("compact-mode");
        btn.innerText = "📋 COMPACT VIEW";
        btn.style.background = "transparent";
        btn.style.color = "var(--cyan)";
    }
}

async function uiUndo() {
    const res = await fetch("/api/undo", { method: "POST" });
    const data = await res.json();
    if(data.success) { showToast("Action Undone! ↩️"); loadTeams(); }
    else { showToast("Nothing to Undo!"); }
}

async function uiRedo() {
    const res = await fetch("/api/redo", { method: "POST" });
    const data = await res.json();
    if(data.success) { showToast("Action Redone! ↪️"); loadTeams(); }
    else { showToast("Nothing to Redo!"); }
}

// -----------------------------------------------------
// CHART.JS GRAPH ANALYTICS LOGIC
// -----------------------------------------------------
async function openAnalyticsModal() {
    document.getElementById("analyticsModal").classList.add("show");
    
    const res = await fetch("/api/teams");
    const currentTeams = await res.json();
    
    const validTeams = currentTeams.filter(t => !t.absent).sort((a,b) => b.points - a.points).slice(0, 15);
    
    const labels = validTeams.map(t => t.name.length > 12 ? t.name.substring(0,10)+'..' : t.name);
    const dataPoints = validTeams.map(t => t.points);
    
    const ctx = document.getElementById('pointsChart').getContext('2d');
    if(analyticsChartInstance) { analyticsChartInstance.destroy(); }
    
    analyticsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Points',
                data: dataPoints,
                backgroundColor: 'rgba(0, 229, 255, 0.6)',
                borderColor: 'rgba(0, 229, 255, 1)',
                borderWidth: 1,
                borderRadius: 4,
                hoverBackgroundColor: 'rgba(242, 196, 0, 0.8)',
                hoverBorderColor: 'rgba(242, 196, 0, 1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: 'rgba(13, 22, 38, 0.9)', titleFont: { family: 'Rajdhani', size: 16 }, bodyFont: { family: 'Rajdhani', size: 14, weight: 'bold' }, borderColor: 'rgba(0, 229, 255, 0.5)', borderWidth: 1 }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#b0c4de', font: { family: 'Rajdhani', size: 12, weight: 'bold' } } },
                x: { grid: { display: false }, ticks: { color: '#b0c4de', font: { family: 'Rajdhani', size: 11, weight: 'bold' }, maxRotation: 45, minRotation: 45 } }
            },
            animation: { duration: 1000, easing: 'easeOutQuart' }
        }
    });
}

// -----------------------------------------------------
// MATCH HISTORY LOGIC
// -----------------------------------------------------
async function openHistoryModal() {
    document.getElementById("historyModal").classList.add("show");
    const res = await fetch("/api/history");
    historyData = await res.json();
    const container = document.getElementById("historyListContainer");
    
    if(historyData.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding:30px;"><span style="font-size:40px; display:block; margin-bottom:10px;">📭</span><p style="color:#9da9b8; font-size:16px;">No finished matches saved yet.</p></div>`;
        return;
    }
    
    let html = "";
    historyData.forEach(m => {
        let sortedTeams = [...m.teams].sort((a,b) => b.total_pts - a.total_pts);
        html += `
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:15px; margin-bottom:15px; box-shadow:0 4px 15px rgba(0,0,0,0.2);">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px; margin-bottom:10px;">
                    <h3 style="margin:0; color:var(--gold); font-size:22px;">MATCH #${m.match_num}</h3>
                </div>
                <div style="max-height:200px; overflow-y:auto; padding-right:5px;">
                    <table style="width:100%; border-collapse:collapse; font-size:14px;">
                        <tr style="color:var(--cyan); border-bottom:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.3);">
                            <th style="text-align:left; padding:8px;">Team</th>
                            <th style="text-align:center; padding:8px;">Kills</th>
                            <th style="text-align:center; padding:8px;">Place</th>
                            <th style="text-align:center; padding:8px;">Total</th>
                        </tr>`;
        sortedTeams.forEach(t => {
            html += `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.03); transition:0.2s;">
                    <td style="text-align:left; padding:8px; font-weight:700;">${t.name}</td>
                    <td style="text-align:center; padding:8px; color:var(--green);">${t.kills}</td>
                    <td style="text-align:center; padding:8px; color:var(--cyan);">${t.placement_points}</td>
                    <td style="text-align:center; padding:8px; color:var(--gold); font-weight:800; font-size:16px;">${t.total_pts}</td>
                </tr>`;
        });
        html += `</table></div></div>`;
    });
    container.innerHTML = html;
}

async function clearMatchHistory() {
    if(!confirm("⚠️ ARE YOU SURE? This will permanently delete all saved match results and reset the match counter back to MATCH 1.")) return;
    const res = await fetch("/api/clear_history", { method: "POST" });
    if(res.ok) { showToast("Match History Wiped!"); closeModal('historyModal'); loadConfigData(); loadTeams(); }
}

function showToast(msg) {
    const t = document.getElementById("toast");
    t.innerText = msg; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2500);
}

function updateTopCounters() {
    let aTeams = 0, aPlayers = 0;
    teamsData.forEach(t => {
        if(!t.absent) {
            let alive = t.players.filter(p => p === 1).length;
            if(alive > 0) aTeams++;
            aPlayers += alive;
        }
    });
    document.getElementById("topTeams").innerText = aTeams;
    document.getElementById("topPlayers").innerText = aPlayers;
    return aTeams;
}

// SET DYNAMIC PLAYER COUNT FOR A TEAM (4, 3, 2, 1)
function uiSetPlayerCount(id, count) {
    fetch("/api/update", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id, player_count: count})
    }).then(res => loadTeams());
}

function uiChangeKills(id, amount) {
    const team = teamsData.find(t => t.id === id);
    if(team && !team.absent) {
        team.kills = Math.max(0, team.kills + amount);
        team.points = team.kills + team.placement_points;
        
        document.getElementById(`kills-${id}`).innerText = team.kills;
        document.getElementById(`pts-${id}`).innerText = team.points;
        
        fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id, kills_change: amount}) });
    }
}

function uiTogglePlayer(id, pIndex) {
    const team = teamsData.find(t => t.id === id);
    if(team && !team.absent) {
        team.players[pIndex] = team.players[pIndex] ? 0 : 1;
        
        const btn = document.getElementById(`pbtn-${id}-${pIndex}`);
        if(team.players[pIndex]) btn.classList.remove("dead"); else btn.classList.add("dead");
        
        const aliveCount = team.players.filter(p=>p===1).length;
        const card = document.getElementById(`card-${id}`);
        if(aliveCount === 0 && team.position === 0) card.classList.add("eliminated");
        else card.classList.remove("eliminated");
        
        updateTopCounters();
        fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id, player: pIndex}) });
    }
}

function uiUpdatePos(id, pos) {
    pos = parseInt(pos) || 0;
    fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id, position: pos}) })
    .then(res => loadTeams());
}

function uiEliminate(id) {
    const team = teamsData.find(t => t.id === id);
    if(team && !team.absent) {
        document.getElementById(`card-${id}`).classList.add("eliminated");
        for(let i=0; i<team.players.length; i++){
            let pbtn = document.getElementById(`pbtn-${id}-${i}`);
            if(pbtn) pbtn.classList.add("dead");
        }
        fetch("/api/eliminate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id}) });
        updateTopCounters(); showToast("Team Wiped");
    }
}

function uiUpdateName(id, val) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id, name: val}) }); }

async function uiToggleAbsent(id) {
    await fetch("/api/toggle_absent", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: id}) });
    loadTeams(); showToast("Status Updated");
}

async function adjustSlots(amount) {
    let newCount = teamsData.length + amount; if(newCount < 0) newCount = 0;
    await fetch("/api/adjust_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count: newCount}) });
    loadTeams(); showToast(`Slots updated to ${newCount}`);
}

async function saveMatchOverall() {
    if(!confirm("Save current match points to database, reset live points, and auto-advance to the next match?")) return;
    const res = await fetch("/api/save_match_overall", { method: "POST" });
    const data = await res.json();
    if(res.ok) {
        showToast("Match Saved Successfully!");
        document.getElementById("matchName").value = data.next_match;
        await updateConfig(); loadTeams();
    }
}

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
    await fetch("/api/config", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({tournament, match, map}) });
    showToast("Config Saved!");
}

function renderAllTeams() {
    const container = document.getElementById("teamsContainer");
    let html = "";
    
    // Sort strictly by ID (Slot Number) to prevent jump issues
    let displayTeams = [...teamsData].sort((a,b) => a.id - b.id);
    
    const totalTeams = displayTeams.length;
    let aliveTeamsCount = updateTopCounters();

    displayTeams.forEach(team => {
        const isAbsent = team.absent || false;
        const aliveCount = team.players.filter(p => p === 1).length;
        const isDead = aliveCount === 0;
        const isWinner = (!isDead && aliveTeamsCount === 1 && !isAbsent);

        let pHTML = "";
        // Dynamically loop based on team.players array length (1,2,3,4)
        team.players.forEach((a, idx) => { 
            pHTML += `<div id="pbtn-${team.id}-${idx}" class="player-node ${a ? '' : 'dead'}" onclick="uiTogglePlayer(${team.id}, ${idx})">P${idx+1}</div>`; 
        });

        let posOpts = `<option value="0" ${team.position==0?'selected':''}>POS 0 (Alive)</option>`;
        for(let i = totalTeams; i >= 1; i--) posOpts += `<option value="${i}" ${team.position==i?'selected':''}>RANK #${i}</option>`;

        let logoImg = team.logo ? `<img src="${team.logo}">` : `<span style="color:#7a8a9e; font-size:10px;">NO LOGO</span>`;
        let absentBtnClass = isAbsent ? "btn-not-present" : "btn-not-present is-present";
        let absentBtnText = isAbsent ? "❌ NOT PRESENT" : "✅ PRESENT";

        html += `
            <div id="card-${team.id}" class="team-card searchable ${isAbsent ? 'not-present' : ''} ${isDead ? 'eliminated' : ''} ${isWinner ? 'winner' : ''}" data-name="${team.name.toLowerCase()}" data-slot="${team.id}">
                <div class="tc-header">
                    <span class="tc-slot">#${team.id}</span>
                    <input class="tc-name" value="${team.name}" onblur="uiUpdateName(${team.id}, this.value)" ${isAbsent ? 'disabled' : ''}>
                    ${isWinner ? `<span style="background:var(--gold); color:black; padding:2px 8px; border-radius:4px; font-weight:800; font-size:12px; margin-right:10px; animation: pulse 1.5s infinite;">🏆 WINNER</span>` : ''}
                    
                    <select class="player-count-select" onchange="uiSetPlayerCount(${team.id}, this.value)" ${isAbsent ? 'disabled' : ''}>
                        <option value="4" ${team.players.length==4?'selected':''}>4 PLAYERS</option>
                        <option value="3" ${team.players.length==3?'selected':''}>3 PLAYERS</option>
                        <option value="2" ${team.players.length==2?'selected':''}>2 PLAYERS</option>
                        <option value="1" ${team.players.length==1?'selected':''}>1 PLAYER</option>
                    </select>

                    <button class="${absentBtnClass}" onclick="uiToggleAbsent(${team.id})">${absentBtnText}</button>
                    <button class="btn btn-elim" onclick="uiEliminate(${team.id})" ${isAbsent ? 'disabled' : ''}>WIPE</button>
                </div>
                <div class="tc-players" style="${isAbsent ? 'opacity:0.3; pointer-events:none;' : ''}">${pHTML}</div>
                <div class="tc-controls" style="${isAbsent ? 'opacity:0.3; pointer-events:none;' : ''}">
                    <select onchange="uiUpdatePos(${team.id}, this.value)" ${isAbsent ? 'disabled' : ''}>${posOpts}</select>
                    <button class="btn btn-icon" onclick="uiChangeKills(${team.id}, -1)" ${isAbsent ? 'disabled' : ''}>-</button>
                    <button class="btn btn-icon plus" onclick="uiChangeKills(${team.id}, 1)" ${isAbsent ? 'disabled' : ''}>+1</button>
                </div>
                <div class="tc-stats" style="${isAbsent ? 'opacity:0.3;' : ''}">
                    <div class="tc-stat-box fin"><span>Finishes</span><strong id="kills-${team.id}">${team.kills}</strong></div>
                    <div class="tc-stat-box pts"><span>Place Pts</span><strong>${team.placement_points}</strong></div>
                    <div class="tc-stat-box tot"><span>Total Pts</span><strong id="pts-${team.id}">${team.points}</strong></div>
                    <div class="tc-stat-box overall"><span>Overall</span><strong>${team.overall_pts || 0}</strong></div>
                </div>
                <div class="logo-row">
                    ${logoImg}
                    <input type="file" accept="image/*" onchange="uploadLogo(${team.id}, this)" style="max-width:180px;">
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
    filterTeams(); 
}

function filterTeams() {
    const query = document.getElementById("searchInput").value.toLowerCase().trim();
    document.querySelectorAll(".searchable").forEach(c => { c.style.display = (query === "" || c.dataset.name.includes(query) || c.dataset.slot === query) ? "block" : "none"; });
}

async function loadTeams() {
    const res = await fetch("/api/teams");
    teamsData = await res.json();
    renderAllTeams();
}

async function importSlots() {
    const rawText = document.getElementById("slotInput").value;
    if(!rawText.trim()) return alert("Please paste the slot list first!");
    const lines = rawText.split('\n');
    let names = [];
    lines.forEach(line => {
        let c = line.trim();
        if(!c || c.toUpperCase().includes("GROUP") || c.toUpperCase().includes("SLOT LIST")) return;
        c = c.replace(/<@!?\d+>/g, '').trim();
        let teamMatch = c.match(/team\s+(.*)/i);
        if(teamMatch) c = teamMatch[1].trim(); else c = c.replace(/^(?:slot\s*#?\d+[\s\-\→\:\.\|]*|\#?\d+[\.\-\)\:\|]+\s*)/i, '').trim();
        c = c.replace(/^[\*\_\`\~\s\-\→\:\|\>]+/g, '').trim(); c = c.replace(/[\*\_\`\~\s]+$/g, '').trim();
        if(c.length > 0) names.push(c);
    });
    if(names.length === 0) return alert("No valid team names found!");
    await fetch("/api/import_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({names}) });
    showToast(`Imported ${names.length} Teams`); loadTeams();
}

async function resetMatchState() {
    if(!confirm("Start New Match? Kills & Alive status will reset, Teams & Logos stay.")) return;
    await fetch("/api/reset_match", { method: "POST" });
    showToast("Match Reset!"); loadTeams();
}

async function resetTeams() {
    if(!confirm("⚠️ DELETE ALL TEAMS? This clears the current slot list.")) return;
    await fetch("/api/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count: 0}) });
    showToast("Teams Deleted"); loadTeams();
}

async function uploadLogo(id, fileInput) {
    if(fileInput.files && fileInput.files[0]){
        const fd = new FormData();
        fd.append("id", id); fd.append("logo", fileInput.files[0]);
        await fetch("/api/upload_logo", { method: "POST", body: fd });
        showToast("Logo Uploaded!"); loadTeams();
    }
}

const style = document.createElement('style');
style.innerHTML = `@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(242,196,0,0.7); } 70% { box-shadow: 0 0 0 10px rgba(242,196,0,0); } 100% { box-shadow: 0 0 0 0 rgba(242,196,0,0); } }`;
document.head.appendChild(style);

loadConfigData(); loadTeams();
</script>
</body>
</html>
"""

# =========================================================
# OBS OVERLAYS (EXACTLY PRESERVED)
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
.row.absent-team{
    background:linear-gradient(90deg, rgba(30, 30, 30, 0.9), rgba(15, 15, 15, 0.9));
    opacity: 0.45;
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
.absent-badge{
    font-size:9px;
    font-weight:800;
    color:#ff9900;
    background:rgba(255, 153, 0, 0.15);
    padding:1px 4px;
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
            if(!t.absent) {
                const a = t.players.filter(p => p === 1).length;
                if(a > 0) aliveTeams++;
                alivePlayers += a;
            }
        });
        document.getElementById("ptAliveTeams").innerText = aliveTeams;
        document.getElementById("ptAlivePlayers").innerText = alivePlayers;

        const sorted = [...data].sort((a,b) => {
            if(a.absent !== b.absent) return a.absent ? 1 : -1;
            if(b.points !== a.points) return b.points - a.points;
            if(b.kills !== a.kills) return b.kills - a.kills;
            const aAlive = a.players.filter(p => p === 1).length;
            const bAlive = b.players.filter(p => p === 1).length;
            return bAlive - aAlive;
        });

        let html = "";
        sorted.forEach((team, index) => {
            const isAbsent = team.absent || false;
            const aliveCount = team.players.filter(p => p === 1).length;
            const isDead = !isAbsent && aliveCount === 0;

            let statusHTML = "";
            if(isAbsent){
                statusHTML = `<span class="absent-badge">ABSENT</span>`;
            } else if(isDead){
                statusHTML = `<span class="elim-badge">${team.position > 0 ? '#' + team.position : 'OUT'}</span>`;
            } else {
                team.players.forEach(a => {
                    statusHTML += `<div class="player ${a ? "" : "dead"}"></div>`;
                });
            }

            let logoHTML = team.logo ? `<img class="team-logo" src="${escapeHtml(team.logo)}">` : '';
            html += `
                <div class="row ${isAbsent ? "absent-team" : (isDead ? "dead-team" : "")}">
                    <div class="rank-cell">${isAbsent ? '-' : index + 1}</div>
                    <div class="team-name-area">${logoHTML}<span style="overflow:hidden; text-overflow:ellipsis;">${escapeHtml(team.name)}</span></div>
                    <div class="players">${statusHTML}</div>
                    <div class="kills">${isAbsent ? '-' : team.kills}</div>
                    <div class="pts">${isAbsent ? '-' : team.points}</div>
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
            if(team.absent) return;
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
.st-row.absent-row{
    background: linear-gradient(90deg, rgba(30, 30, 30, 0.9), rgba(15, 15, 15, 0.9));
    opacity: 0.45;
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
            <div class="bh-title">OVERALL STANDINGS</div>
        </div>
        <div class="bh-title" style="font-size:34px; color:white;" id="stMatchMap">LEADERBOARD</div>
    </div>

    <div class="standings-grid">
        <table class="st-table">
            <thead>
                <tr class="st-head"><th>#</th><th>TEAM</th><th>MATCHES</th><th>KILLS</th><th>PLACE PTS</th><th>TOTAL PTS</th></tr>
            </thead>
            <tbody id="colLeft"></tbody>
        </table>
        <table class="st-table">
            <thead>
                <tr class="st-head"><th>#</th><th>TEAM</th><th>MATCHES</th><th>KILLS</th><th>PLACE PTS</th><th>TOTAL PTS</th></tr>
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

        const sorted = [...data].sort((a,b) => {
            if(a.absent !== b.absent) return a.absent ? 1 : -1;
            if((b.overall_pts || 0) !== (a.overall_pts || 0)) return (b.overall_pts || 0) - (a.overall_pts || 0);
            return (b.overall_kills || 0) - (a.overall_kills || 0);
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
        const isAbsent = t.absent || false;
        const logo = t.logo ? `<img class="st-logo" src="${escapeHtml(t.logo)}">` : "";
        return `
            <tr class="st-row ${!isAbsent && rank === 1 ? 'top1' : ''} ${isAbsent ? 'absent-row' : ''}">
                <td>${isAbsent ? '-' : '#' + rank}</td>
                <td><div class="st-team">${logo}<span>${escapeHtml(t.name)}</span></div></td>
                <td style="color:#ffffff;">${isAbsent ? '-' : (t.matches_played || 0)}</td>
                <td style="color:#00ff66;">${isAbsent ? '-' : (t.overall_kills || 0)}</td>
                <td style="color:#00bfff;">${isAbsent ? '-' : (t.overall_place_pts || 0)}</td>
                <td class="st-pts" style="color:#f2c400;">${isAbsent ? '-' : (t.overall_pts || 0)}</td>
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

@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok"})

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
    teams = load()
    return jsonify(teams)

@app.route("/api/undo", methods=["POST"])
def api_undo():
    global undo_stack, redo_stack
    if undo_stack:
        current_state = load()
        redo_stack.append(copy.deepcopy(current_state))
        
        previous_state = undo_stack.pop()
        with file_lock:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(previous_state, f, indent=2)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/redo", methods=["POST"])
def api_redo():
    global undo_stack, redo_stack
    if redo_stack:
        current_state = load()
        undo_stack.append(copy.deepcopy(current_state))
        
        next_state = redo_stack.pop()
        with file_lock:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(next_state, f, indent=2)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/history")
def api_history():
    if not os.path.exists(HISTORY_FILE): return jsonify([])
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except: return jsonify([])

@app.route("/api/clear_history", methods=["POST"])
def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
    
    cfg = load_config()
    cfg["match"] = "MATCH 1"
    save_config(cfg)
    
    save_state_for_undo()
    teams = load()
    for t in teams:
        t["matches_played"] = 0
        t["overall_kills"] = 0
        t["overall_place_pts"] = 0
        t["overall_pts"] = 0
    save(teams)
    return jsonify({"success": True})

@app.route("/api/upload_logo", methods=["POST"])
def upload_logo():
    team_id = request.form.get("id")
    if "logo" not in request.files: return jsonify({"success": False})
    file = request.files["logo"]
    if file.filename == "": return jsonify({"success": False})

    filename = secure_filename(f"team_{team_id}_{int(time.time())}_{file.filename}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    save_state_for_undo()
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
    if not names: return jsonify({"success": False})

    save_state_for_undo()
    existing_teams = load()
    logo_map = {t["name"].upper(): t.get("logo", "") for t in existing_teams}

    teams = []
    for i, name in enumerate(names, start=1):
        teams.append({
            "id": i, "name": name, "logo": logo_map.get(name.upper(), ""),
            "kills": 0, "position": 0, "points": 0, "placement_points": 0,
            "overall_kills": 0, "overall_place_pts": 0, "overall_pts": 0,
            "matches_played": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
        })
    save(teams)
    return jsonify({"success": True})

@app.route("/api/adjust_slots", methods=["POST"])
def adjust_slots():
    data = request.get_json() or {}
    new_count = int(data.get("count", 0))
    new_count = max(0, min(new_count, 50))
    
    save_state_for_undo()
    teams = load()
    current_count = len(teams)
    
    if new_count > current_count:
        for i in range(current_count + 1, new_count + 1):
            teams.append({
                "id": i, "name": f"TEAM {i}", "logo": "", "kills": 0, "position": 0,
                "points": 0, "placement_points": 0, "overall_kills": 0, "overall_place_pts": 0,
                "overall_pts": 0, "matches_played": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
            })
    elif new_count < current_count:
        teams = teams[:new_count]
        
    save(teams)
    return jsonify({"success": True})

@app.route("/api/reset_match", methods=["POST"])
def reset_match():
    save_state_for_undo()
    teams = load()
    for team in teams:
        team["kills"] = 0
        team["position"] = 0
        team["points"] = 0
        team["placement_points"] = 0
        # Reset everyone alive but KEEP the dynamic length (if they had 3 players, keep 3)
        team["players"] = [1] * len(team.get("players", [1, 1, 1, 1]))
        team["elim_ts"] = 0
    save(teams)
    return jsonify({"success": True})

@app.route("/api/create", methods=["POST"])
def create():
    data = request.get_json() or {}
    count = int(data.get("count", 0))
    save_state_for_undo()
    if count <= 0:
        save([])
        return jsonify({"success": True})
    count = min(count, 50)
    existing_teams = load()
    logo_map = {t["id"]: t.get("logo", "") for t in existing_teams}

    teams = []
    for i in range(1, count + 1):
        teams.append({
            "id": i, "name": f"TEAM {i}", "logo": logo_map.get(i, ""),
            "kills": 0, "position": 0, "points": 0, "placement_points": 0,
            "overall_kills": 0, "overall_place_pts": 0, "overall_pts": 0,
            "matches_played": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
        })
    save(teams)
    return jsonify({"success": True})

@app.route("/api/update", methods=["POST"])
def update():
    data = request.get_json() or {}
    save_state_for_undo()
    teams = load()
    team_id = int(data.get("id", 0))
    total_teams = len(teams)

    for team in teams:
        if team["id"] != team_id: continue
        if "name" in data: team["name"] = data["name"]
        
        # DYNAMIC PLAYER COUNT UPDATE
        if "player_count" in data:
            new_count = int(data["player_count"])
            current = team.get("players", [1, 1, 1, 1])
            if new_count > len(current):
                current.extend([1] * (new_count - len(current)))
            elif new_count < len(current):
                current = current[:new_count]
            team["players"] = current
            
            # Recalculate elimination status if needed based on new length
            if sum(team["players"]) == 0 and team.get("position", 0) == 0:
                assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                for p in range(total_teams, 0, -1):
                    if p not in assigned_positions:
                        team["position"] = p
                        break
                team["elim_ts"] = time.time()
            elif sum(team["players"]) > 0 and team.get("position", 0) > 0:
                team["position"] = 0
                team["elim_ts"] = 0

        if "player" in data:
            player = int(data["player"])
            if 0 <= player < len(team["players"]):
                was_dead = (sum(team["players"]) == 0)
                team["players"][player] = 0 if team["players"][player] else 1
                now_alive = sum(team["players"])

                if now_alive == 0 and team.get("position", 0) == 0:
                    assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                    for p in range(total_teams, 0, -1):
                        if p not in assigned_positions:
                            team["position"] = p
                            break
                    team["elim_ts"] = time.time()
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
    save_state_for_undo()
    teams = load()
    team_id = int(data.get("id", 0))
    total_teams = len(teams)

    for team in teams:
        if team["id"] == team_id:
            team["players"] = [0] * len(team.get("players", [1,1,1,1]))
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

@app.route("/api/toggle_absent", methods=["POST"])
def toggle_absent():
    data = request.get_json() or {}
    save_state_for_undo()
    team_id = int(data.get("id", 0))
    teams = load()
    for team in teams:
        if team["id"] == team_id:
            team["absent"] = not team.get("absent", False)
            break
    save(teams)
    return jsonify({"success": True})

@app.route("/api/save_match_overall", methods=["POST"])
def save_match_overall():
    save_state_for_undo()
    teams = load()
    current_match_data = []
    for t in teams:
        if not t.get("absent", False):
            t["matches_played"] = t.get("matches_played", 0) + 1
            t["overall_kills"] = t.get("overall_kills", 0) + t.get("kills", 0)
            t["overall_place_pts"] = t.get("overall_place_pts", 0) + t.get("placement_points", 0)
            t["overall_pts"] = t.get("overall_pts", 0) + t.get("points", 0)
            
        current_match_data.append({
            "id": t["id"], "name": t["name"], "kills": t.get("kills", 0),
            "placement_points": t.get("placement_points", 0), "total_pts": t.get("points", 0),
            "absent": t.get("absent", False)
        })

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
                history = json.load(hf)
        except: history = []
            
    match_number = len(history) + 1
    history.append({
        "match_num": match_number,
        "teams": current_match_data
    })
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    cfg = load_config()
    cfg["match"] = f"MATCH {match_number + 1}"
    save_config(cfg)

    for t in teams:
        t["kills"] = 0; t["placement_points"] = 0; t["points"] = 0; 
        # Preserve dynamic length on match reset
        t["players"] = [1] * len(t.get("players", [1, 1, 1, 1]))
        t["position"] = 0; t["elim_ts"] = 0
        
    save(teams)
    return jsonify({"success": True, "next_match": f"MATCH {match_number + 1}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
