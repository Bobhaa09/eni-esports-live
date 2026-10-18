from flask import Flask, request, jsonify, render_template_string, send_file, url_for
import json
import os
import time
import copy
import io
import shutil
from threading import Lock
from werkzeug.utils import secure_filename

app = Flask(__name__)
file_lock = Lock()

DATA_FILE = "teams.json"
CONFIG_FILE = "config.json"
HISTORY_FILE = "match_history.json"
THEMES_FILE = "themes.json"
UPLOAD_FOLDER = "static/logos"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

SERVER_LOGO_FILENAME = "server_logo.webp"
SERVER_LOGO_PATH = os.path.join(UPLOAD_FOLDER, SERVER_LOGO_FILENAME)

MAX_HISTORY = 20
undo_stack = []
redo_stack = []
connected_users = {}

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
        if 'wwcd' not in team: team['wwcd'] = 0
        
        k, p, tot = calculate_points(team)
        team["kills"] = k
        team["placement_points"] = p
        team["points"] = tot
    return teams

def auto_assign_winner_if_one_left(teams):
    """अगर सिर्फ 1 टीम जिंदा बचती है, तो उसे ऑटोमेटिक #1 पोजीशन और WWCD दे दी जाए"""
    active = [t for t in teams if not t.get("absent", False)]
    alive = [t for t in active if any(p == 1 for p in t.get("players", []))]
    if len(active) > 1 and len(alive) == 1:
        winner = alive[0]
        if winner.get("position", 0) != 1:
            winner["position"] = 1
            k, p, tot = calculate_points(winner)
            winner["placement_points"] = p
            winner["points"] = tot

def save(teams):
    auto_assign_winner_if_one_left(teams)
    recalculate_all(teams)
    with file_lock:
        if os.path.exists(DATA_FILE):
            try: shutil.copy(DATA_FILE, DATA_FILE + ".bak")
            except Exception: pass
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(teams, f, indent=2)

def load():
    if not os.path.exists(DATA_FILE): return []
    with file_lock:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                auto_assign_winner_if_one_left(data)
                return recalculate_all(data)
        except Exception:
            if os.path.exists(DATA_FILE + ".bak"):
                try:
                    with open(DATA_FILE + ".bak", "r", encoding="utf-8") as f:
                        data = json.load(f)
                        auto_assign_winner_if_one_left(data)
                        return recalculate_all(data)
                except Exception: return []
            return []

def save_state_for_undo():
    global undo_stack, redo_stack
    current_state = load()
    undo_stack.append(copy.deepcopy(current_state))
    if len(undo_stack) > MAX_HISTORY:
        undo_stack.pop(0)
    redo_stack.clear()

def load_config():
    default_cfg = {"tournament": "ESPORTS NATION INDIA", "match": "MATCH 1", "map": "ERANGEL", "total_matches": 10}
    if not os.path.exists(CONFIG_FILE): return default_cfg
    with file_lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**default_cfg, **json.load(f)}
        except Exception:
            return default_cfg

def save_config(config):
    with file_lock:
        if os.path.exists(CONFIG_FILE):
            try: shutil.copy(CONFIG_FILE, CONFIG_FILE + ".bak")
            except Exception: pass
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

BUILTIN_PRESETS = {
    "Classic Gold": {"primary": "#f2c400", "secondary": "#00e5ff", "bg_primary": "#061326", "bg_secondary": "#0d274c"},
    "Royal Blue": {"primary": "#00b4d8", "secondary": "#90e0ef", "bg_primary": "#03045e", "bg_secondary": "#023e8a"},
    "Crimson Red": {"primary": "#ff2a55", "secondary": "#ffb703", "bg_primary": "#1a050a", "bg_secondary": "#3d0a14"},
    "Cyber Purple": {"primary": "#b5179e", "secondary": "#4cc9f0", "bg_primary": "#10002b", "bg_secondary": "#240046"},
    "Neon Cyber": {"primary": "#00ffcc", "secondary": "#ff00ff", "bg_primary": "#050b14", "bg_secondary": "#120826"},
    "Sunset Orange": {"primary": "#ff7700", "secondary": "#ffbb00", "bg_primary": "#1a0f05", "bg_secondary": "#381a05"},
    "Emerald Neon": {"primary": "#00ff88", "secondary": "#00e5ff", "bg_primary": "#041a10", "bg_secondary": "#083822"},
    "Rose Gold": {"primary": "#ff85a1", "secondary": "#fbb1bd", "bg_primary": "#1f0a10", "bg_secondary": "#3d1421"}
}

def load_themes():
    default_data = {
        "admin_theme": "Classic Gold",
        "matches": {
            "MATCH 1": copy.deepcopy(BUILTIN_PRESETS["Classic Gold"]),
            "MATCH 2": copy.deepcopy(BUILTIN_PRESETS["Royal Blue"]),
            "MATCH 3": copy.deepcopy(BUILTIN_PRESETS["Crimson Red"])
        }
    }
    if not os.path.exists(THEMES_FILE): return default_data
    with file_lock:
        try:
            with open(THEMES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "matches" not in data: data["matches"] = default_data["matches"]
                if "admin_theme" not in data: data["admin_theme"] = "Classic Gold"
                return data
        except Exception: return default_data

def save_themes(data):
    with file_lock:
        with open(THEMES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

# =========================================================
# PROFESSIONAL ADMIN PAGE HTML & JS
# =========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>ESPORTS NATION INDIA | PROFESSIONAL DASHBOARD</title>

<style id="adminDynamicTheme">
@import url('https://fonts.googleapis.com/css2?family=Teko:wght@500;600;700&family=Rajdhani:wght@500;600;700;800&display=swap');

:root {
    --bg-main: #020408;
    --card-bg: rgba(13, 22, 38, 0.88);
    --gold: #f2c400;
    --cyan: #00e5ff;
    --red: #ff2a55;
    --green: #00ff66;
    --glass-border: rgba(255,255,255,0.1);
}

* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    margin: 0; padding: 0;
    background: radial-gradient(circle at top, #091325 0%, var(--bg-main) 100%);
    color: #ffffff;
    font-family: 'Rajdhani', sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

.sticky-header {
    position: sticky; top: 0; z-index: 1000;
    background: rgba(3, 7, 16, 0.95); backdrop-filter: blur(18px);
    border-bottom: 1px solid var(--glass-border); padding: 12px 20px;
    display: flex; justify-content: space-between; align-items: center;
    box-shadow: 0 10px 30px rgba(0,0,0,0.7);
    flex-wrap: wrap; gap: 10px;
}

.menu-dots-btn {
    background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border);
    color: var(--gold); padding: 6px 14px; border-radius: 8px; cursor: pointer;
    font-size: 18px; font-weight: 800; margin-right: 12px; transition: all 0.3s ease;
}
.menu-dots-btn:hover { background: rgba(242,196,0,0.15); border-color: var(--gold); box-shadow: 0 0 12px rgba(242,196,0,0.4); }

.brand-container { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.server-logo { width: 40px; height: 40px; object-fit: contain; border-radius: 8px; border: 1px solid var(--gold); box-shadow: 0 0 10px rgba(242,196,0,0.3); }
.brand h1 { margin: 0; font-size: 26px; font-family: 'Teko', sans-serif; color: var(--gold); letter-spacing: 1.5px; text-shadow: 0 0 12px rgba(242,196,0,0.4); line-height: 1; }
.brand span { font-size: 11px; color: var(--cyan); font-weight: 700; letter-spacing: 2.5px; display: block; }

.sync-status {
    display: flex; align-items: center; gap: 6px; margin-left: 10px; font-size: 11px; font-weight: 800; letter-spacing: 1px;
    padding: 5px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.4);
}
.sync-dot { width: 8px; height: 8px; border-radius: 50%; }
.sync-live { color: var(--green); border-color: rgba(0, 255, 102, 0.3); }
.sync-live .sync-dot { background: var(--green); box-shadow: 0 0 8px var(--green); animation: pulse-sync 1.5s infinite; }
.sync-offline { color: var(--red); border-color: rgba(255, 42, 85, 0.3); }
.sync-offline .sync-dot { background: var(--red); box-shadow: 0 0 8px var(--red); }
@keyframes pulse-sync { 0% { opacity: 1; transform:scale(1); } 50% { opacity: 0.5; transform:scale(0.8); } 100% { opacity: 1; transform:scale(1); } }

.live-stats { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.history-controls { display: flex; gap: 5px; margin-right: 10px; border-right: 1px solid rgba(255,255,255,0.1); padding-right: 10px; }
.btn-undo-redo { 
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.2); 
    color: white; border-radius: 6px; width: 36px; height: 36px; 
    display: flex; align-items: center; justify-content: center; font-size: 18px; 
    cursor: pointer; transition: 0.2s; 
}
.btn-undo-redo:hover { background: rgba(0,229,255,0.2); border-color: var(--cyan); }

.stat-badge {
    background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.2);
    padding: 4px 12px; border-radius: 6px; display: flex; flex-direction: column; align-items: center; min-width: 65px;
}
.stat-badge span { font-size: 9px; color: #9da9b8; font-weight: 700; text-transform: uppercase; }
.stat-badge strong { font-size: 16px; color: var(--cyan); font-weight: 800; line-height: 1.1; }
.stat-badge.players strong { color: var(--green); }
.stat-badge.players { background: rgba(0, 255, 102, 0.08); border-color: rgba(0, 255, 102, 0.2); }

.btn-top-reset {
    background: linear-gradient(135deg, #b30000, #ff1a1a);
    color: #fff;
    border: 1px solid #ff4d4d;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 800;
    border-radius: 6px;
    cursor: pointer;
    box-shadow: 0 0 10px rgba(255, 26, 26, 0.4);
    transition: 0.2s;
    font-family: 'Rajdhani', sans-serif;
}
.btn-top-reset:hover { background: #ff3333; transform: scale(1.05); }

.container { padding: 20px; max-width: 1400px; margin: 0 auto; flex: 1; width: 100%; }

.glass-card {
    background: var(--card-bg); backdrop-filter: blur(14px); border: 1px solid var(--glass-border);
    border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.5);
}

.links-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
.obs-link {
    background: linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)); border: 1px solid var(--glass-border);
    padding: 12px; border-radius: 8px; text-align: center; text-decoration: none; color: #b0c4de; font-size: 13px; font-weight: 700;
    transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
.obs-link:hover { background: rgba(0,229,255,0.12); border-color: var(--cyan); color: white; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,229,255,0.25); }

input, select, textarea {
    background: rgba(0,0,0,0.6); color: white; border: 1px solid rgba(255,255,255,0.15); padding: 12px; border-radius: 8px;
    font-size: 14px; font-family: 'Rajdhani', sans-serif; font-weight: 700; width: 100%; outline: none; transition: all 0.3s ease;
}
input:focus, select:focus, textarea:focus { border-color: var(--cyan); box-shadow: 0 0 12px rgba(0,229,255,0.35); background: rgba(0,0,0,0.8); }

.btn {
    border: none; border-radius: 8px; padding: 12px 16px; cursor: pointer; font-weight: 800; font-size: 14px; font-family: 'Rajdhani', sans-serif;
    letter-spacing: 1px; text-transform: uppercase; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    display: inline-flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}
.btn:hover { transform: translateY(-2px); filter: brightness(1.15); box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
.btn-primary { background: linear-gradient(135deg, #0077b6, #00bfff); color: #fff; border: 1px solid #00bfff; }
.btn-gold { background: linear-gradient(135deg, #c89d00, var(--gold)); color: #040911; }
.btn-green { background: linear-gradient(135deg, #00994d, var(--green)); color: #040911; }
.btn-danger { background: linear-gradient(135deg, #8a0014, var(--red)); color: white; border: 1px solid var(--red); }
.btn-orange { background: linear-gradient(135deg, #cc7a00, #ff9900); color: white; border: 1px solid #ff9900; }

.search-bar { border-color: rgba(242,196,0,0.4) !important; font-size:16px; margin-bottom: 15px; }

/* Teams Grid & Cards */
.teams-grid { display: grid; grid-template-columns: 1fr; gap: 16px; transition: 0.3s; }
@media(min-width: 768px) { .teams-grid { grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); } }
.teams-grid.compact-mode { grid-template-columns: 1fr; gap: 8px; }
@media(min-width: 768px) { .teams-grid.compact-mode { grid-template-columns: repeat(auto-fill, minmax(450px, 1fr)); } }

.team-card {
    background: linear-gradient(160deg, rgba(16,28,48,0.92), rgba(6,12,24,0.97)); border: 1px solid var(--glass-border);
    border-left: 4px solid var(--cyan); border-radius: 12px; padding: 14px; transition: all 0.3s ease;
    position: relative; overflow: hidden; box-shadow: 0 6px 20px rgba(0,0,0,0.4);
}
.team-card.eliminated { 
    border-left-color: var(--red) !important; 
    border: 1px solid rgba(255,42,85,0.8) !important; 
    background: linear-gradient(160deg, rgba(45, 10, 18, 0.98), rgba(20, 3, 6, 0.99)) !important; 
    box-shadow: 0 0 20px rgba(255,42,85,0.4) !important; 
}
.team-card.not-present { border-left-color: #555; background: linear-gradient(160deg, rgba(20,20,20,0.9), rgba(10,10,10,0.95)); opacity: 0.4; }

/* Chicken Dinner Winner Golden Box Highlight */
.team-card.winner {
    border: 2px solid var(--gold) !important;
    border-left: 6px solid var(--gold) !important;
    background: linear-gradient(160deg, rgba(70, 52, 6, 0.98), rgba(30, 22, 2, 0.99)) !important;
    box-shadow: 0 0 35px rgba(242, 196, 0, 0.75) !important;
    animation: goldPulse 2s infinite alternate;
}
@keyframes goldPulse {
    0% { box-shadow: 0 0 20px rgba(242, 196, 0, 0.5); }
    100% { box-shadow: 0 0 45px rgba(242, 196, 0, 0.95); }
}

.tc-header { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.tc-slot { background: rgba(255,255,255,0.08); padding: 4px 8px; border-radius: 6px; font-weight: 800; color: #9da9b8; font-size: 13px; }
.tc-name { flex: 1; border: none; background: transparent; padding: 0; font-size: 18px; color: var(--gold); text-transform: uppercase; font-weight: 800; min-width: 110px; }
.btn-elim, .btn-not-present { padding: 5px 10px; font-size:11px; font-weight: 800; border-radius: 6px; cursor: pointer; transition: 0.3s; }
.btn-elim { background: rgba(255, 42, 85, 0.15); border: 1px solid var(--red); color: var(--red); }
.btn-elim:hover { background: var(--red); color: white; }
.btn-not-present { background: rgba(255, 42, 85, 0.15); border: 1px solid var(--red); color: var(--red); }
.btn-not-present.is-present { background: rgba(0, 255, 102, 0.15); border-color: var(--green); color: var(--green); }

.player-count-select {
    background: rgba(0, 229, 255, 0.1); color: var(--cyan); border: 1px solid rgba(0, 229, 255, 0.3);
    border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 800; cursor: pointer; outline: none;
    font-family: 'Rajdhani', sans-serif;
}
.player-count-select option { background: #03060f; color: white; }

.tc-players { display: flex; justify-content: center; gap: 10px; margin-bottom: 12px; background: rgba(0,0,0,0.3); padding: 8px 10px; border-radius: 8px; align-items: center; }
.player-node { 
    width: 36px; height: 36px; border-radius: 50%; 
    background: linear-gradient(135deg, var(--green), #00b347); 
    display: flex; align-items: center; justify-content: center; 
    color: #040911; font-weight: 800; font-size: 12px; cursor: pointer; 
    box-shadow: 0 0 10px rgba(0,255,102,0.4); border: 2px solid rgba(255,255,255,0.7); 
    transition: all 0.2s ease; 
}
.player-node:hover { transform: scale(1.1); filter: brightness(1.15); }
.player-node.dead { 
    background: linear-gradient(135deg, var(--red), #b3002d); 
    color: #ffffff; 
    border-color: rgba(255,255,255,0.4); 
    box-shadow: 0 0 10px rgba(255,42,85,0.4); 
}

.tc-controls { display: flex; gap: 8px; margin-bottom: 12px; align-items:center; }
.tc-controls select { padding: 9px 8px; font-size: 13px; }
.btn-icon { width: 42px; height: 42px; padding: 0; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.15); color: white; font-size: 20px; font-weight:bold; border-radius: 8px; cursor: pointer; }
.btn-icon.plus { background: rgba(0, 255, 102, 0.1); border-color: rgba(0, 255, 102, 0.4); color: var(--green); }

.tc-stats { display: flex; justify-content: space-between; background: rgba(0,0,0,0.5); border-radius: 8px; padding: 8px 10px; border: 1px solid rgba(255,255,255,0.05); }
.tc-stat-box { text-align: center; flex: 1; }
.tc-stat-box span { display: block; font-size: 9px; color: #7a8a9e; font-weight: 700; text-transform: uppercase; margin-bottom:2px;}
.tc-stat-box strong { font-size: 16px; font-weight: 800; }
.tc-stat-box.fin strong { color: var(--green); }
.tc-stat-box.pts strong { color: var(--cyan); }
.tc-stat-box.tot strong { color: var(--gold); font-size: 18px; }
.logo-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 11px; background: rgba(255,255,255,0.03); padding: 6px 10px; border-radius: 8px; margin-top: 10px; }
.logo-row img { width: 24px; height: 24px; object-fit: contain; border-radius: 4px; }

/* COMPACT MODE */
.compact-mode .team-card { padding: 10px 12px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.compact-mode .tc-header { margin: 0; flex: 1; min-width: 150px; }
.compact-mode .tc-stats, .compact-mode .logo-row, .compact-mode .btn-elim, .compact-mode .btn-not-present, .compact-mode .tc-controls select, .compact-mode .player-count-select { display: none; }
.compact-mode .tc-players { margin: 0; padding: 4px; gap: 6px; flex: 1; background: transparent; border: none; min-width: 120px; }
.compact-mode .player-node { width: 26px; height: 26px; font-size: 10px; }
.compact-mode .tc-controls { margin: 0; flex: 0; justify-content: flex-end; }
.compact-mode .btn-icon { width: 34px; height: 34px; font-size: 18px; }

/* Sidebar & Modals */
.sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(5px); z-index: 1500; display: none; }
.sidebar-overlay.show { display: block; }
.sidebar-menu { position: fixed; top: 0; left: -280px; width: 280px; height: 100%; background: linear-gradient(180deg, #070e1c, #03060f); border-right: 1px solid var(--glass-border); z-index: 2000; transition: 0.3s; box-shadow: 5px 0 30px rgba(0,0,0,0.8); display: flex; flex-direction: column; padding: 20px; overflow-y:auto; }
.sidebar-menu.open { left: 0; }
.sidebar-link { padding: 13px 15px; color: #b0c4de; text-decoration: none; font-weight: 700; font-size: 14px; border-radius: 8px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); margin-bottom: 10px; display: flex; align-items: center; gap:10px; transition: 0.3s; }
.sidebar-link:hover { background: rgba(242,196,0,0.1); border-color: var(--gold); color: white; transform: translateX(4px); }
.sidebar-link.danger-link:hover { background: rgba(255,42,85,0.15); border-color: var(--red); }

.modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(8px); z-index: 3000; display: none; align-items: center; justify-content: center; padding: 20px; }
.modal.show { display: flex; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from{opacity:0; transform:scale(0.95);} to{opacity:1; transform:scale(1);} }
.modal-content { background: linear-gradient(135deg, #0d1626, #070e1c); border: 1px solid var(--gold); border-radius: 12px; width: 100%; max-width: 650px; max-height: 85vh; overflow-y: auto; padding: 25px; box-shadow: 0 15px 50px rgba(0,0,0,0.8); }

.toast { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%) translateY(20px); background: linear-gradient(135deg, var(--gold), #c89d00); color: #000; padding: 12px 30px; border-radius: 30px; font-weight: 800; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 10px 30px rgba(242, 196, 0, 0.4); opacity: 0; visibility: hidden; transition: 0.3s; z-index: 9999; }
.toast.show { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }

.podium { display: flex; align-items: flex-end; justify-content: center; gap: 15px; margin: 25px 0; height: 180px; }
.podium-step { background: rgba(0,0,0,0.4); border: 1px solid var(--glass-border); border-radius: 8px 8px 0 0; display: flex; flex-direction: column; align-items: center; padding-top: 10px; width: 110px; }
.podium-step.pos-1 { height: 170px; border-color: var(--gold); background: rgba(242,196,0,0.2); }
.podium-step.pos-2 { height: 130px; border-color: silver; background: rgba(192,192,192,0.2); }
.podium-step.pos-3 { height: 100px; border-color: #cd7f32; background: rgba(205,127,50,0.2); }
.podium-rank { font-size: 32px; font-weight: 800; font-family: 'Teko', sans-serif; line-height: 1; }

.site-footer {
    background: rgba(3, 7, 16, 0.95); border-top: 1px solid var(--glass-border);
    padding: 20px 25px; margin-top: auto; display: flex; justify-content: space-between;
    align-items: center; flex-wrap: wrap; gap: 15px; backdrop-filter: blur(10px);
}
.footer-brand { display: flex; align-items: center; gap: 10px; font-family: 'Teko', sans-serif; font-size: 20px; color: var(--gold); letter-spacing: 1px; }
.footer-brand img { width: 28px; height: 28px; object-fit: contain; border-radius: 4px; }
.footer-links { display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
.social-badge {
    background: rgba(255,255,255,0.04); border: 1px solid var(--glass-border); color: #b0c4de;
    padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 700; text-decoration: none;
    display: inline-flex; align-items: center; gap: 6px; transition: 0.3s;
}
.social-badge:hover { border-color: var(--cyan); color: white; background: rgba(0,229,255,0.1); transform: translateY(-2px); }
.social-badge.discord:hover { border-color: #5865F2; background: rgba(88,101,242,0.15); }
.social-badge.insta:hover { border-color: #E1306C; background: rgba(225,48,108,0.15); }
.social-badge.youtube:hover { border-color: #FF0000; background: rgba(255,0,0,0.15); }
.footer-copy { font-size: 12px; color: #7a8a9e; font-weight: 600; text-align: center; width: 100%; border-top: 1px solid rgba(255,255,255,0.03); padding-top: 10px; margin-top: 5px; }
@media(min-width: 768px) { .footer-copy { width: auto; border-top: none; padding-top: 0; margin-top: 0; } }
</style>
</head>
<body>

<!-- Sidebar Menu (3 Dots) -->
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleMenu()"></div>
<div class="sidebar-menu" id="sidebarMenu">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; padding-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.1);">
        <h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:26px;">OPTIONS</h2>
        <button class="menu-dots-btn" style="margin:0; padding:2px 8px;" onclick="toggleMenu()">✕</button>
    </div>
    
    <a href="#" class="sidebar-link" style="color:#00ff66; border-color:rgba(0,255,102,0.3);" onclick="toggleMenu(); openThemeManagerModal();">
        <span style="font-size:18px;">🎨</span> Match & Admin Themes
    </a>
    <a href="#" class="sidebar-link" style="color:var(--gold);" onclick="toggleMenu(); openFinalResultModal();">
        <span style="font-size:18px;">🏆</span> Final Tournament Result
    </a>
    <a href="#" class="sidebar-link" onclick="toggleMenu(); openHistoryModal();">
        <span style="font-size:18px;">📚</span> Match Archive (Saved Matches)
    </a>
    <a href="#" class="sidebar-link danger-link" style="margin-top:auto;" onclick="toggleMenu(); clearMatchHistory();">
        <span style="font-size:18px;">🗑️</span> Clear Entire History
    </a>
</div>

<!-- Theme Manager Modal (OBS Overlays + Admin Panel) -->
<div class="modal" id="themeManagerModal">
    <div class="modal-content">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:12px;">
            <h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:28px;">🎨 GRAPHICS & ADMIN THEMES</h2>
            <button class="btn btn-danger" style="padding:4px 10px; font-size:12px;" onclick="closeModal('themeManagerModal')">✕ CLOSE</button>
        </div>

        <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:14px; margin-bottom:18px;">
            <h3 style="margin:0 0 10px 0; font-family:'Teko'; font-size:20px; color:var(--gold);">🖥️ ADMIN PANEL THEME (LIVE LOOK)</h3>
            <label style="font-size:12px; color:#b0c4de; font-weight:700;">CHOOSE ADMIN PANEL PALETTE</label>
            <div style="display:flex; gap:10px; margin-top:6px;">
                <select id="adminThemeSelect" style="flex:1; border-color:var(--gold);"></select>
                <button class="btn btn-gold" style="padding:8px 16px;" onclick="saveAdminTheme()">APPLY ADMIN THEME</button>
            </div>
        </div>

        <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:14px;">
            <h3 style="margin:0 0 10px 0; font-family:'Teko'; font-size:20px; color:var(--cyan);">📡 OBS OVERLAYS MATCH THEME</h3>
            <div style="margin-bottom:12px;">
                <label style="font-size:12px; color:var(--gold); font-weight:800;">SELECT OVERLAY MATCH</label>
                <select id="tmMatchSelect" onchange="onTmMatchChange()" style="margin-top:5px; border-color:var(--gold);"></select>
            </div>

            <div style="margin-bottom:15px;">
                <label style="font-size:12px; color:var(--cyan); font-weight:800;">OVERLAY COLOR PRESET</label>
                <select id="tmPresetSelect" style="margin-top:5px; border-color:var(--cyan);"></select>
            </div>

            <button class="btn btn-primary" style="width:100%;" onclick="saveMatchTheme()">💾 SAVE THEME FOR OVERLAY</button>
        </div>
    </div>
</div>

<!-- Final Result Modal -->
<div class="modal" id="finalResultModal"><div class="modal-content"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:12px;"><h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:30px;">🏆 FINAL TOURNAMENT RESULT</h2><button class="btn btn-danger" style="padding:6px 12px; font-size:12px;" onclick="closeModal('finalResultModal')">CLOSE</button></div><div id="podiumContainer" class="podium"></div><div id="finalListContainer"></div></div></div>

<!-- History Archive Modal (Full Match Data Viewer) -->
<div class="modal" id="historyModal">
    <div class="modal-content" style="max-width:750px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:12px;">
            <h2 style="margin:0; font-family:'Teko'; color:var(--gold); font-size:30px;">📚 MATCH ARCHIVE (SAVED MATCHES)</h2>
            <button class="btn btn-danger" style="padding:6px 12px; font-size:12px;" onclick="closeModal('historyModal')">CLOSE</button>
        </div>
        <div id="historyListContainer">Loading...</div>
    </div>
</div>

<div class="sticky-header">
    <div class="brand-container">
        <button class="menu-dots-btn" onclick="toggleMenu()">⋮</button>
        <img src="/static/logos/server_logo.webp" class="server-logo" alt="Logo">
        <div class="brand"><h1>ESPORTS NATION INDIA</h1><span>ADMIN BROADCAST DASHBOARD</span></div>
        <div id="syncIndicator" class="sync-status sync-live"><div class="sync-dot"></div><span id="syncText">ONLINE</span></div>
        <div class="sync-status" style="color:var(--gold); border-color:rgba(242,196,0,0.3);"><span>USERS: <strong id="connectedUsersCount">1</strong></span></div>
    </div>
    
    <div class="live-stats">
        <button class="btn-top-reset" onclick="uiResetAll()" title="Reset all data to 0 and start completely fresh">⚠️ RESET ALL</button>
        <div class="history-controls">
            <button class="btn-undo-redo" onclick="uiUndo()" title="Undo">↩️</button>
            <button class="btn-undo-redo" onclick="uiRedo()" title="Redo">↪️</button>
        </div>
        <div class="stat-badge"><span>Progress</span><strong id="topProgress" style="color:var(--gold);">0%</strong></div>
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
            <a href="/overlay/wwcd" target="_blank" class="obs-link" style="color:var(--gold); border-color:rgba(242,196,0,0.4);">🍗 WWCD SCREEN</a>
        </div>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px,1fr)); gap:15px; margin-bottom:15px;">
        <div class="glass-card" style="margin:0;">
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div style="flex:1"><label style="font-size:11px; color:var(--gold); font-weight:700;">TOURNAMENT</label><input id="tourneyName" type="text" value="ESPORTS NATION INDIA"></div>
                <div style="width:90px"><label style="font-size:11px; color:var(--gold); font-weight:700;">MATCH</label><input id="matchName" type="text" value="MATCH 1"></div>
                <div style="width:80px"><label style="font-size:11px; color:var(--gold); font-weight:700;">TOTAL M.</label><input id="totalMatchesInput" type="number" value="10" min="1"></div>
            </div>
            <div style="margin-bottom:10px;"><label style="font-size:11px; color:var(--gold); font-weight:700;">MAP</label>
                <select id="mapName"><option>ERANGEL</option><option>MIRAMAR</option><option>RONDO</option></select>
            </div>
            <button class="btn btn-gold" style="width:100%" onclick="updateConfig()">SAVE MATCH INFO</button>
        </div>

        <div class="glass-card" style="margin:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                <label style="font-size:12px; font-weight:800; color:var(--cyan);">📋 DISCORD SLOT LIST</label>
                <div style="display:flex; gap:5px;">
                    <button class="btn btn-gold" style="padding:2px 8px; font-size:12px;" onclick="adjustSlots(1)">➕ Slot</button>
                    <button class="btn btn-danger" style="padding:2px 8px; font-size:12px;" onclick="adjustSlots(-1)">➖ Slot</button>
                </div>
            </div>
            <textarea id="slotInput" style="height:55px; margin-bottom:10px;" placeholder="Paste Discord slots..."></textarea>
            <button class="btn btn-primary" style="width:100%" onclick="importSlots()">IMPORT TEAMS</button>
        </div>
    </div>

    <div class="glass-card" style="display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between; align-items:center;">
        <button id="btnCompact" class="btn btn-primary" style="background:transparent; border:1px solid var(--cyan); color:var(--cyan);" onclick="toggleCompactMode()">📋 COMPACT VIEW</button>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button class="btn btn-danger" onclick="resetTeams()">🗑️ DELETE ALL</button>
            <button class="btn btn-green" onclick="resetMatchState()">🔄 NEW MATCH</button>
            <button class="btn btn-orange" onclick="saveMatchOverall()">💾 SAVE MATCH</button>
        </div>
    </div>

    <input type="text" id="searchInput" class="search-bar" placeholder="🔍 Search Team Name or Slot..." oninput="filterTeams()">
    <div id="teamsContainer" class="teams-grid"></div>
</div>

<footer class="site-footer">
    <div class="footer-brand">
        <img src="/static/logos/server_logo.webp" alt="Logo">
        <span>ESPORTS NATION INDIA</span>
    </div>
    <div class="footer-links">
        <a href="https://discord.gg/esportsindia" target="_blank" class="social-badge discord">🎮 Discord Server</a>
        <a href="https://www.instagram.com/esportsnation.india?igsh=ZG1zc3dhOGphN3h2" target="_blank" class="social-badge insta">📷 Instagram</a>
        <a href="https://youtube.com/@esportnationindia?si=LcxdyjbGXS5NaWLy" target="_blank" class="social-badge youtube">▶️ YouTube Channel</a>
    </div>
    <div class="footer-copy">© 2026 Esports Nation India. All Rights Reserved.</div>
</footer>

<div id="toast" class="toast">Action Successful</div>

<script>
let teamsData = []; let historyData = []; let isCompactMode = false; let wasOffline = false;
const clientSessionId = "prod_" + Math.random().toString(36).substring(2, 10);

async function checkServerStatus() {
    try {
        const res = await fetch("/api/ping?cid=" + clientSessionId);
        if(!res.ok) throw new Error();
        const d = await res.json();
        document.getElementById("syncIndicator").className = "sync-status sync-live";
        document.getElementById("syncText").innerText = "ONLINE";
        document.getElementById("connectedUsersCount").innerText = d.users || 1;
        if(wasOffline) { showToast("Connection Restored 🟢"); wasOffline = false; }
    } catch(e) {
        document.getElementById("syncIndicator").className = "sync-status sync-offline";
        document.getElementById("syncText").innerText = "OFFLINE";
        if(!wasOffline) { showToast("Connection Lost 🔴"); wasOffline = true; }
    }
}
setInterval(checkServerStatus, 3000); checkServerStatus();

async function syncAdminData() {
    try {
        const res = await fetch("/api/teams?t=" + new Date().getTime());
        if (!res.ok) return;
        teamsData = await res.json();
        
        const activeTeams = teamsData.filter(t => !t.absent);
        const aliveTeams = activeTeams.filter(t => t.players.some(p => p === 1));
        
        let at = aliveTeams.length;
        let ap = 0;

        // Auto #1 trigger when only 1 team is left
        if(activeTeams.length > 1 && at === 1) {
            const winner = aliveTeams[0];
            if(winner.position !== 1) {
                await fetch("/api/update", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({id: winner.id, position: 1})
                });
                winner.position = 1;
            }
        }

        teamsData.forEach(team => {
            if(!team.absent) {
                let alive = team.players.filter(p=>p===1).length;
                ap += alive;
            }
            const card = document.getElementById(`card-${team.id}`);
            if(card) {
                document.getElementById(`kills-${team.id}`).innerText = team.kills;
                document.getElementById(`pts-${team.id}`).innerText = team.points;
                document.getElementById(`ov-${team.id}`).innerText = team.overall_pts || 0;
                
                const posSel = document.getElementById(`pos-sel-${team.id}`);
                if(posSel && String(posSel.value) !== String(team.position)) {
                    posSel.value = team.position;
                }
                
                team.players.forEach((val, idx) => {
                    const pNode = document.getElementById(`pbtn-${team.id}-${idx}`);
                    if(pNode) { 
                        if(val) pNode.classList.remove("dead"); 
                        else pNode.classList.add("dead"); 
                    }
                });

                const isDead = (team.players.filter(p=>p===1).length === 0);
                if(isDead && team.position > 0) card.classList.add("eliminated");
                else card.classList.remove("eliminated");

                // Highlight WWCD winner box in Gold when exactly 1 team remains OR position == 1
                const isWinner = (!team.absent && ((activeTeams.length > 1 && at === 1 && aliveTeams[0].id === team.id) || team.position === 1));
                if(isWinner) {
                    card.classList.add("winner");
                    let badge = document.getElementById(`wwcd-badge-${team.id}`);
                    if(!badge) {
                        const tag = document.createElement("span");
                        tag.id = `wwcd-badge-${team.id}`;
                        tag.style.cssText = "background:var(--gold); color:#000; font-weight:800; font-size:11px; padding:2px 8px; border-radius:4px; margin-left:6px;";
                        tag.innerText = "👑 WWCD #1";
                        card.querySelector(".tc-header").appendChild(tag);
                    }
                } else {
                    card.classList.remove("winner");
                    const badge = document.getElementById(`wwcd-badge-${team.id}`);
                    if(badge) badge.remove();
                }
            }
        });
        document.getElementById("topTeams").innerText = at;
        document.getElementById("topPlayers").innerText = ap;
    } catch(e){}
}
setInterval(syncAdminData, 1000);

function toggleMenu() { document.getElementById("sidebarMenu").classList.toggle("open"); document.getElementById("sidebarOverlay").classList.toggle("show"); }
function closeModal(id) { document.getElementById(id).classList.remove("show"); }
function showToast(msg) { const t = document.getElementById("toast"); t.innerText = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2000); }

function toggleCompactMode() {
    isCompactMode = !isCompactMode;
    const c = document.getElementById("teamsContainer"); const b = document.getElementById("btnCompact");
    if(isCompactMode) { c.classList.add("compact-mode"); b.innerText = "🗂️ NORMAL VIEW"; b.style.background = "var(--cyan)"; b.style.color = "black"; }
    else { c.classList.remove("compact-mode"); b.innerText = "📋 COMPACT VIEW"; b.style.background = "transparent"; b.style.color = "var(--cyan)"; }
}

let allThemesData = { matches: {}, admin_theme: "Classic Gold" };
let builtinPresetsData = {};

function applyAdminThemeLocally(themeName) {
    const t = builtinPresetsData[themeName] || builtinPresetsData["Classic Gold"];
    if(!t) return;
    const styleEl = document.getElementById("adminDynamicTheme");
    if(styleEl) {
        document.documentElement.style.setProperty('--gold', t.primary);
        document.documentElement.style.setProperty('--cyan', t.secondary);
        document.documentElement.style.setProperty('--bg-main', t.bg_primary);
        document.documentElement.style.setProperty('--card-bg', `rgba(13, 22, 38, 0.9)`);
        document.body.style.background = `radial-gradient(circle at top, ${t.bg_secondary} 0%, ${t.bg_primary} 100%)`;
    }
}

async function loadThemeSettings() {
    try {
        const res = await fetch("/api/themes");
        const d = await res.json();
        allThemesData = d.themes || { matches: {}, admin_theme: "Classic Gold" };
        builtinPresetsData = d.presets || {};
        
        const currentAdminTh = allThemesData.admin_theme || "Classic Gold";
        applyAdminThemeLocally(currentAdminTh);
    } catch(e){}
}

async function openThemeManagerModal() {
    document.getElementById("themeManagerModal").classList.add("show");
    const [cfgRes, thmRes] = await Promise.all([fetch("/api/config"), fetch("/api/themes")]);
    const cfg = await cfgRes.json();
    const thmJson = await thmRes.json();
    allThemesData = thmJson.themes || { matches: {}, admin_theme: "Classic Gold" };
    builtinPresetsData = thmJson.presets || {};

    // Fill Admin theme presets
    const admSel = document.getElementById("adminThemeSelect");
    admSel.innerHTML = "";
    Object.keys(builtinPresetsData).forEach(p => {
        const sel = (allThemesData.admin_theme === p) ? "selected" : "";
        admSel.innerHTML += `<option value="${p}" ${sel}>${p}</option>`;
    });

    // Fill OBS Match select
    const totalM = parseInt(cfg.total_matches) || 10;
    const matchSel = document.getElementById("tmMatchSelect");
    matchSel.innerHTML = "";
    for(let i = 1; i <= totalM; i++) {
        const mName = `MATCH ${i}`;
        const sel = (cfg.match && cfg.match.toUpperCase() === mName) ? "selected" : "";
        matchSel.innerHTML += `<option value="${mName}" ${sel}>${mName}</option>`;
    }

    // Fill OBS Presets
    const preSel = document.getElementById("tmPresetSelect");
    preSel.innerHTML = "";
    Object.keys(builtinPresetsData).forEach(p => {
        preSel.innerHTML += `<option value="${p}">${p}</option>`;
    });

    onTmMatchChange();
}

function onTmMatchChange() {
    const mKey = document.getElementById("tmMatchSelect").value;
    const t = (allThemesData.matches && allThemesData.matches[mKey]) ? allThemesData.matches[mKey] : builtinPresetsData["Classic Gold"];
    document.getElementById("tmPresetSelect").value = t.preset || "Classic Gold";
}

async function saveAdminTheme() {
    const chosen = document.getElementById("adminThemeSelect").value;
    allThemesData.admin_theme = chosen;
    await fetch("/api/themes", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ admin_theme: chosen })
    });
    applyAdminThemeLocally(chosen);
    showToast(`Admin Theme Applied: ${chosen}! ✨`);
    closeModal('themeManagerModal');
}

async function saveMatchTheme() {
    const mKey = document.getElementById("tmMatchSelect").value;
    const pName = document.getElementById("tmPresetSelect").value;
    const themeObj = { preset: pName, ...builtinPresetsData[pName] };
    if(!allThemesData.matches) allThemesData.matches = {};
    allThemesData.matches[mKey] = themeObj;
    await fetch("/api/themes", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ match_key: mKey, theme: themeObj }) });
    showToast(`Overlay Theme Saved for ${mKey}! 🎨`);
    closeModal('themeManagerModal');
}

async function openFinalResultModal() {
    document.getElementById("finalResultModal").classList.add("show");
    const res = await fetch("/api/teams"); const data = await res.json();
    const sorted = data.filter(t=>!t.absent).sort((a,b) => (b.overall_pts||0) - (a.overall_pts||0));
    if(sorted.length < 3) { document.getElementById("podiumContainer").innerHTML = "Not enough data."; return; }
    const p1 = sorted[0], p2 = sorted[1], p3 = sorted[2];
    document.getElementById("podiumContainer").innerHTML = `
        <div class="podium-step pos-2"><div class="podium-rank">#2</div><div style="font-weight:800;">${p2.name}</div><div style="color:var(--cyan);">${p2.overall_pts} PTS</div></div>
        <div class="podium-step pos-1"><div class="podium-rank">#1 👑</div><div style="font-weight:800; color:var(--gold);">${p1.name}</div><div style="color:#fff;">${p1.overall_pts} PTS</div></div>
        <div class="podium-step pos-3"><div class="podium-rank">#3</div><div style="font-weight:800;">${p3.name}</div><div style="color:var(--cyan);">${p3.overall_pts} PTS</div></div>
    `;
    let tbl = `<table style="width:100%; border-collapse:collapse; font-size:14px; margin-top:15px;"><tr style="color:var(--gold); border-bottom:1px solid rgba(255,255,255,0.15);"><th align="left">Rank</th><th align="left">Team</th><th>WWCD</th><th>Kills</th><th>Total Pts</th></tr>`;
    sorted.forEach((t, i) => { tbl += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td>#${i+1}</td><td><b>${t.name}</b></td><td align="center">${t.wwcd||0}</td><td align="center">${t.overall_kills}</td><td align="center" style="color:var(--gold)"><b>${t.overall_pts}</b></td></tr>`; });
    document.getElementById("finalListContainer").innerHTML = tbl + `</table>`;
}

async function openHistoryModal() {
    document.getElementById("historyModal").classList.add("show");
    const res = await fetch("/api/history"); historyData = await res.json();
    const c = document.getElementById("historyListContainer");
    if(!historyData || historyData.length === 0) { 
        c.innerHTML = "<p style='color:#9da9b8; text-align:center;'>No saved match records yet.</p>"; 
        return; 
    }
    
    let html = "";
    historyData.slice().reverse().forEach((m, idx) => {
        let teamsList = m.teams || [];
        teamsList.sort((a,b) => (b.total_pts || 0) - (a.total_pts || 0));

        let rowsHtml = "";
        teamsList.forEach((tm, rIdx) => {
            rowsHtml += `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.05); font-size:13px;">
                    <td style="padding:6px 8px; color:var(--gold);">#${tm.position > 0 ? tm.position : (rIdx+1)}</td>
                    <td style="font-weight:700;">${tm.name}</td>
                    <td align="center" style="color:var(--green);">${tm.kills || 0}</td>
                    <td align="center" style="color:var(--cyan);">${tm.placement_points || 0}</td>
                    <td align="center" style="color:var(--gold); font-weight:800;">${tm.total_pts || 0}</td>
                </tr>
            `;
        });

        html += `
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); padding:15px; border-radius:10px; margin-bottom:15px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:8px;">
                    <h3 style="margin:0; color:var(--gold); font-family:'Teko'; font-size:24px;">${m.match_name} <span style="font-size:16px; color:#fff;">(${m.map})</span></h3>
                    <span style="font-size:12px; color:#9da9b8;">Saved: ${m.timestamp || 'Completed'}</span>
                </div>
                <table style="width:100%; border-collapse:collapse;">
                    <tr style="color:#9da9b8; font-size:12px; text-transform:uppercase; border-bottom:1px solid rgba(255,255,255,0.1);">
                        <th align="left" style="padding:4px 8px;">Rank</th>
                        <th align="left">Team</th>
                        <th>Kills</th>
                        <th>Place Pts</th>
                        <th>Total</th>
                    </tr>
                    ${rowsHtml}
                </table>
            </div>
        `;
    });
    c.innerHTML = html;
}

async function clearMatchHistory() { if(!confirm("Wipe history?")) return; await fetch("/api/clear_history", { method: "POST" }); showToast("Wiped!"); loadTeams(); closeModal('historyModal'); }
async function uiUndo() { await fetch("/api/undo", { method: "POST" }); loadTeams(); }
async function uiRedo() { await fetch("/api/redo", { method: "POST" }); loadTeams(); }

async function uiResetAll() {
    if(!confirm("⚠️ Are you sure you want to RESET ALL? This will set all scores to 0, clear match history, and reset progression to 0%.")) return;
    await fetch("/api/reset_all", { method: "POST" });
    showToast("Everything Reset to 0! 🔄");
    loadTeams();
}

function uiSetPlayerCount(id, count) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, player_count: count}) }).then(loadTeams); }
function uiChangeKills(id, amt) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, kills_change: amt}) }).then(syncAdminData); }
function uiTogglePlayer(id, idx) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, player: idx}) }).then(syncAdminData); }
function uiUpdatePos(id, pos) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, position: parseInt(pos)||0}) }).then(loadTeams); }
function uiEliminate(id) { fetch("/api/eliminate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id}) }).then(syncAdminData); }
function uiUpdateName(id, name) { fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, name}) }); }
async function uiToggleAbsent(id) { await fetch("/api/toggle_absent", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id}) }); loadTeams(); }

async function adjustSlots(amount) {
    let count = teamsData.length + amount; if(count < 0) count = 0;
    await fetch("/api/adjust_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count}) });
    loadTeams();
}

async function saveMatchOverall() {
    if(!confirm("Save match and full score data to history?")) return;
    const res = await fetch("/api/save_match_overall", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({}) });
    const data = await res.json();
    if(res.ok) { 
        showToast("Full Match Data Saved! 💾"); 
        document.getElementById("matchName").value = data.next_match; 
        loadTeams(); 
    }
    else if(data.error) showToast(data.error);
}

async function loadConfigData() {
    const [cfgRes, hRes] = await Promise.all([fetch("/api/config"), fetch("/api/history")]);
    const cfg = await cfgRes.json(); const hist = await hRes.json();
    document.getElementById("tourneyName").value = cfg.tournament || "ESPORTS NATION INDIA";
    document.getElementById("matchName").value = cfg.match || "MATCH 1";
    document.getElementById("mapName").value = cfg.map || "ERANGEL";
    if(cfg.total_matches) document.getElementById("totalMatchesInput").value = cfg.total_matches;
    const completed = Array.isArray(hist) ? hist.length : 0; 
    const tot = cfg.total_matches || 10;
    document.getElementById("topProgress").innerText = `${completed}/${tot} (${Math.round((completed/tot)*100)}%)`;
}

async function updateConfig() {
    await fetch("/api/config", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ tournament: document.getElementById("tourneyName").value, match: document.getElementById("matchName").value, map: document.getElementById("mapName").value, total_matches: document.getElementById("totalMatchesInput").value }) });
    showToast("Config Saved!"); loadConfigData();
}

function renderAllTeams() {
    const container = document.getElementById("teamsContainer"); let html = "";
    let displayTeams = [...teamsData].sort((a,b) => a.id - b.id);
    const totalTeams = displayTeams.length;

    displayTeams.forEach(team => {
        const isAbsent = team.absent || false;
        const isDead = team.players.filter(p => p === 1).length === 0;
        let pHTML = "";
        team.players.forEach((a, idx) => { pHTML += `<div id="pbtn-${team.id}-${idx}" class="player-node ${a ? '' : 'dead'}" onclick="uiTogglePlayer(${team.id}, ${idx})">P${idx+1}</div>`; });
        
        let posOpts = `<option value="0" ${team.position==0?'selected':''}>POS 0 (Alive)</option>`;
        for(let i = 1; i <= totalTeams; i++) {
            let label = `RANK #${i}`;
            if(i === 1) label = `RANK #1 (WWCD 👑)`;
            else if(team.position === i && isDead) label = `RANK #${i} (Eliminated 💀)`;
            posOpts += `<option value="${i}" ${team.position==i?'selected':''}>${label}</option>`;
        }

        let logoImg = team.logo ? `<img src="${team.logo}">` : `<span>No Logo</span>`;
        let absentBtnClass = isAbsent ? "btn-not-present" : "btn-not-present is-present";
        let absentBtnText = isAbsent ? "❌ ABSENT" : "✅ PRESENT";

        html += `
            <div id="card-${team.id}" class="team-card searchable ${isAbsent ? 'not-present' : ''} ${isDead ? 'eliminated' : ''} ${team.position === 1 ? 'winner' : ''}" data-name="${team.name.toLowerCase()}">
                <div class="tc-header">
                    <span class="tc-slot">#${team.id}</span>
                    <input class="tc-name" value="${team.name}" onblur="uiUpdateName(${team.id}, this.value)" ${isAbsent ? 'disabled' : ''}>
                    ${team.wwcd > 0 ? `<span style="color:var(--gold); font-size:11px; font-weight:800;">🍗 ${team.wwcd}</span>` : ''}
                    <select class="player-count-select" onchange="uiSetPlayerCount(${team.id}, this.value)">
                        <option value="4" ${team.players.length==4?'selected':''}>4P</option><option value="3" ${team.players.length==3?'selected':''}>3P</option>
                        <option value="2" ${team.players.length==2?'selected':''}>2P</option><option value="1" ${team.players.length==1?'selected':''}>1P</option>
                    </select>
                    <button class="${absentBtnClass}" onclick="uiToggleAbsent(${team.id})">${absentBtnText}</button>
                    <button class="btn btn-elim" onclick="uiEliminate(${team.id})">WIPE</button>
                </div>
                <div class="tc-players">${pHTML}</div>
                <div class="tc-controls">
                    <select id="pos-sel-${team.id}" onchange="uiUpdatePos(${team.id}, this.value)">${posOpts}</select>
                    <button class="btn btn-icon" onclick="uiChangeKills(${team.id}, -1)">-</button>
                    <button class="btn btn-icon plus" onclick="uiChangeKills(${team.id}, 1)">+1</button>
                </div>
                <div class="tc-stats">
                    <div class="tc-stat-box fin"><span>Finishes</span><strong id="kills-${team.id}">${team.kills}</strong></div>
                    <div class="tc-stat-box pts"><span>Total Pts</span><strong id="pts-${team.id}">${team.points}</strong></div>
                    <div class="tc-stat-box tot"><span>Overall</span><strong id="ov-${team.id}">${team.overall_pts || 0}</strong></div>
                </div>
                <div class="logo-row">${logoImg}<input type="file" accept="image/*" onchange="uploadLogo(${team.id}, this)"></div>
            </div>`;
    });
    container.innerHTML = html; filterTeams(); syncAdminData();
}

function filterTeams() {
    const q = document.getElementById("searchInput").value.toLowerCase().trim();
    document.querySelectorAll(".searchable").forEach(c => { c.style.display = (q === "" || c.dataset.name.includes(q)) ? "block" : "none"; });
}

async function loadTeams() { const res = await fetch("/api/teams"); teamsData = await res.json(); renderAllTeams(); loadConfigData(); }
async function importSlots() {
    const rawText = document.getElementById("slotInput").value;
    if(!rawText.trim()) return alert("Paste slots!");
    let names = [];
    rawText.split('\n').forEach(line => {
        let c = line.trim(); if(c) names.push(c.replace(/^(?:slot\s*#?\d+[\s\-\→\:\.\|]*|\#?\d+[\.\-\)\:\|]+\s*)/i, '').trim());
    });
    await fetch("/api/import_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({names}) });
    loadTeams(); showToast("Imported!");
}
async function resetMatchState() { if(!confirm("Reset match?")) return; await fetch("/api/reset_match", { method: "POST" }); loadTeams(); }
async function resetTeams() { if(!confirm("Delete all?")) return; await fetch("/api/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count: 0}) }); loadTeams(); }
async function uploadLogo(id, fileInput) {
    if(fileInput.files && fileInput.files[0]){
        const fd = new FormData(); fd.append("id", id); fd.append("logo", fileInput.files[0]);
        await fetch("/api/upload_logo", { method: "POST", body: fd }); loadTeams();
    }
}

loadThemeSettings();
loadTeams();
</script>
</body>
</html>
"""

# OBS Overlays with Animations and Theme Engine
THEME_ENGINE_JS = r"""
<script>
let lastTheme="";
async function syncTheme() {
    try {
        const res = await fetch("/api/active_theme");
        if(!res.ok) return;
        const d = await res.json();
        let str = JSON.stringify(d.theme);
        if(str === lastTheme) return;
        lastTheme = str;
        applyTh(d.theme);
    } catch(e){}
}
function applyTh(t) {
    let el = document.getElementById("dyn-th");
    if(!el) { el = document.createElement("style"); el.id="dyn-th"; document.head.appendChild(el); }
    el.innerHTML = `
        .top-status-bar, .header, .st-head { background: ${t.primary} !important; color: ${t.bg_primary} !important; }
        .row, .st-row { background: linear-gradient(135deg, ${t.bg_primary}, ${t.bg_secondary}) !important; transition: all 0.4s ease; }
        .rank-cell, .pts, .st-pts, .bh-title, .mi-match, .winner-name { color: ${t.primary} !important; }
        .kills, .mi-tourney, .bh-sub { color: ${t.secondary} !important; }
    `;
}
syncTheme(); setInterval(syncTheme, 2000);
</script>
"""

PT_HTML = r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#pt{position:fixed;top:40px;right:15px;width:285px;color:white;box-shadow:0 12px 35px rgba(0,0,0,0.8);border-radius:6px;overflow:hidden;background:#061326;animation:fadeInPT 0.8s ease;}@keyframes fadeInPT{from{opacity:0;transform:translateY(-15px);}to{opacity:1;transform:translateY(0);}}.top-status-bar{display:flex;justify-content:space-between;align-items:center;background:#061326;border-top:3px solid #f2c400;padding:5px 10px;font-size:11px;font-weight:800;}.header{height:26px;display:grid;grid-template-columns:36px 1fr 48px 34px 36px;align-items:center;background:#f2c400;color:#050b14;font-weight:800;font-size:11px;padding:0 6px;}.row{height:28px;display:grid;grid-template-columns:36px 1fr 48px 34px 36px;align-items:center;background:rgb(6,20,39);border-bottom:1px solid rgba(255,255,255,0.08);padding:0 6px;transition:all 0.3s ease;}.rank-cell{text-align:center;color:#f2c400;font-weight:800;font-size:11px;}.team-name-area{padding-left:4px;font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px;}.team-logo{width:17px;height:17px;object-fit:contain;border-radius:2px;flex-shrink:0;}.players{display:flex;justify-content:center;gap:3px;}.player{width:5px;height:14px;background:#00ff66;}.player.dead{background:#3d4b5c;}.kills{text-align:center;color:#00e5ff;font-weight:700;}.pts{text-align:center;color:#f2c400;font-weight:800;background:rgba(242,196,0,0.1);height:100%;display:flex;align-items:center;justify-content:center;}</style></head><body><div id="pt"><div class="top-status-bar"><span>TEAMS <strong id="t">0</strong></span><span>ALIVE <strong id="p">0</strong></span></div><div class="header"><div>#</div><div>TEAM</div><div>ALIVE</div><div>FIN</div><div>PTS</div></div><div id="r"></div></div>
<script>
let prevRanks={};
async function l(){
    try{
        const res=await fetch("/api/teams"); const data=await res.json();
        let at=0, ap=0;
        data.forEach(t=>{if(!t.absent){let a=t.players.filter(p=>p===1).length;if(a>0)at++;ap+=a;}});
        document.getElementById("t").innerText=at; document.getElementById("p").innerText=ap;
        const sorted=[...data].sort((a,b)=>{if(a.absent!==b.absent)return a.absent?1:-1;const aA=a.players.filter(p=>p===1).length>0, bA=b.players.filter(p=>p===1).length>0;if(aA!==bA)return aA?-1:1;return(b.points||0)-(a.points||0);});
        let h="";
        sorted.forEach((t,i)=>{
            const rank=i+1; const prev=prevRanks[t.id]||rank; const diff=prev-rank;
            let ind=diff>0?`<span style="color:#00ff66;font-size:9px;">▲</span>`:(diff<0?`<span style="color:#ff2a55;font-size:9px;">▼</span>`:"");
            prevRanks[t.id]=rank;
            let s=""; t.players.forEach(a=>s+=`<div class="player ${a?'':'dead'}"></div>`);
            let logo=t.logo?`<img class="team-logo" src="${t.logo}">`:"";
            h+=`<div class="row"><div class="rank-cell">#${rank}${ind}</div><div class="team-name-area">${logo}${t.name}</div><div class="players">${s}</div><div class="kills">${t.kills}</div><div class="pts">${t.points}</div></div>`;
        });
        document.getElementById("r").innerHTML=h;
    }catch(e){}
}
l();setInterval(l,1500);
</script>
""" + THEME_ENGINE_JS + "</body></html>"

ELIM_HTML = r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#elimination{position:fixed;left:50%;top:16%;width:420px;transform:translate(-50%,-50%) scale(0.85);opacity:0;pointer-events:none;background:linear-gradient(135deg, rgb(6,20,39), rgb(14,34,60));border:1px solid rgba(255,46,77,0.55);border-top:4px solid #ff2e4d;border-radius:12px;padding:16px 22px;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,0.8);z-index:999;}#elimination.show{animation:elimShow 3.8s cubic-bezier(0.16,1,0.3,1) forwards;}@keyframes elimShow{0%{opacity:0;transform:translate(-50%,-70%) scale(0.7);}15%{opacity:1;transform:translate(-50%,-50%) scale(1);}85%{opacity:1;transform:translate(-50%,-50%) scale(1);}100%{opacity:0;transform:translate(-50%,-35%) scale(0.85);}}.elim-banner{display:inline-block;background:rgba(255,46,77,0.2);color:#ff4d6d;font-size:11px;font-weight:800;letter-spacing:3px;padding:3px 12px;border-radius:4px;margin-bottom:8px;}.elim-team-row{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:14px;}.elim-logo{width:48px;height:48px;object-fit:contain;border-radius:8px;background:rgba(255,255,255,0.07);padding:4px;}.elim-team{color:#ffffff;font-family:'Teko',sans-serif;font-size:36px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;}.elim-info{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}.info-box{padding:7px 6px;border:1px solid rgba(255,255,255,0.14);border-radius:8px;background:rgba(0,0,0,0.35);}.info-label{color:#9da9b8;font-size:10px;font-weight:800;}.info-value{color:white;font-size:21px;font-weight:800;}.info-value.gold{color:#f2c400;}.info-value.cyan{color:#00e5ff;}</style></head><body><div id="elimination"><div class="elim-banner">SQUAD ELIMINATED</div><div class="elim-team-row"><img id="elimLogo" class="elim-logo" src="" style="display:none;" onerror="this.style.display='none'"><div class="elim-team" id="elimTeam">TEAM NAME</div></div><div class="elim-info"><div class="info-box"><div class="info-label">RANK</div><div class="info-value gold" id="elimRank">#0</div></div><div class="info-box"><div class="info-label">FINISHES</div><div class="info-value cyan" id="elimKills">0</div></div><div class="info-box"><div class="info-label">TOTAL PTS</div><div class="info-value" id="elimPts">0</div></div></div></div>
<script>
let lastState={}, lastTs={}, queue=[], playing=false;
async function check(){
    try{
        const res=await fetch("/api/teams"); const data=await res.json();
        data.forEach(t=>{
            if(t.absent)return;
            let oldA=lastState[t.id], curA=t.players.filter(p=>p===1).length;
            let oldT=lastTs[t.id], curT=t.elim_ts||0;
            if(((oldA!==undefined&&oldA>0&&curA===0)||(oldT!==undefined&&curT>oldT))&&t.position>0){
                queue.push(t); runQ();
            }
            lastState[t.id]=curA; lastTs[t.id]=curT;
        });
    }catch(e){}
}
function runQ(){
    if(playing||queue.length===0)return;
    playing=true; let t=queue.shift();
    document.getElementById("elimTeam").innerText=t.name;
    document.getElementById("elimKills").innerText=t.kills;
    document.getElementById("elimRank").innerText="#"+t.position;
    document.getElementById("elimPts").innerText=t.points;
    let logo=document.getElementById("elimLogo");
    if(t.logo){logo.src=t.logo; logo.style.display="block";}else logo.style.display="none";
    let el=document.getElementById("elimination");
    el.classList.remove("show"); void el.offsetWidth; el.classList.add("show");
    setTimeout(()=>{playing=false; runQ();},3800);
}
setInterval(check,1000);
</script>
""" + THEME_ENGINE_JS + "</body></html>"

MATCH_HTML = r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#match-info{position:fixed;bottom:18px;left:18px;min-width:240px;background:linear-gradient(135deg, rgb(6,20,39), rgb(12,34,62));border:1px solid rgba(242,196,0,0.4);border-left:4px solid #f2c400;border-radius:8px;padding:8px 14px;color:white;box-shadow:0 8px 25px rgba(0,0,0,0.65);animation:slideMatch 0.8s ease;}.mi-tourney{font-size:10px;font-weight:800;color:#00e5ff;letter-spacing:1.5px;}.mi-row{display:flex;align-items:baseline;gap:10px;margin-top:2px;}.mi-match{font-family:'Teko',sans-serif;font-size:24px;font-weight:700;color:#f2c400;}.mi-map{font-family:'Teko',sans-serif;font-size:24px;font-weight:700;color:white;}</style></head><body><div id="match-info"><div class="mi-tourney" id="dt">ESPORTS NATION INDIA</div><div class="mi-row"><div class="mi-match" id="dm">MATCH 1</div><div>|</div><div class="mi-map" id="dmap">ERANGEL</div></div></div>
<script>
async function c(){try{const res=await fetch("/api/config");const cfg=await res.json();document.getElementById("dt").innerText=cfg.tournament||"ESPORTS NATION INDIA";document.getElementById("dm").innerText=cfg.match||"MATCH 1";document.getElementById("dmap").innerText=cfg.map||"ERANGEL";}catch(e){}}
c();setInterval(c,2000);
</script>
""" + THEME_ENGINE_JS + "</body></html>"

STANDINGS_HTML = r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:radial-gradient(circle at center, rgb(10,28,54) 0%, rgb(3,8,17) 100%);font-family:'Rajdhani',sans-serif;color:white;}.board-wrapper{max-width:1320px;margin:35px auto;padding:0 25px;animation:fadeInBoard 0.8s ease;}@keyframes fadeInBoard{from{opacity:0;}to{opacity:1;}}.board-header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #f2c400;padding-bottom:10px;margin-bottom:22px;}.bh-title{font-family:'Teko',sans-serif;font-size:48px;color:#f2c400;letter-spacing:2px;text-transform:uppercase;}.bh-sub{font-size:16px;font-weight:800;color:#00e5ff;letter-spacing:3px;}.standings-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px 28px;}.st-table{width:100%;border-collapse:separate;border-spacing:0 6px;}.st-head{background:#f2c400;color:#040811;font-weight:800;font-size:13px;}.st-head th{padding:7px 10px;text-align:center;}.st-head th:nth-child(2){text-align:left;}.st-row{background:rgb(9,28,54);}.st-row.top1{background:rgb(36,31,10);outline:1px solid #f2c400;}.st-row td{padding:8px 10px;text-align:center;font-weight:800;font-size:16px;}.st-row td:first-child{color:#f2c400;width:68px;}.st-team{display:flex;align-items:center;gap:10px;text-align:left;}.st-logo{width:26px;height:26px;object-fit:contain;border-radius:4px;}.st-pts{color:#f2c400;font-size:18px;background:rgba(242,196,0,0.12);}</style></head><body><div class="board-wrapper"><div class="board-header"><div><div class="bh-sub" id="stTourney">ESPORTS NATION INDIA</div><div class="bh-title">OVERALL STANDINGS</div></div><div class="bh-title" style="font-size:34px;">LEADERBOARD</div></div><div class="standings-grid"><table class="st-table"><thead><tr class="st-head"><th>#</th><th>TEAM</th><th>M</th><th>WWCD</th><th>KILLS</th><th>PLACE</th><th>TOTAL</th></tr></thead><tbody id="colLeft"></tbody></table><table class="st-table"><thead><tr class="st-head"><th>#</th><th>TEAM</th><th>M</th><th>WWCD</th><th>KILLS</th><th>PLACE</th><th>TOTAL</th></tr></thead><tbody id="colRight"></tbody></table></div></div>
<script>
async function loadSt(){
    try{
        const [cRes, tRes]=await Promise.all([fetch("/api/config"),fetch("/api/teams")]);
        const cfg=await cRes.json(); const data=await tRes.json();
        document.getElementById("stTourney").innerText=cfg.tournament||"ESPORTS NATION INDIA";
        const sorted=[...data].sort((a,b)=>{
            if(a.absent!==b.absent)return a.absent?1:-1;
            return ((b.overall_pts||0)+(b.points||0)) - ((a.overall_pts||0)+(a.points||0));
        });
        const mid=Math.ceil(sorted.length/2);
        const render=(list, offset)=>list.map((t,idx)=>`
            <tr class="st-row ${!t.absent&&(offset+idx+1)===1?'top1':''}">
                <td>#${offset+idx+1}</td>
                <td><div class="st-team">${t.logo?`<img class="st-logo" src="${t.logo}">`:''}<span>${t.name}</span></div></td>
                <td>${t.matches_played||0}</td><td style="color:#f2c400;">${t.wwcd||0}</td>
                <td style="color:#00ff66;">${(t.overall_kills||0)+(t.kills||0)}</td>
                <td style="color:#00bfff;">${(t.overall_place_pts||0)+(t.placement_points||0)}</td>
                <td class="st-pts">${(t.overall_pts||0)+(t.points||0)}</td>
            </tr>
        `).join("");
        document.getElementById("colLeft").innerHTML=render(sorted.slice(0,mid),0);
        document.getElementById("colRight").innerHTML=render(sorted.slice(mid),mid);
    }catch(e){}
}
loadSt(); setInterval(loadSt,2000);
</script>
""" + THEME_ENGINE_JS + "</body></html>"

WWCD_HTML = r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#wwcd-screen{position:fixed;top:0;left:0;width:100vw;height:100vh;background:radial-gradient(circle at center, rgba(16,28,48,0.96) 0%, rgba(3,6,15,0.99) 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;pointer-events:none;z-index:9999;}#wwcd-screen.show{animation:wwcdAnim 10s cubic-bezier(0.16,1,0.3,1) forwards;}@keyframes wwcdAnim{0%{opacity:0;transform:scale(1.15);}10%{opacity:1;transform:scale(1);}90%{opacity:1;transform:scale(1);}100%{opacity:0;transform:scale(0.95);}}.wwcd-badge{border-top:2px solid #f2c400;border-bottom:2px solid #f2c400;color:#f2c400;font-size:24px;font-weight:800;letter-spacing:8px;padding:8px 50px;margin-bottom:20px;text-transform:uppercase;}.wwcd-title{font-family:'Teko',sans-serif;font-size:96px;color:#fff;line-height:0.9;margin:0 0 25px 0;text-transform:uppercase;}.wwcd-title span{color:#f2c400;}.winner-card{background:linear-gradient(135deg,rgb(10,26,48),rgb(5,13,26));border:2px solid #f2c400;border-radius:20px;padding:35px 70px;display:flex;flex-direction:column;align-items:center;min-width:550px;box-shadow:0 25px 70px rgba(0,0,0,0.9);}.winner-logo{width:130px;height:130px;object-fit:contain;border-radius:16px;background:rgba(255,255,255,0.06);padding:12px;border:2px solid rgba(242,196,0,0.6);margin-bottom:18px;}.winner-name{font-family:'Teko',sans-serif;font-size:80px;color:#f2c400;line-height:1;text-transform:uppercase;margin-bottom:25px;text-align:center;}.winner-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:25px;width:100%;}.w-stat-box{background:rgba(0,0,0,0.55);border:1px solid rgba(255,255,255,0.12);border-bottom:3px solid #f2c400;border-radius:12px;padding:14px 24px;text-align:center;}.w-stat-label{font-size:13px;color:#9da9b8;font-weight:800;letter-spacing:2px;}.w-stat-val{font-size:38px;font-weight:800;color:#f2c400;line-height:1;}</style></head><body><div id="wwcd-screen"><div class="wwcd-badge">🍗 WINNER WINNER CHICKEN DINNER 🍗</div><h1 class="wwcd-title">MATCH <span>CHAMPIONS</span></h1><div class="winner-card"><img id="wwcdLogo" class="winner-logo" src="" style="display:none;" onerror="this.style.display='none'"><div id="wwcdName" class="winner-name">TEAM NAME</div><div class="winner-stats"><div class="w-stat-box"><div class="w-stat-label">RANK</div><div class="w-stat-val">#1</div></div><div class="w-stat-box"><div class="w-stat-label">FINISHES</div><div id="wwcdKills" class="w-stat-val" style="color:#00e5ff;">0</div></div><div class="w-stat-box"><div class="w-stat-label">PTS</div><div id="wwcdPts" class="w-stat-val">0</div></div></div></div></div>
<script>
let prevAlive=null, shown=false;
async function cW(){
    try{
        const res=await fetch("/api/teams"); const data=await res.json();
        const active=data.filter(t=>!t.absent);
        const alive=active.filter(t=>t.players.filter(p=>p===1).length>0);
        let cur=alive.length;
        if(cur>1) shown=false;
        if(prevAlive!==null&&prevAlive>1&&cur===1&&!shown){
            shown=true; let w=alive[0];
            setTimeout(()=>{
                document.getElementById("wwcdName").innerText=w.name;
                document.getElementById("wwcdKills").innerText=w.kills;
                document.getElementById("wwcdPts").innerText=w.kills+10;
                let l=document.getElementById("wwcdLogo");
                if(w.logo){l.src=w.logo; l.style.display="block";}else l.style.display="none";
                let s=document.getElementById("wwcd-screen"); s.classList.remove("show"); void s.offsetWidth; s.classList.add("show");
            },3800);
        }
        prevAlive=cur;
    }catch(e){}
}
setInterval(cW,1000);
</script>
""" + THEME_ENGINE_JS + "</body></html>"

# =========================================================
# ROUTES & API
# =========================================================

@app.route("/")
def admin(): 
    return render_template_string(ADMIN_HTML)

@app.route("/overlay/pt")
def overlay_pt(): return render_template_string(PT_HTML)
@app.route("/overlay/elimination")
def overlay_elimination(): return render_template_string(ELIM_HTML)
@app.route("/overlay/match")
def overlay_match(): return render_template_string(MATCH_HTML)
@app.route("/overlay/standings")
def overlay_standings(): return render_template_string(STANDINGS_HTML)
@app.route("/overlay/wwcd")
def overlay_wwcd(): return render_template_string(WWCD_HTML)

@app.route("/api/ping")
def ping():
    cid = request.args.get("cid", request.remote_addr)
    now = time.time()
    connected_users[cid] = now
    active = sum(1 for ts in connected_users.values() if now - ts < 6)
    return jsonify({"status": "ok", "users": active})

@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = load_config()
        if "tournament" in data: cfg["tournament"] = data["tournament"]
        if "match" in data: cfg["match"] = data["match"]
        if "map" in data: cfg["map"] = data["map"]
        if "total_matches" in data:
            try: cfg["total_matches"] = max(1, int(data["total_matches"]))
            except: pass
        save_config(cfg)
        return jsonify({"success": True})
    return jsonify(load_config())

@app.route("/api/themes", methods=["GET", "POST"])
def api_themes():
    if request.method == "POST":
        data = request.get_json() or {}
        themes_data = load_themes()
        
        # Admin Theme Setting
        if "admin_theme" in data:
            themes_data["admin_theme"] = data["admin_theme"]
            
        # OBS Match Theme Setting
        if "match_key" in data:
            match_key = data.get("match_key", "MATCH 1").strip().upper()
            theme_cfg = data.get("theme", {})
            if "matches" not in themes_data: themes_data["matches"] = {}
            themes_data["matches"][match_key] = theme_cfg
            
        save_themes(themes_data)
        return jsonify({"success": True})
    return jsonify({"themes": load_themes(), "presets": BUILTIN_PRESETS})

@app.route("/api/active_theme")
def api_active_theme():
    cfg = load_config()
    current_match = (cfg.get("match") or "MATCH 1").strip().upper()
    themes_data = load_themes()
    matches_map = themes_data.get("matches", {})
    active = matches_map.get(current_match, BUILTIN_PRESETS["Classic Gold"])
    return jsonify({"match": current_match, "theme": active})

@app.route("/api/teams")
def api_teams(): 
    return jsonify(load())

@app.route("/api/undo", methods=["POST"])
def api_undo():
    global undo_stack, redo_stack
    if undo_stack:
        current_state = load()
        redo_stack.append(copy.deepcopy(current_state))
        previous_state = undo_stack.pop()
        save(previous_state)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/redo", methods=["POST"])
def api_redo():
    global undo_stack, redo_stack
    if redo_stack:
        current_state = load()
        undo_stack.append(copy.deepcopy(current_state))
        next_state = redo_stack.pop()
        save(next_state)
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
    if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
    cfg = load_config()
    cfg["match"] = "MATCH 1"
    save_config(cfg)
    save_state_for_undo()
    teams = load()
    for t in teams:
        t["matches_played"] = 0; t["overall_kills"] = 0
        t["overall_place_pts"] = 0; t["overall_pts"] = 0; t["wwcd"] = 0
    save(teams)
    return jsonify({"success": True})

@app.route("/api/reset_all", methods=["POST"])
def reset_all():
    """Resets everything to zero and 0% progress except the Match Option."""
    save_state_for_undo()
    if os.path.exists(HISTORY_FILE):
        try: os.remove(HISTORY_FILE)
        except: pass

    teams = load()
    for t in teams:
        t["kills"] = 0
        t["position"] = 0
        t["points"] = 0
        t["placement_points"] = 0
        t["overall_kills"] = 0
        t["overall_place_pts"] = 0
        t["overall_pts"] = 0
        t["matches_played"] = 0
        t["wwcd"] = 0
        t["players"] = [1] * len(t.get("players", [1, 1, 1, 1]))
        t["elim_ts"] = 0
        t["match_saved_flag"] = False

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
    for i, name in enumerate(names, start=3):
        teams.append({
            "id": i, "name": name, "logo": logo_map.get(name.upper(), ""),
            "kills": 0, "position": 0, "points": 0, "placement_points": 0,
            "overall_kills": 0, "overall_place_pts": 0, "overall_pts": 0,
            "matches_played": 0, "wwcd": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
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
        max_id = max([t["id"] for t in teams]) if teams else 2
        for _ in range(current_count, new_count):
            max_id += 1
            teams.append({
                "id": max_id, "name": f"TEAM {max_id}", "logo": "", "kills": 0, "position": 0,
                "points": 0, "placement_points": 0, "overall_kills": 0, "overall_place_pts": 0,
                "overall_pts": 0, "matches_played": 0, "wwcd": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
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
        team["kills"] = 0; team["position"] = 0; team["points"] = 0; team["placement_points"] = 0;
        team["players"] = [1] * len(team.get("players", [1,1,1,1]))
        team["elim_ts"] = 0
        team["match_saved_flag"] = False
    save(teams)
    return jsonify({"success": True})

@app.route("/api/create", methods=["POST"])
def create():
    data = request.get_json() or {}
    count = int(data.get("count", 0))
    save_state_for_undo()
    if count <= 0:
        save([]); return jsonify({"success": True})
    count = min(count, 50)
    existing_teams = load()
    logo_map = {t["id"]: t.get("logo", "") for t in existing_teams}
    teams = []
    for i in range(3, count + 3):
        teams.append({
            "id": i, "name": f"TEAM {i}", "logo": logo_map.get(i, ""),
            "kills": 0, "position": 0, "points": 0, "placement_points": 0,
            "overall_kills": 0, "overall_place_pts": 0, "overall_pts": 0,
            "matches_played": 0, "wwcd": 0, "absent": False, "players": [1, 1, 1, 1], "elim_ts": 0
        })
    save(teams)
    return jsonify({"success": True})

@app.route("/api/update", methods=["POST"])
def update():
    data = request.get_json() or {}
    save_state_for_undo()
    teams = load()
    team_id = int(data.get("id", 0))
    total_active = len([t for t in teams if not t.get("absent")])

    for team in teams:
        if team["id"] != team_id: continue
        if "name" in data: team["name"] = data["name"]
        
        if "player_count" in data:
            new_count = int(data["player_count"])
            current = team.get("players", [1, 1, 1, 1])
            if new_count > len(current): current.extend([1] * (new_count - len(current)))
            elif new_count < len(current): current = current[:new_count]
            team["players"] = current
            
            if sum(team["players"]) == 0 and team.get("position", 0) == 0:
                assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                for p in range(total_active, 1, -1):
                    if p not in assigned_positions:
                        team["position"] = p; break
                team["elim_ts"] = time.time()
            elif sum(team["players"]) > 0 and team.get("position", 0) > 0:
                team["position"] = 0; team["elim_ts"] = 0

        if "player" in data:
            player = int(data["player"])
            if 0 <= player < len(team["players"]):
                was_dead = (sum(team["players"]) == 0)
                team["players"][player] = 0 if team["players"][player] else 1
                now_alive = sum(team["players"])

                if now_alive == 0 and team.get("position", 0) == 0:
                    assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                    for p in range(total_active, 1, -1):
                        if p not in assigned_positions:
                            team["position"] = p; break
                    team["elim_ts"] = time.time()
                elif was_dead and now_alive > 0:
                    team["position"] = 0

        if "kills_change" in data: team["kills"] = max(0, team.get("kills", 0) + int(data["kills_change"]))
        if "position" in data: team["position"] = int(data["position"])

    save(teams)
    return jsonify({"success": True})

@app.route("/api/eliminate", methods=["POST"])
def eliminate():
    data = request.get_json() or {}
    save_state_for_undo()
    teams = load()
    team_id = int(data.get("id", 0))
    total_active = len([t for t in teams if not t.get("absent")])

    for team in teams:
        if team["id"] == team_id:
            team["players"] = [0] * len(team.get("players", [1,1,1,1]))
            if team.get("position", 0) == 0:
                assigned_positions = [t.get("position", 0) for t in teams if t.get("position", 0) > 0]
                for p in range(total_active, 1, -1):
                    if p not in assigned_positions:
                        team["position"] = p; break
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
    
    if teams and all(t.get("match_saved_flag", False) for t in teams if not t.get("absent")):
        return jsonify({"error": "Match already saved! Click NEW MATCH before saving again."}), 400

    auto_assign_winner_if_one_left(teams)
    recalculate_all(teams)

    current_match_data = []
    for t in teams:
        if not t.get("absent", False):
            t["matches_played"] = t.get("matches_played", 0) + 1
            t["overall_kills"] = t.get("overall_kills", 0) + t.get("kills", 0)
            t["overall_place_pts"] = t.get("overall_place_pts", 0) + t.get("placement_points", 0)
            t["overall_pts"] = t.get("overall_pts", 0) + t.get("points", 0)
            if t.get("position", 0) == 1:
                t["wwcd"] = t.get("wwcd", 0) + 1
            t["match_saved_flag"] = True
            
        current_match_data.append({
            "id": t["id"],
            "name": t["name"],
            "kills": t.get("kills", 0),
            "placement_points": t.get("placement_points", 0),
            "total_pts": t.get("points", 0),
            "position": t.get("position", 0),
            "absent": t.get("absent", False)
        })

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
                history = json.load(hf)
        except: history = []
            
    match_number = len(history) + 1
    cfg = load_config()
    
    # Save full detailed match snapshot
    history.append({
        "match_num": match_number,
        "match_name": cfg.get("match", f"MATCH {match_number}"),
        "map": cfg.get("map", "ERANGEL"),
        "timestamp": time.strftime("%d %b %Y, %I:%M %p"),
        "teams": copy.deepcopy(current_match_data)
    })
    
    with file_lock:
        if os.path.exists(HISTORY_FILE):
            try: shutil.copy(HISTORY_FILE, HISTORY_FILE + ".bak")
            except: pass
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    cfg["match"] = f"MATCH {match_number + 1}"
    save_config(cfg)
    save(teams)
    return jsonify({"success": True, "next_match": f"MATCH {match_number + 1}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
