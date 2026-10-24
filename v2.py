import copy
import json
import os
import shutil
import socket
import time
from threading import Lock
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
file_lock = Lock()

DATA_FILE = "teams.json"
CONFIG_FILE = "config.json"
HISTORY_FILE = "match_history.json"
THEMES_FILE = "themes.json"
UPLOAD_FOLDER = os.path.join("static", "logos")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
SERVER_LOGO_FILENAME = "server_logo.webp"
SERVER_LOGO_PATH = os.path.join(UPLOAD_FOLDER, SERVER_LOGO_FILENAME)

MAX_HISTORY = 20
undo_stack = []
redo_stack = []
connected_users = {}

PLACEMENT = {1: 10, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1, 8: 1}


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def placement_points(position):
    try:
        return PLACEMENT.get(int(position), 0)
    except (ValueError, TypeError):
        return 0


def calculate_points(team):
    kills = max(0, int(team.get("kills", 0)))
    place = placement_points(team.get("position", 0))
    return kills, place, (kills + place)


def recalculate_all(teams):
    if not isinstance(teams, list):
        return []
    for team in teams:
        if not isinstance(team, dict):
            continue
        if "absent" not in team:
            team["absent"] = False
        if "overall_kills" not in team:
            team["overall_kills"] = 0
        if "overall_pts" not in team:
            team["overall_pts"] = 0
        if "overall_place_pts" not in team:
            team["overall_place_pts"] = 0
        if "matches_played" not in team:
            team["matches_played"] = 0
        if "wwcd" not in team:
            team["wwcd"] = 0
        if "players" not in team or not team["players"]:
            team["players"] = [1, 1, 1, 1]

        k, p, tot = calculate_points(team)
        team["kills"] = k
        team["placement_points"] = p
        team["points"] = tot
    return teams


def auto_assign_winner_if_one_left(teams):
    if not isinstance(teams, list):
        return
    active = [
        t for t in teams if isinstance(t, dict) and not t.get("absent", False)
    ]
    alive = [t for t in active if any(p == 1 for p in t.get("players", []))]
    if len(active) > 1 and len(alive) == 1:
        winner = alive[0]
        if winner.get("position", 0) != 1:
            winner["position"] = 1
            k, p, tot = calculate_points(winner)
            winner["placement_points"] = p
            winner["points"] = tot


def safe_write_json(file_path, data):
    with file_lock:
        if os.path.exists(file_path):
            try:
                shutil.copy(file_path, file_path + ".bak")
            except Exception:
                pass
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def save(teams):
    auto_assign_winner_if_one_left(teams)
    recalculate_all(teams)
    safe_write_json(DATA_FILE, teams)


def load():
    if not os.path.exists(DATA_FILE):
        return []
    with file_lock:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)
                auto_assign_winner_if_one_left(data)
                return recalculate_all(data)
        except Exception:
            return []


def save_state_for_undo():
    global undo_stack, redo_stack
    current_state = load()
    undo_stack.append(copy.deepcopy(current_state))
    if len(undo_stack) > MAX_HISTORY:
        undo_stack.pop(0)
    redo_stack.clear()


def load_config():
    default_cfg = {
        "tournament": "ESPORTS NATION INDIA",
        "match": "MATCH 1",
        "map": "ERANGEL",
        "caster1_name": "CASTER ALPHA",
        "caster1_title": "PLAY-BY-PLAY",
        "caster2_name": "ANALYST BRAVO",
        "caster2_title": "COLOR COMMENTARY",
        "start_timer_min": "5",
        "broadcast_headline": "GRAND FINALS - DAY 1",
        "discord_tag": "discord.gg/esportsindia",
        "insta_tag": "@esportsnation.india",
        "yt_tag": "@esportnationindia",
        "chroma_key_mode": True,
        "map_position": "bottom-right",
        "dual_team1_name": "",
        "dual_team1_sub": "POV 1",
        "dual_team2_name": "",
        "dual_team2_sub": "POV 2",
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(default_cfg)
        return default_cfg
    with file_lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return default_cfg
                return {**default_cfg, **json.loads(content)}
        except Exception:
            return default_cfg


def save_config(config):
    safe_write_json(CONFIG_FILE, config)


BUILTIN_PRESETS = {
    "Classic Gold": {
        "primary": "#f2c400",
        "secondary": "#00e5ff",
        "map_color": "#ffffff",
        "bg_primary": "#06090e",
        "bg_secondary": "#0d121a",
    },
    "Royal Blue": {
        "primary": "#00b4d8",
        "secondary": "#90e0ef",
        "map_color": "#00ffff",
        "bg_primary": "#03045e",
        "bg_secondary": "#0a1128",
    },
    "Crimson Red": {
        "primary": "#ff2a55",
        "secondary": "#ffb703",
        "map_color": "#ffdd00",
        "bg_primary": "#1a050a",
        "bg_secondary": "#260810",
    },
    "Cyber Purple": {
        "primary": "#b5179e",
        "secondary": "#4cc9f0",
        "map_color": "#ffffff",
        "bg_primary": "#10002b",
        "bg_secondary": "#1d0538",
    },
    "Neon Cyber": {
        "primary": "#00ffcc",
        "secondary": "#ff00ff",
        "map_color": "#ff00ff",
        "bg_primary": "#050b14",
        "bg_secondary": "#0d1726",
    },
    "Sunset Orange": {
        "primary": "#ff7700",
        "secondary": "#ffbb00",
        "map_color": "#ffffff",
        "bg_primary": "#1a0f05",
        "bg_secondary": "#261507",
    },
    "Emerald Neon": {
        "primary": "#00ff88",
        "secondary": "#00e5ff",
        "map_color": "#00e5ff",
        "bg_primary": "#041a10",
        "bg_secondary": "#082618",
    },
    "Rose Gold": {
        "primary": "#ff85a1",
        "secondary": "#fbb1bd",
        "map_color": "#ffffff",
        "bg_primary": "#1f0a10",
        "bg_secondary": "#2e0f18",
    },
}


def load_themes():
    default_data = {
        "admin_theme": "Classic Gold",
        "matches": {
            "MATCH 1": copy.deepcopy(BUILTIN_PRESETS["Classic Gold"]),
            "MATCH 2": copy.deepcopy(BUILTIN_PRESETS["Royal Blue"]),
            "MATCH 3": copy.deepcopy(BUILTIN_PRESETS["Crimson Red"]),
        },
    }
    if not os.path.exists(THEMES_FILE):
        save_themes(default_data)
        return default_data
    with file_lock:
        try:
            with open(THEMES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return default_data
                data = json.loads(content)
                if "matches" not in data:
                    data["matches"] = default_data["matches"]
                if "admin_theme" not in data:
                    data["admin_theme"] = "Classic Gold"
                return data
        except Exception:
            return default_data


def save_themes(data):
    safe_write_json(THEMES_FILE, data)


load_config()
load_themes()

# =========================================================
# GLOBAL BROADCAST ENGINE (CSS + ANIMATIONS)
# =========================================================

THEME_ENGINE_JS = r"""
<script>
let lastTheme="";
async function syncTheme() {
    try {
        const res = await fetch("/api/active_theme?t=" + Date.now());
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
    const customMapColor = t.map_color || "#ffffff";
    el.innerHTML = `
        :root {
            --gold: ${t.primary} !important;
            --cyan: ${t.secondary} !important;
            --dark-1: ${t.bg_primary} !important;
            --dark-2: ${t.bg_secondary} !important;
        }
        .top-status-bar, .header, .st-head, .accent-bg { background: ${t.primary} !important; color: ${t.bg_primary} !important; }
        .row, .st-row { background: linear-gradient(135deg, ${t.bg_primary}, ${t.bg_secondary}) !important; transition: all 0.4s ease; }
        .rank-cell, .pts, .st-pts, .bh-title, .mi-match, .winner-name, .accent-col { color: ${t.primary} !important; }
        .kills, .mi-tourney, .bh-sub, .secondary-col { color: ${t.secondary} !important; }
        .mi-map { color: ${customMapColor} !important; }
    `;
}
syncTheme(); setInterval(syncTheme, 2000);

function initParticles() {
    const canvas = document.querySelector(".particles-canvas");
    if(!canvas) return;
    const ctx = canvas.getContext("2d");
    let w = canvas.width = window.innerWidth;
    let h = canvas.height = window.innerHeight;
    const parts = Array.from({length: 40}, () => ({
        x: Math.random() * w, y: Math.random() * h,
        r: Math.random() * 2 + 1,
        vx: (Math.random() - 0.5) * 0.4, vy: -Math.random() * 0.7 - 0.2,
        alpha: Math.random() * 0.7 + 0.2
    }));
    function loop() {
        ctx.clearRect(0,0,w,h);
        parts.forEach(p => {
            p.x += p.vx; p.y += p.vy;
            if(p.y < 0) { p.y = h; p.x = Math.random() * w; }
            ctx.fillStyle = `rgba(0, 229, 255, ${p.alpha})`;
            ctx.shadowBlur = 8; ctx.shadowColor = "#00e5ff";
            ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        });
        requestAnimationFrame(loop);
    }
    loop();
}
window.addEventListener("DOMContentLoaded", initParticles);
</script>
"""

BROADCAST_CORE_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700;800&family=Orbitron:wght@700;900&display=swap');

:root {
    --gold: #f2c400;
    --cyan: #00e5ff;
    --red: #ff2a55;
    --dark-1: #06090e;
    --dark-2: #0d121a;
    --chroma: #00ff00;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body, html { width: 100vw; height: 100vh; overflow: hidden; background: transparent; font-family: 'Rajdhani', sans-serif; color: #fff; }

.screen-bg {
    position: fixed; inset: 0;
    background: radial-gradient(circle at center, #0e1624 0%, #04060a 100%);
    z-index: 1; overflow: hidden;
}

.screen-bg::before {
    content: ''; position: absolute; inset: -50%;
    background-image: 
        linear-gradient(rgba(0, 229, 255, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 229, 255, 0.05) 1px, transparent 1px);
    background-size: 50px 50px;
    transform: perspective(600px) rotateX(45deg);
    animation: gridDrift 16s linear infinite;
}

@keyframes gridDrift {
    0% { transform: perspective(600px) rotateX(45deg) translateY(0); }
    100% { transform: perspective(600px) rotateX(45deg) translateY(50px); }
}

.particles-canvas { position: absolute; inset: 0; z-index: 2; pointer-events: none; }

.cyber-card {
    background: linear-gradient(135deg, rgba(14, 23, 38, 0.9), rgba(7, 12, 20, 0.95));
    border: 1px solid rgba(242, 196, 0, 0.4);
    clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 18px 100%, 0 calc(100% - 18px));
    box-shadow: 0 15px 45px rgba(0,0,0,0.85);
    position: relative;
    backdrop-filter: blur(8px);
}

.chroma-box {
    background-color: var(--chroma) !important;
    background-image: none !important;
}
"""

# =========================================================
# ADMIN PANEL (WITH 3 DOTS MENU & OVERLAY STUDIO)
# =========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Admin Live Control</title>
<style id="adminDynamicStyle">
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');

:root {
    --bg-main: #06090e;
    --card-bg: #0d121a;
    --gold: #f2c400;
    --cyan: #00e5ff;
    --red: #ff2a55;
    --green: #00ff66;
    --border: #1a2332;
}

* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    margin: 0; padding: 0;
    background: var(--bg-main);
    color: #ffffff;
    font-family: 'Rajdhani', sans-serif;
    user-select: none;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

.main-header {
    background: linear-gradient(180deg, #101926 0%, #080c13 100%);
    border-bottom: 2px solid var(--gold);
    padding: 8px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.header-brand { display: flex; align-items: center; gap: 8px; }
.header-logo { width: 36px; height: 36px; object-fit: contain; border-radius: 6px; border: 1px solid var(--gold); background: #000; }
.brand-text h1 { margin: 0; font-family: 'Teko', sans-serif; font-size: 24px; color: var(--gold); line-height: 1; letter-spacing: 1px; }
.brand-text span { font-size: 11px; font-weight: 800; color: var(--cyan); letter-spacing: 1.5px; display: block; }

.top-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #0a0e16;
    border-bottom: 1px solid var(--border);
    padding: 6px 8px;
    position: sticky;
    top: 0;
    z-index: 100;
    gap: 6px;
}
.nav-left { display: flex; align-items: center; gap: 6px; }
.nav-logo-mini { width: 26px; height: 26px; object-fit: contain; border-radius: 4px; border: 1px solid var(--gold); }
.btn-menu { background: #161f2e; border: 1px solid #2a374a; color: var(--gold); padding: 4px 8px; border-radius: 5px; font-size: 16px; font-weight: 800; cursor: pointer; }
.live-badge { color: var(--green); font-size: 14px; font-weight: 800; }

.user-badge {
    background: rgba(242,196,0,0.12);
    border: 1px solid rgba(242,196,0,0.3);
    color: var(--gold);
    font-size: 11px;
    font-weight: 800;
    padding: 3px 6px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    gap: 4px;
}

.nav-actions { display: flex; align-items: center; gap: 4px; }
.nav-btn {
    background: #141d2b;
    border: 1px solid #222f42;
    color: #cbd5e1;
    padding: 5px 8px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 800;
    text-decoration: none;
    cursor: pointer;
    touch-action: manipulation;
}
.nav-btn.gold { color: var(--gold); border-color: rgba(242,196,0,0.4); }
.nav-btn.green { color: var(--green); border-color: rgba(0,255,102,0.4); }
.nav-btn.red { color: var(--red); border-color: rgba(255,42,85,0.4); }
.nav-btn.cyan { color: var(--cyan); border-color: rgba(0,229,255,0.4); }

.match-config-box {
    background: #0b111a;
    border-bottom: 1px solid var(--border);
    padding: 6px 8px;
}
.match-config-box summary {
    font-size: 13px;
    font-weight: 800;
    color: var(--gold);
    cursor: pointer;
}
.cfg-grid {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 6px;
}
.cfg-input {
    background: #06090e;
    color: #fff;
    border: 1px solid #222f42;
    padding: 5px 8px;
    font-size: 12px;
    font-weight: 800;
    border-radius: 4px;
    outline: none;
    font-family: 'Rajdhani', sans-serif;
}

.obs-strip {
    display: flex;
    gap: 5px;
    padding: 5px 8px;
    background: #070a0f;
    border-bottom: 1px solid #131a24;
    overflow-x: auto;
}
.obs-badge {
    background: #111722;
    border: 1px solid #202b3a;
    color: #b0c4de;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 800;
    text-decoration: none;
    white-space: nowrap;
}
.obs-badge:hover { color: #fff; border-color: var(--cyan); }

.quick-strip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 8px;
    background: #0a0f16;
    border-bottom: 1px solid #141c27;
}
.search-input {
    flex: 1;
    background: #0d141f;
    border: 1px solid #1e293b;
    color: #fff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    outline: none;
    font-family: 'Rajdhani', sans-serif;
    font-weight: 700;
}

.teams-list { display: flex; flex-direction: column; flex: 1; }

.t-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 40px;
    padding: 0 6px;
    border-bottom: 1px solid #141d2a;
    background: var(--card-bg) !important;
    overflow: hidden;
    contain: layout paint;
}

.t-row.absent-mode { opacity: 0.35; filter: grayscale(1); }
.t-row.eliminated { background: rgba(45, 12, 18, 0.95) !important; }
.t-row.winner { background: linear-gradient(90deg, rgba(65, 48, 6, 0.95), rgba(24, 18, 2, 0.95)) !important; border-left: 3px solid var(--gold); }

.slot-num {
    width: 26px;
    font-size: 13px;
    font-weight: 800;
    color: #7b8ea6;
    flex-shrink: 0;
}

.t-main-info {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    padding-right: 4px;
}

.admin-t-logo {
    width: 22px;
    height: 22px;
    object-fit: contain;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
    border: 1px solid #1e293b;
    cursor: pointer;
    flex-shrink: 0;
    transition: 0.2s;
}
.admin-t-logo:hover { border-color: var(--cyan); transform: scale(1.1); }

.t-name {
    font-size: 13px;
    font-weight: 800;
    color: #ffffff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: uppercase;
    min-width: 60px;
    flex: 1;
}

.sel-pcount {
    background: #111823;
    color: var(--cyan);
    border: 1px solid #222f42;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 800;
    padding: 2px 3px;
    outline: none;
    cursor: pointer;
    flex-shrink: 0;
}

.btn-toggle-absent {
    background: rgba(0, 255, 102, 0.15);
    border: 1px solid var(--green);
    color: var(--green);
    font-size: 10px;
    font-weight: 800;
    padding: 3px 5px;
    border-radius: 3px;
    cursor: pointer;
    flex-shrink: 0;
    touch-action: manipulation;
}
.btn-toggle-absent.is-absent {
    background: rgba(255, 42, 85, 0.15);
    border-color: var(--red);
    color: var(--red);
}

.p-dots {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 0 4px;
    flex-shrink: 0;
}

.dot {
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 6px rgba(0,255,102,0.4);
    cursor: pointer;
    transition: transform 0.08s, background 0.1s;
    touch-action: manipulation;
}
.dot:active { transform: scale(1.3); }
.dot.dead { 
    background: var(--red) !important; 
    box-shadow: 0 0 6px rgba(255,42,85,0.7) !important;
    border: none !important;
}

.t-ctrls {
    display: flex;
    align-items: center;
    gap: 3px;
    flex-shrink: 0;
}
.btn-k {
    width: 26px;
    height: 26px;
    background: #16202e;
    border: 1px solid #2b3a4f;
    color: #fff;
    border-radius: 3px;
    font-size: 14px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    touch-action: manipulation;
}
.btn-k.plus { color: var(--cyan); border-color: rgba(0,229,255,0.4); }
.btn-k:active { transform: scale(0.9); }

.k-val {
    min-width: 18px;
    text-align: center;
    font-size: 14px;
    font-weight: 800;
    color: #fff;
}

.pos-select-mini {
    background: #111823;
    color: #cbd5e1;
    border: 1px solid #222f42;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 800;
    padding: 2px;
    width: 58px;
    outline: none;
    cursor: pointer;
}

.btn-w {
    background: rgba(255, 42, 85, 0.15);
    border: 1px solid var(--red);
    color: var(--red);
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 800;
    border-radius: 3px;
    cursor: pointer;
    touch-action: manipulation;
}
.btn-w:active { transform: scale(0.9); }

.sidebar-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: none; }
.sidebar-overlay.show { display: block; }
.sidebar-menu { position: fixed; top: 0; left: -260px; width: 260px; height: 100%; background: #0c1219; border-right: 1px solid #1f2d3d; z-index: 1100; transition: 0.25s; padding: 15px; }
.sidebar-menu.open { left: 0; }
.menu-item { display: block; padding: 10px; color: #cbd5e1; text-decoration: none; font-size: 13px; font-weight: 700; border-radius: 4px; margin-bottom: 6px; background: #131b26; }

.modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; display: none; align-items: center; justify-content: center; padding: 15px; }
.modal.show { display: flex; }
.modal-content { background: #0f1722; border: 1px solid var(--gold); border-radius: 8px; width: 100%; max-width: 480px; max-height: 88vh; overflow-y: auto; padding: 14px; }

.site-footer {
    background: #080c13;
    border-top: 1px solid var(--border);
    padding: 12px 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    margin-top: auto;
}
.footer-social-links { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
.social-link { background: #141d2b; border: 1px solid var(--border); color: #cbd5e1; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 800; text-decoration: none; }
.footer-copy { font-size: 10px; color: #64748b; font-weight: 700; text-align: center; }

.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--gold); color: #000; padding: 5px 18px; border-radius: 20px; font-weight: 800; font-size: 11px; opacity: 0; visibility: hidden; transition: 0.2s; z-index: 9999; }
.toast.show { opacity: 1; visibility: visible; }
</style>
</head>
<body>

<div class="main-header">
    <div class="header-brand">
        <img src="/static/logos/server_logo.webp" class="header-logo" alt="Logo" onerror="this.style.display='none'">
        <div class="brand-text">
            <h1>ESPORTS NATION INDIA</h1>
            <span>PRODUCTION ADMIN PANEL</span>
        </div>
    </div>
</div>

<div class="top-nav">
    <div class="nav-left">
        <img src="/static/logos/server_logo.webp" class="nav-logo-mini" alt="Logo" onerror="this.style.display='none'">
        <!-- 3 DOTS MENU -->
        <button class="btn-menu" onclick="toggleMenu()" title="Open Menu">⋮</button>
        <span class="live-badge" id="topTeams">0 ALIVE</span>
        <div class="user-badge">🟢 <span id="userCountText">1 USERS</span></div>
    </div>
    <div class="nav-actions">
        <button class="nav-btn" onclick="uiUndo()" title="Undo">↩</button>
        <button class="nav-btn" onclick="uiRedo()" title="Redo">↪</button>
        <button class="nav-btn green" onclick="resetMatchState()">NEW M</button>
        <button class="nav-btn gold" onclick="saveMatchOverall()">SAVE</button>
        <button class="nav-btn red" onclick="uiResetAll()">RESET</button>
    </div>
</div>

<details class="match-config-box">
    <summary>⚙️ MATCH SETUP (Click to Edit) ▾</summary>
    <div class="cfg-grid">
        <input type="text" id="cfgTourney" class="cfg-input" style="flex:2;" placeholder="Tournament Name" value="ESPORTS NATION INDIA">
        <input type="text" id="cfgMatch" class="cfg-input" style="flex:1;" placeholder="Match (e.g. MATCH 1)" value="MATCH 1">
        <select id="cfgMap" class="cfg-input" style="flex:1;">
            <option value="ERANGEL">ERANGEL</option>
            <option value="MIRAMAR">MIRAMAR</option>
            <option value="RONDO">RONDO</option>
            <option value="SANHOK">SANHOK</option>
        </select>
        <button class="nav-btn gold" style="padding:5px 10px;" onclick="saveConfigData()">SAVE</button>
    </div>
</details>

<div class="obs-strip">
    <a href="/overlay/starting" target="_blank" class="obs-badge" style="color:var(--cyan); border-color:rgba(0,229,255,0.4);">⏳ STARTING</a>
    <a href="/overlay/caster" target="_blank" class="obs-badge" style="color:var(--gold); border-color:rgba(242,196,0,0.4);">🎙️ CASTER DESK</a>
    <a href="/overlay/pt" target="_blank" class="obs-badge">📊 LIVE PT</a>
    <a href="/overlay/mapgame" target="_blank" class="obs-badge">🗺️ MINI-MAP PiP</a>
    <a href="/overlay/dualpov" target="_blank" class="obs-badge" style="color:#ff7700;">⚔️ DUAL POV</a>
    <a href="/overlay/standings" target="_blank" class="obs-badge" style="color:var(--gold);">🏆 STANDINGS</a>
    <a href="/overlay/elimination" target="_blank" class="obs-badge" style="color:var(--red);">💀 ELIM CARD</a>
    <a href="/overlay/wwcd" target="_blank" class="obs-badge" style="color:var(--gold);">🍗 WWCD</a>
    <a href="/overlay/brb" target="_blank" class="obs-badge">☕ BRB BREAK</a>
    <a href="/overlay/ending" target="_blank" class="obs-badge" style="color:#c084fc;">🏁 ENDING</a>
</div>

<div class="quick-strip">
    <input type="text" id="searchInput" class="search-input" placeholder="Search..." oninput="filterTeams()">
    <button class="nav-btn gold" onclick="openSlotsModal()">📋 SLOTS</button>
    <button class="nav-btn gold" onclick="adjustSlots(1)">+ Slot</button>
    <button class="nav-btn red" onclick="adjustSlots(-1)">- Slot</button>
    <button class="nav-btn red" onclick="deleteAllSlots()">CLR</button>
</div>

<div id="teamsContainer" class="teams-list"></div>

<footer class="site-footer">
    <div class="footer-social-links">
        <a href="https://discord.gg/esportsindia" target="_blank" class="social-link">🎮 Discord</a>
        <a href="https://www.instagram.com/esportsnation.india" target="_blank" class="social-link">📷 Instagram</a>
        <a href="https://youtube.com/@esportnationindia" target="_blank" class="social-link">▶️ YouTube</a>
    </div>
    <div class="footer-copy">© 2026 ESPORTS NATION INDIA PRODUCTION. ALL RIGHTS RESERVED.</div>
</footer>

<!-- 3 DOTS SIDEBAR MENU -->
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleMenu()"></div>
<div class="sidebar-menu" id="sidebarMenu">
    <div style="display:flex; justify-content:space-between; margin-bottom:15px; border-bottom:1px solid #1e293b; padding-bottom:8px;">
        <span style="font-weight:800; color:var(--gold); font-size:15px;">OPTIONS</span>
        <button onclick="toggleMenu()" style="background:none; border:none; color:#fff; font-size:16px; cursor:pointer;">✕</button>
    </div>
    
    <a href="#" class="menu-item" style="color:var(--cyan); border:1px solid rgba(0,229,255,0.4);" onclick="toggleMenu(); openStudioModal();">🎬 Broadcast Overlays Studio</a>
    <a href="#" class="menu-item" onclick="toggleMenu(); openSlotsModal();">📋 Paste Discord Slot List</a>
    <a href="#" class="menu-item" style="color:var(--gold);" onclick="toggleMenu(); openObsThemeModal();">🎨 OBS Overlay Themes</a>
    <a href="#" class="menu-item" style="color:var(--cyan);" onclick="toggleMenu(); openAdminThemeModal();">🖥️ Admin Panel Themes</a>
    <a href="#" class="menu-item" onclick="toggleMenu(); openHistoryModal();">📚 Match Archive (Scores)</a>
    <a href="#" class="menu-item" style="color:var(--red); margin-top:20px;" onclick="toggleMenu(); clearMatchHistory();">🗑️ Clear Match History</a>
</div>

<!-- BROADCAST OVERLAY STUDIO MODAL -->
<div class="modal" id="studioModal">
    <div class="modal-content">
        <h3 style="margin:0 0 10px 0; font-size:16px; color:var(--cyan);">🎬 BROADCAST OVERLAYS FULL ACCESS</h3>
        <p style="font-size:11px; color:#8fa0b5; margin-top:0;">Customize caster names, timers, dual pov and game frames live.</p>

        <label style="font-size:11px; color:var(--gold); font-weight:800;">🎙️ CASTER 1 (LEFT DESK)</label>
        <div style="display:flex; gap:6px; margin-bottom:10px;">
            <input type="text" id="stCaster1" class="cfg-input" style="flex:1;" placeholder="Name (e.g. CASTER ALPHA)">
            <input type="text" id="stRole1" class="cfg-input" style="flex:1;" placeholder="Role (e.g. PLAY-BY-PLAY)">
        </div>

        <label style="font-size:11px; color:var(--gold); font-weight:800;">🎙️ CASTER 2 (RIGHT DESK)</label>
        <div style="display:flex; gap:6px; margin-bottom:10px;">
            <input type="text" id="stCaster2" class="cfg-input" style="flex:1;" placeholder="Name (e.g. ANALYST BRAVO)">
            <input type="text" id="stRole2" class="cfg-input" style="flex:1;" placeholder="Role (e.g. COLOR COMMENTATOR)">
        </div>

        <label style="font-size:11px; color:#ff7700; font-weight:800; display:block;">⚔️ DUAL POV TEAM / PLAYER 1 (LEFT)</label>
        <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input type="text" id="stDual1Name" class="cfg-input" style="flex:2;" placeholder="Custom Name (Khali = Auto Alive)">
            <input type="text" id="stDual1Sub" class="cfg-input" style="flex:1;" placeholder="Tag (e.g. POV 1)">
        </div>

        <label style="font-size:11px; color:#ff7700; font-weight:800; display:block;">⚔️ DUAL POV TEAM / PLAYER 2 (RIGHT)</label>
        <div style="display:flex; gap:6px; margin-bottom:10px;">
            <input type="text" id="stDual2Name" class="cfg-input" style="flex:2;" placeholder="Custom Name (Khali = Auto Alive)">
            <input type="text" id="stDual2Sub" class="cfg-input" style="flex:1;" placeholder="Tag (e.g. POV 2)">
        </div>

        <label style="font-size:11px; color:#cbd5e1; font-weight:800;">⏳ STREAM STARTING COUNTDOWN (MINUTES)</label>
        <input type="number" id="stTimerMin" class="cfg-input" style="width:100%; margin-bottom:10px;" placeholder="5">

        <label style="font-size:11px; color:#cbd5e1; font-weight:800;">📢 HEADLINE / TICKER</label>
        <input type="text" id="stHeadline" class="cfg-input" style="width:100%; margin-bottom:10px;" placeholder="GRAND FINALS - DAY 1">

        <label style="font-size:11px; color:var(--cyan); font-weight:800;">🟩 GREEN SCREEN (CHROMA KEY) MODE FOR GAMEPLAY</label>
        <select id="stChromaKey" class="cfg-input" style="width:100%; margin-bottom:12px;">
            <option value="true">ENABLED (Solid Green Screen Cutout)</option>
            <option value="false">DISABLED (Transparent Cutout)</option>
        </select>

        <label style="font-size:11px; color:var(--cyan); font-weight:800;">🗺️ MINI-MAP HUD POSITION</label>
        <select id="stMapPos" class="cfg-input" style="width:100%; margin-bottom:14px;">
            <option value="bottom-right">Bottom-Right Corner</option>
            <option value="bottom-left">Bottom-Left Corner</option>
            <option value="top-right">Top-Right Corner</option>
        </select>

        <div style="display:flex; gap:6px;">
            <button class="nav-btn cyan" style="flex:1; padding:7px;" onclick="saveStudioData()">SAVE & APPLY LIVE</button>
            <button class="nav-btn red" style="padding:7px;" onclick="closeModal('studioModal')">CLOSE</button>
        </div>
    </div>
</div>

<!-- SLOTS MODAL -->
<div class="modal" id="slotsModal">
    <div class="modal-content">
        <h3 style="margin:0 0 8px 0; font-size:16px; color:var(--cyan);">📋 PASTE DISCORD SLOTS</h3>
        <p style="font-size:11px; color:#8b9bb0; margin-top:0;">Slot numbering starts from <b>Slot #3</b> onwards.</p>
        <textarea id="slotInput" style="width:100%; height:130px; background:#080c12; color:#fff; border:1px solid #1e293b; padding:8px; font-family:'Rajdhani'; font-size:13px; border-radius:4px;" placeholder="Team 1&#10;Team 2&#10;Team 3..."></textarea>
        <div style="display:flex; gap:6px; margin-top:8px;">
            <button class="nav-btn green" style="flex:1; padding:7px;" onclick="importSlots()">IMPORT SLOTS</button>
            <button class="nav-btn red" style="padding:7px;" onclick="closeModal('slotsModal')">CLOSE</button>
        </div>
    </div>
</div>

<!-- OBS THEME MODAL -->
<div class="modal" id="obsThemeModal">
    <div class="modal-content">
        <h3 style="margin:0 0 8px 0; font-size:16px; color:var(--gold);">📡 OBS OVERLAY THEMES</h3>
        <label style="font-size:11px; color:#b0c4de;">CHOOSE OVERLAY PALETTE</label>
        <select id="tmPresetSelect" onchange="onObsPresetDropdownChange()" style="width:100%; padding:6px; background:#080c12; color:#fff; border:1px solid #1e293b; border-radius:4px; margin-top:4px; margin-bottom:10px; font-size:13px;">
            <option value="Classic Gold">Classic Gold (Golden Glow)</option>
            <option value="Royal Blue">Royal Blue (Deep Ocean)</option>
            <option value="Crimson Red">Crimson Red (Aggressive Fire)</option>
            <option value="Cyber Purple">Cyber Purple (Neon Synthwave)</option>
            <option value="Neon Cyber">Neon Cyber (Cyan & Magenta)</option>
            <option value="Sunset Orange">Sunset Orange (Warm Gradient)</option>
            <option value="Emerald Neon">Emerald Neon (Pro League Green)</option>
            <option value="Rose Gold">Rose Gold (Pyaara Pink Theme)</option>
        </select>

        <label style="font-size:11px; color:#b0c4de;">🗺️ MAP NAME COLOR</label>
        <div style="display:flex; align-items:center; gap:8px; margin-top:4px; margin-bottom:14px;">
            <input type="color" id="tmMapColorPicker" style="width:40px; height:32px; background:none; border:1px solid #1e293b; border-radius:4px; cursor:pointer;" value="#ffffff">
            <span style="font-size:11px; color:#7b8ea6;">Click to choose custom map color</span>
        </div>

        <div style="display:flex; gap:6px;">
            <button class="nav-btn gold" style="flex:1; padding:7px;" onclick="saveObsTheme()">SAVE OVERLAY THEME</button>
            <button class="nav-btn red" style="padding:7px;" onclick="closeModal('obsThemeModal')">CLOSE</button>
        </div>
    </div>
</div>

<!-- ADMIN THEME MODAL -->
<div class="modal" id="adminThemeModal">
    <div class="modal-content">
        <h3 style="margin:0 0 8px 0; font-size:16px; color:var(--cyan);">🖥️ ADMIN PANEL THEME</h3>
        <label style="font-size:11px; color:#b0c4de;">CHOOSE ADMIN THEME PALETTE</label>
        <select id="adminThemeSelect" style="width:100%; padding:6px; background:#080c12; color:#fff; border:1px solid #1e293b; border-radius:4px; margin-top:4px; margin-bottom:12px; font-size:13px;"></select>
        <div style="display:flex; gap:6px;">
            <button class="nav-btn cyan" style="flex:1; padding:7px;" onclick="saveAdminTheme()">APPLY ADMIN THEME</button>
            <button class="nav-btn red" style="padding:7px;" onclick="closeModal('adminThemeModal')">CLOSE</button>
        </div>
    </div>
</div>

<!-- HISTORY MODAL -->
<div class="modal" id="historyModal">
    <div class="modal-content" style="max-width:550px;">
        <h3 style="margin:0 0 10px 0; color:var(--gold); font-size:16px;">📚 DETAILED MATCH ARCHIVE</h3>
        <div id="historyListContainer"></div>
        <button class="nav-btn red" style="width:100%; margin-top:8px; padding:6px;" onclick="closeModal('historyModal')">CLOSE</button>
    </div>
</div>

<div id="toast" class="toast">Saved</div>

<!-- HIDDEN LOGO UPLOAD INPUT -->
<input type="file" id="logoUploadInput" accept="image/png, image/jpeg, image/webp, image/gif" style="display:none" onchange="handleLogoUpload(this)">

<script>
let teamsData = [];
let allThemesData = { matches: {}, admin_theme: "Classic Gold" };
let builtinPresetsData = {};
let isSyncing = false;
let lastKnownHash = "";
const mySessionId = "usr_" + Math.random().toString(36).substring(2, 9);
let uploadTeamId = null;

function applyAdminTheme(paletteName) {
    const t = builtinPresetsData[paletteName] || builtinPresetsData["Classic Gold"];
    if(!t) return;
    document.documentElement.style.setProperty('--gold', t.primary);
    document.documentElement.style.setProperty('--cyan', t.secondary);
    document.documentElement.style.setProperty('--bg-main', t.bg_primary);
    document.documentElement.style.setProperty('--card-bg', t.bg_secondary);
}

async function pingHeartbeat() {
    try {
        const res = await fetch("/api/ping?cid=" + mySessionId);
        if(res.ok) {
            const data = await res.json();
            const count = data.users || 1;
            document.getElementById("userCountText").innerText = count + (count > 1 ? " USERS" : " USER");
        }
    } catch(e){}
}
setInterval(pingHeartbeat, 3000);
pingHeartbeat();

async function loadConfigData() {
    try {
        const [cRes, thmRes] = await Promise.all([fetch("/api/config"), fetch("/api/themes")]);
        if(cRes.ok) {
            const cfg = await cRes.json();
            document.getElementById("cfgTourney").value = cfg.tournament || "ESPORTS NATION INDIA";
            document.getElementById("cfgMatch").value = cfg.match || "MATCH 1";
            document.getElementById("cfgMap").value = cfg.map || "ERANGEL";
            
            document.getElementById("stCaster1").value = cfg.caster1_name || "CASTER ALPHA";
            document.getElementById("stRole1").value = cfg.caster1_title || "PLAY-BY-PLAY";
            document.getElementById("stCaster2").value = cfg.caster2_name || "ANALYST BRAVO";
            document.getElementById("stRole2").value = cfg.caster2_title || "COLOR COMMENTARY";
            document.getElementById("stTimerMin").value = cfg.start_timer_min || "5";
            document.getElementById("stHeadline").value = cfg.broadcast_headline || "GRAND FINALS - DAY 1";
            document.getElementById("stChromaKey").value = String(cfg.chroma_key_mode !== false);
            document.getElementById("stMapPos").value = cfg.map_position || "bottom-right";
            
            document.getElementById("stDual1Name").value = cfg.dual_team1_name || "";
            document.getElementById("stDual1Sub").value = cfg.dual_team1_sub || "POV 1";
            document.getElementById("stDual2Name").value = cfg.dual_team2_name || "";
            document.getElementById("stDual2Sub").value = cfg.dual_team2_sub || "POV 2";
        }
        if(thmRes.ok) {
            const thmData = await thmRes.json();
            allThemesData = thmData.themes || { matches: {}, admin_theme: "Classic Gold" };
            builtinPresetsData = thmData.presets || {};
            applyAdminTheme(allThemesData.admin_theme || "Classic Gold");
        }
    } catch(e){}
}

async function saveConfigData() {
    const payload = {
        tournament: document.getElementById("cfgTourney").value,
        match: document.getElementById("cfgMatch").value,
        map: document.getElementById("cfgMap").value
    };
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });
    showToast("Config Saved!");
}

async function saveStudioData() {
    const payload = {
        caster1_name: document.getElementById("stCaster1").value,
        caster1_title: document.getElementById("stRole1").value,
        caster2_name: document.getElementById("stCaster2").value,
        caster2_title: document.getElementById("stRole2").value,
        start_timer_min: document.getElementById("stTimerMin").value,
        broadcast_headline: document.getElementById("stHeadline").value,
        chroma_key_mode: document.getElementById("stChromaKey").value === "true",
        map_position: document.getElementById("stMapPos").value,
        dual_team1_name: document.getElementById("stDual1Name").value,
        dual_team1_sub: document.getElementById("stDual1Sub").value,
        dual_team2_name: document.getElementById("stDual2Name").value,
        dual_team2_sub: document.getElementById("stDual2Sub").value
    };
    await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });
    showToast("Broadcast Settings Updated Live! 🎬");
    closeModal('studioModal');
}

async function syncAdminData() {
    if(isSyncing) return;
    isSyncing = true;
    try {
        const res = await fetch("/api/teams?t=" + Date.now());
        if (!res.ok) return;
        const freshData = await res.json();
        
        const currentHash = JSON.stringify(freshData);
        if(currentHash === lastKnownHash) {
            isSyncing = false;
            return;
        }
        lastKnownHash = currentHash;
        teamsData = freshData;

        const activeTeams = teamsData.filter(t => !t.absent);
        const aliveTeams = activeTeams.filter(t => t.players.some(p => p === 1));
        let at = aliveTeams.length;
        document.getElementById("topTeams").innerText = at + " ALIVE";

        teamsData.forEach(team => {
            const row = document.getElementById(`row-${team.id}`);
            if(row) {
                const kEl = document.getElementById(`k-${team.id}`);
                if(kEl) kEl.innerText = team.kills;
                
                const posSel = document.getElementById(`pos-sel-${team.id}`);
                if(posSel && String(posSel.value) !== String(team.position)) {
                    posSel.value = team.position;
                }
                
                team.players.forEach((val, idx) => {
                    const dot = document.getElementById(`dot-${team.id}-${idx}`);
                    if(dot) {
                        if(val) dot.classList.remove("dead");
                        else dot.classList.add("dead");
                    }
                });

                const isDead = (team.players.filter(p=>p===1).length === 0);
                const isWinner = (!team.absent && ((activeTeams.length > 1 && at === 1 && aliveTeams[0].id === team.id) || team.position === 1));
                
                const absBtn = document.getElementById(`abs-${team.id}`);
                if(absBtn) {
                    if(team.absent) {
                        absBtn.className = "btn-toggle-absent is-absent";
                        absBtn.innerText = "ABS";
                    } else {
                        absBtn.className = "btn-toggle-absent";
                        absBtn.innerText = "PRE";
                    }
                }
                
                // Update logo visually if changed
                const logoImg = row.querySelector('.admin-t-logo');
                if(logoImg) {
                    const expectedSrc = team.logo || 'https://dummyimage.com/40x40/111823/f2c400&text=+';
                    if(!logoImg.src.includes(expectedSrc) && !expectedSrc.includes('dummyimage')) {
                        logoImg.src = expectedSrc;
                    }
                }

                if(team.absent) row.className = "t-row absent-mode searchable";
                else if(isWinner) row.className = "t-row winner searchable";
                else if(isDead && team.position > 0) row.className = "t-row eliminated searchable";
                else row.className = "t-row searchable";
            }
        });
    } catch(e){
    } finally {
        isSyncing = false;
    }
}
setInterval(syncAdminData, 1000);

function renderAllTeams() {
    const container = document.getElementById("teamsContainer");
    let html = "";
    let displayTeams = [...teamsData].sort((a,b) => a.id - b.id);
    const totalCount = displayTeams.length;

    displayTeams.forEach(team => {
        const isDead = team.players.filter(p => p === 1).length === 0;
        let pHTML = "";
        team.players.forEach((a, idx) => {
            pHTML += `<div id="dot-${team.id}-${idx}" class="dot ${a ? '' : 'dead'}" onclick="fastTogglePlayer(${team.id}, ${idx})"></div>`;
        });

        const pCount = team.players.length;

        let posOpts = `<option value="0" ${team.position==0?'selected':''}>Alive</option>`;
        for(let i = 1; i <= totalCount; i++) {
            posOpts += `<option value="${i}" ${team.position==i?'selected':''}>#${i}</option>`;
        }
        
        const logoSrc = team.logo ? team.logo : 'https://dummyimage.com/40x40/111823/f2c400&text=+';

        html += `
            <div id="row-${team.id}" class="t-row searchable ${team.absent ? 'absent-mode' : (team.position === 1 ? 'winner' : (isDead ? 'eliminated' : ''))}" data-name="${(team.name || '').toLowerCase()}">
                <div class="slot-num">#${team.id}</div>
                <div class="t-main-info">
                    <img class="admin-t-logo" src="${logoSrc}" onclick="triggerLogoUpload(${team.id})" title="Click to change logo">
                    <span class="t-name">${team.name}</span>
                    <select class="sel-pcount" onchange="uiSetPlayerCount(${team.id}, this.value)">
                        <option value="4" ${pCount==4?'selected':''}>4P</option>
                        <option value="3" ${pCount==3?'selected':''}>3P</option>
                        <option value="2" ${pCount==2?'selected':''}>2P</option>
                        <option value="1" ${pCount==1?'selected':''}>1P</option>
                    </select>
                    <button id="abs-${team.id}" class="btn-toggle-absent ${team.absent ? 'is-absent' : ''}" onclick="fastToggleAbsent(${team.id})">${team.absent ? 'ABS' : 'PRE'}</button>
                </div>
                <div class="p-dots">${pHTML}</div>
                <div class="t-ctrls">
                    <button class="btn-k" onclick="fastChangeKills(${team.id}, -1)">-</button>
                    <span id="k-${team.id}" class="k-val">${team.kills}</span>
                    <button class="btn-k plus" onclick="fastChangeKills(${team.id}, 1)">+</button>
                    <select id="pos-sel-${team.id}" class="pos-select-mini" onchange="uiUpdatePos(${team.id}, this.value)">${posOpts}</select>
                    <button class="btn-w" onclick="fastEliminate(${team.id})">W</button>
                </div>
            </div>`;
    });
    container.innerHTML = html;
    filterTeams();
    syncAdminData();
}

function filterTeams() {
    const q = (document.getElementById("searchInput").value || '').toLowerCase().trim();
    document.querySelectorAll(".searchable").forEach(r => {
        r.style.display = (q === "" || (r.dataset.name && r.dataset.name.includes(q))) ? "flex" : "none";
    });
}

function triggerLogoUpload(id) {
    uploadTeamId = id;
    document.getElementById("logoUploadInput").click();
}

async function handleLogoUpload(input) {
    if(!input.files || !input.files[0] || !uploadTeamId) return;
    const formData = new FormData();
    formData.append("logo", input.files[0]);
    formData.append("id", uploadTeamId);

    try {
        showToast("Uploading Logo...");
        const res = await fetch("/api/upload_logo", { method: "POST", body: formData });
        const d = await res.json();
        if(d.success) {
            showToast("Logo updated! ✅");
            loadTeams();
        } else {
            alert(d.error || "Upload failed");
        }
    } catch(e) {
        alert("Upload error. Check connection.");
    }
    input.value = ""; 
}

function toggleMenu() { 
    document.getElementById("sidebarMenu").classList.toggle("open"); 
    document.getElementById("sidebarOverlay").classList.toggle("show"); 
}
function closeModal(id) { document.getElementById(id).classList.remove("show"); }
function openSlotsModal() { document.getElementById("slotsModal").classList.add("show"); }
function openStudioModal() { document.getElementById("studioModal").classList.add("show"); }

async function openObsThemeModal() {
    document.getElementById("obsThemeModal").classList.add("show");
    const thmRes = await fetch("/api/themes");
    const thmJson = await thmRes.json();
    allThemesData = thmJson.themes || { matches: {} };
    builtinPresetsData = thmJson.presets || {};
    
    const preSel = document.getElementById("tmPresetSelect");
    preSel.innerHTML = "";
    const curMatch = document.getElementById("cfgMatch").value;
    const curPreset = (allThemesData.matches && allThemesData.matches[curMatch]) ? allThemesData.matches[curMatch].preset : "Classic Gold";
    Object.keys(builtinPresetsData).forEach(p => {
        const s = (curPreset === p) ? "selected" : "";
        preSel.innerHTML += `<option value="${p}" ${s}>${p}</option>`;
    });

    const curMapCol = (allThemesData.matches && allThemesData.matches[curMatch] && allThemesData.matches[curMatch].map_color) ? allThemesData.matches[curMatch].map_color : (builtinPresetsData[curPreset] ? builtinPresetsData[curPreset].map_color : "#ffffff");
    document.getElementById("tmMapColorPicker").value = curMapCol || "#ffffff";
}

function onObsPresetDropdownChange() {
    const pName = document.getElementById("tmPresetSelect").value;
    if(builtinPresetsData[pName] && builtinPresetsData[pName].map_color) {
        document.getElementById("tmMapColorPicker").value = builtinPresetsData[pName].map_color;
    }
}

async function saveObsTheme() {
    const curMatch = document.getElementById("cfgMatch").value;
    const pName = document.getElementById("tmPresetSelect").value;
    const mapColorVal = document.getElementById("tmMapColorPicker").value || "#ffffff";
    const themeObj = { preset: pName, ...builtinPresetsData[pName], map_color: mapColorVal };
    await fetch("/api/themes", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ match_key: curMatch, theme: themeObj }) 
    });
    showToast(`Overlay Theme & Map Color Saved!`);
    closeModal('obsThemeModal');
}

async function openAdminThemeModal() {
    document.getElementById("adminThemeModal").classList.add("show");
    const thmRes = await fetch("/api/themes");
    const thmJson = await thmRes.json();
    allThemesData = thmJson.themes || { matches: {}, admin_theme: "Classic Gold" };
    builtinPresetsData = thmJson.presets || {};
    
    const admSel = document.getElementById("adminThemeSelect");
    admSel.innerHTML = "";
    Object.keys(builtinPresetsData).forEach(p => {
        const s = (allThemesData.admin_theme === p) ? "selected" : "";
        admSel.innerHTML += `<option value="${p}" ${s}>${p}</option>`;
    });
}

async function saveAdminTheme() {
    const chosen = document.getElementById("adminThemeSelect").value;
    allThemesData.admin_theme = chosen;
    applyAdminTheme(chosen);
    await fetch("/api/themes", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ admin_theme: chosen })
    });
    showToast(`Admin Theme Applied!`);
    closeModal('adminThemeModal');
}

function showToast(msg) { 
    const t = document.getElementById("toast"); 
    t.innerText = msg; 
    t.classList.add("show"); 
    setTimeout(() => t.classList.remove("show"), 1200); 
}

async function loadTeams() { 
    try {
        const res = await fetch("/api/teams?t=" + Date.now()); 
        if(res.ok) {
            teamsData = await res.json(); 
            lastKnownHash = JSON.stringify(teamsData);
            renderAllTeams(); 
        }
    } catch(e){}
}

function fastChangeKills(id, amt) {
    const tm = teamsData.find(x => String(x.id) === String(id));
    if(tm) tm.kills = Math.max(0, (tm.kills || 0) + amt);
    const kElem = document.getElementById(`k-${id}`);
    if(kElem) {
        let cur = parseInt(kElem.innerText) || 0;
        kElem.innerText = Math.max(0, cur + amt);
    }
    fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, kills_change: amt}) });
}

function fastTogglePlayer(id, idx) {
    const tm = teamsData.find(x => String(x.id) === String(id));
    if(tm && tm.players && idx < tm.players.length) {
        tm.players[idx] = tm.players[idx] ? 0 : 1;
    }
    const dot = document.getElementById(`dot-${id}-${idx}`);
    if(dot) dot.classList.toggle("dead");
    fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, player: idx}) });
}

function fastEliminate(id) {
    const tm = teamsData.find(x => String(x.id) === String(id));
    if(tm && tm.players) {
        tm.players = tm.players.map(() => 0);
    }
    for(let i=0; i<4; i++){
        const dot = document.getElementById(`dot-${id}-${i}`);
        if(dot) dot.classList.add("dead");
    }
    const row = document.getElementById(`row-${id}`);
    if(row) row.classList.add("eliminated");
    fetch("/api/eliminate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id}) });
}

async function fastToggleAbsent(id) {
    const btn = document.getElementById(`abs-${id}`);
    const row = document.getElementById(`row-${id}`);
    const tm = teamsData.find(x => String(x.id) === String(id));
    
    let isNowAbs = false;
    if(tm) {
        tm.absent = !tm.absent;
        isNowAbs = tm.absent;
    } else if(btn) {
        isNowAbs = btn.innerText === "PRE";
    }

    if(btn) {
        btn.innerText = isNowAbs ? "ABS" : "PRE";
        if(isNowAbs) btn.classList.add("is-absent");
        else btn.classList.remove("is-absent");
    }
    if(row) {
        if(isNowAbs) row.classList.add("absent-mode");
        else row.classList.remove("absent-mode");
    }

    try {
        const res = await fetch("/api/toggle_absent", { 
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify({id: id}) 
        });
        const d = await res.json();
        if(d.success && d.absent !== undefined) {
            if(tm) tm.absent = d.absent;
        }
    } catch(e) {}
}

function uiUpdatePos(id, pos) { 
    const tm = teamsData.find(x => String(x.id) === String(id));
    if(tm) tm.position = parseInt(pos) || 0;
    fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, position: parseInt(pos)||0}) }); 
}

function uiSetPlayerCount(id, count) { 
    fetch("/api/update", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id, player_count: count}) }).then(loadTeams); 
}

async function uiUndo() { await fetch("/api/undo", { method: "POST" }); loadTeams(); showToast("Undo ↩"); }
async function uiRedo() { await fetch("/api/redo", { method: "POST" }); loadTeams(); showToast("Redo ↪"); }

async function adjustSlots(amount) {
    let count = teamsData.length + amount; if(count < 0) count = 0;
    await fetch("/api/adjust_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count}) });
    loadTeams();
}

async function deleteAllSlots() {
    if(!confirm("Clear all slots?")) return;
    await fetch("/api/create", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({count: 0}) });
    loadTeams();
    showToast("Slots Cleared!");
}

async function resetMatchState() { 
    if(!confirm("Reset current match kills/alive?")) return; 
    await fetch("/api/reset_match", { method: "POST" }); 
    loadTeams(); 
}

async function uiResetAll() { 
    if(!confirm("Reset ALL tournament data & scores to 0?")) return; 
    await fetch("/api/reset_all", { method: "POST" }); 
    loadTeams(); 
    showToast("Tournament Reset 0!"); 
}

async function saveMatchOverall() {
    if(!confirm("Save match to history?")) return;
    const res = await fetch("/api/save_match_overall", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({}) });
    const d = await res.json();
    if(res.ok) { 
        showToast("Full Match Data Saved! 💾"); 
        loadConfigData();
        loadTeams(); 
    }
    else alert(d.error || "Save error");
}

async function importSlots() {
    const raw = document.getElementById("slotInput").value;
    if(!raw.trim()) return alert("Paste slots!");
    let names = [];
    raw.split('\n').forEach(line => {
        let c = line.trim();
        if(c) names.push(c.replace(/^(?:slot\s*#?\d+[\s\-\→\:\.\|]*|\#?\d+[\.\-\)\:\|]+\s*)/i, '').trim());
    });
    await fetch("/api/import_slots", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({names}) });
    closeModal("slotsModal"); loadTeams(); showToast("Slots Imported (Starts Slot #3)!");
}

async function openHistoryModal() {
    document.getElementById("historyModal").classList.add("show");
    const res = await fetch("/api/history"); const hist = await res.json();
    const c = document.getElementById("historyListContainer");
    if(!hist.length) { c.innerHTML = "<p style='color:#7b8ea6; text-align:center;'>No saved matches.</p>"; return; }
    
    let h = "";
    hist.slice().reverse().forEach(m => {
        let rows = "";
        (m.teams || []).sort((a,b)=>(b.total_pts||0)-(a.total_pts||0)).forEach(t => {
            rows += `
                <tr style="border-bottom:1px solid rgba(255,255,200,0.05); font-size:12px;">
                    <td style="padding:4px; color:var(--gold);">#${t.position||'-'}</td>
                    <td style="font-weight:700;">${t.name}</td>
                    <td align="center">${t.kills||0}</td>
                    <td align="center">${t.placement_points||0}</td>
                    <td align="center" style="color:var(--gold); font-weight:800;">${t.total_pts||0}</td>
                </tr>
            `;
        });

        h += `
            <div style="background:#141c26; border:1px solid #1e293b; border-radius:6px; padding:10px; margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px;">
                    <b style="color:var(--gold); font-size:16px;">${m.match_name} (${m.map})</b>
                    <span style="font-size:11px; color:#8b9bb0;">${m.timestamp}</span>
                </div>
                <table style="width:100%; border-collapse:collapse;">
                    <tr style="color:#7b8ea6; font-size:11px; text-transform:uppercase;">
                        <th align="left">Pos</th><th align="left">Team</th><th>Kills</th><th>Place</th><th>Total</th>
                    </tr>
                    ${rows}
                </table>
            </div>
        `;
    });
    c.innerHTML = h;
}

async function clearMatchHistory() { if(!confirm("Wipe match history?")) return; await fetch("/api/clear_history", { method: "POST" }); loadTeams(); showToast("Wiped!"); }

loadConfigData();
loadTeams();
</script>
</body>
</html>
"""

# =========================================================
# OVERLAYS IMPLEMENTATION
# =========================================================

# 1. STREAM STARTING
STARTING_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.scene-wrap { position: relative; z-index: 10; width: 100vw; height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.logo-box { width: 140px; height: 140px; border-radius: 18px; border: 2px solid var(--gold); padding: 10px; background: rgba(0,0,0,0.5); box-shadow: 0 0 35px rgba(242,196,0,0.4); animation: pGlow 3s infinite alternate; }
@keyframes pGlow { 0% { transform: scale(1); } 100% { transform: scale(1.05); } }
.main-title { font-family: 'Teko', sans-serif; font-size: 105px; font-weight: 800; line-height: 0.9; text-transform: uppercase; letter-spacing: 4px; margin-top: 15px; }
.sub-title { font-size: 18px; font-weight: 800; letter-spacing: 12px; color: var(--cyan); text-transform: uppercase; margin-bottom: 25px; }

.countdown-box { display: flex; gap: 15px; margin-top: 10px; }
.time-unit { background: rgba(8, 14, 22, 0.9); border: 1px solid rgba(242,196,0,0.3); border-bottom: 3px solid var(--gold); border-radius: 8px; width: 105px; height: 95px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.time-val { font-family: 'Orbitron', monospace; font-size: 46px; font-weight: 900; color: var(--gold); line-height: 1; }
.time-lbl { font-size: 11px; font-weight: 800; color: #8fa0b5; letter-spacing: 2px; }

.bottom-info-strip { position: fixed; bottom: 30px; width: 85%; display: flex; justify-content: space-between; padding: 12px 24px; }
</style></head>
<body>
<div class="screen-bg"><canvas class="particles-canvas"></canvas></div>
<div class="scene-wrap">
    <img src="/static/logos/server_logo.webp" class="logo-box" onerror="this.src='https://dummyimage.com/150x150/0b121e/f2c400&text=ENI'">
    <h1 class="main-title">STREAM <span style="color:var(--gold);">STARTING</span></h1>
    <div class="sub-title" id="hlText">MATCH DAY UNDERWAY</div>

    <div class="countdown-box">
        <div class="time-unit"><div class="time-val" id="min">05</div><div class="time-lbl">MINUTES</div></div>
        <div class="time-unit"><div class="time-val" id="sec">00</div><div class="time-lbl">SECONDS</div></div>
    </div>
</div>

<div class="bottom-info-strip cyber-card">
    <div><span style="color:#7f93ab; font-size:12px; font-weight:800;">TOURNAMENT:</span> <b id="tourney" style="color:var(--gold);">ESPORTS NATION</b></div>
    <div><span style="color:#7f93ab; font-size:12px; font-weight:800;">UPCOMING:</span> <b id="match" style="color:#fff;">MATCH 1</b> | <b id="map" style="color:var(--cyan);">ERANGEL</b></div>
</div>

<script>
let totalSec = 300;
let hasCustomTime = false;
setInterval(() => {
    if(totalSec > 0) totalSec--;
    let m = Math.floor(totalSec / 60);
    let s = totalSec % 60;
    document.getElementById("min").innerText = m < 10 ? "0"+m : m;
    document.getElementById("sec").innerText = s < 10 ? "0"+s : s;
}, 1000);

async function loadData() {
    try {
        const r = await fetch("/api/config?t=" + Date.now());
        const d = await r.json();
        document.getElementById("tourney").innerText = d.tournament || "ESPORTS NATION";
        document.getElementById("match").innerText = d.match || "MATCH 1";
        document.getElementById("map").innerText = d.map || "ERANGEL";
        document.getElementById("hlText").innerText = d.broadcast_headline || "MATCH DAY UNDERWAY";
        if(!hasCustomTime && d.start_timer_min) {
            totalSec = parseInt(d.start_timer_min) * 60;
            hasCustomTime = true;
        }
    }catch(e){}
}
loadData(); setInterval(loadData, 3000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# 2. CASTER DESK
CASTER_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.caster-container { 
    position: absolute; 
    inset: 0; 
    display: flex; 
    flex-direction: column; 
    justify-content: space-between; 
    padding: 30px 50px 40px 50px; 
    z-index: 10; 
    pointer-events: none; 
}

.top-desk-banner { 
    align-self: center; 
    padding: 10px 45px; 
    display: flex; 
    align-items: center; 
    gap: 20px; 
}
.top-desk-banner h2 { 
    font-family: 'Teko'; 
    font-size: 38px; 
    color: var(--gold); 
    line-height: 1; 
    letter-spacing: 2px; 
}

.frames-row { 
    display: grid; 
    grid-template-columns: 1fr 1fr; 
    gap: 50px; 
    margin-bottom: 20px; 
}

.cam-window { 
    height: 480px; 
    position: relative; 
    border: 2px solid rgba(255,255,255,0.2); 
    border-radius: 12px; 
}

.caster-tag { 
    position: absolute; 
    bottom: 20px;
    left: 20px; 
    padding: 10px 28px; 
    display: flex; 
    align-items: center; 
    gap: 12px; 
    border-left: 5px solid var(--gold); 
    z-index: 999;
    background: rgba(10, 16, 26, 0.95) !important;
}

.caster-name { 
    font-family: 'Teko'; 
    font-size: 36px; 
    font-weight: 700; 
    color: #ffffff; 
    line-height: 1; 
    letter-spacing: 1.5px;
}

.caster-role { 
    font-size: 12px; 
    font-weight: 800; 
    color: var(--cyan); 
    letter-spacing: 2px; 
    margin-bottom: 2px;
}
</style></head>
<body>
<div class="caster-container">
    <div class="top-desk-banner cyber-card">
        <h2>TALENT DESK</h2>
        <div style="font-size:14px; font-weight:800; color:var(--cyan); letter-spacing:2px;" id="cMatch">MATCH 1</div>
    </div>

    <div class="frames-row">
        <div class="cam-window cyber-card" id="cam1">
            <div class="caster-tag cyber-card">
                <div><div class="caster-role" id="r1">PLAY-BY-PLAY</div><div class="caster-name" id="c1">CASTER 1</div></div>
            </div>
        </div>
        <div class="cam-window cyber-card" id="cam2">
            <div class="caster-tag cyber-card" style="border-left-color:var(--cyan);">
                <div><div class="caster-role" id="r2">ANALYST</div><div class="caster-name" id="c2">CASTER 2</div></div>
            </div>
        </div>
    </div>
</div>

<script>
async function loadCasters() {
    try {
        const r = await fetch("/api/config?t=" + Date.now());
        const d = await r.json();
        document.getElementById("c1").innerText = d.caster1_name || "CASTER 1";
        document.getElementById("r1").innerText = d.caster1_title || "PLAY-BY-PLAY";
        document.getElementById("c2").innerText = d.caster2_name || "CASTER 2";
        document.getElementById("r2").innerText = d.caster2_title || "ANALYST";
        document.getElementById("cMatch").innerText = (d.tournament || "ESPORTS NATION") + " | " + (d.match || "MATCH 1");
        
        if(d.chroma_key_mode) {
            document.getElementById("cam1").classList.add("chroma-box");
            document.getElementById("cam2").classList.add("chroma-box");
        } else {
            document.getElementById("cam1").classList.remove("chroma-box");
            document.getElementById("cam2").classList.remove("chroma-box");
        }
    }catch(e){}
}
loadCasters(); setInterval(loadCasters, 2500);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# 3. DUAL POV (CUSTOM NAMES & AUTOSYNC)
DUALPOV_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.dual-container { 
    position: absolute; 
    inset: 0; 
    display: grid; 
    grid-template-columns: 1fr 1fr; 
    gap: 30px; 
    padding: 45px 30px; 
    z-index: 10; 
    pointer-events: none; 
}
.pov-box { 
    position: relative; 
    border-radius: 12px; 
    border: 2px solid rgba(255,255,255,0.2); 
    height: 85vh; 
    overflow: hidden;
}
.vs-badge { 
    position: fixed; 
    top: 50%; 
    left: 50%; 
    transform: translate(-50%, -50%); 
    z-index: 100; 
    font-family: 'Teko'; 
    font-size: 54px; 
    font-weight: 800; 
    color: var(--gold); 
    padding: 5px 25px; 
    border: 2px solid var(--gold); 
    background: rgba(10, 16, 26, 0.95);
}
.pov-header { 
    position: absolute; 
    top: 20px; 
    left: 20px; 
    right: 20px; 
    display: flex; 
    justify-content: space-between; 
    align-items: center; 
    padding: 10px 22px; 
    z-index: 50;
    background: rgba(10, 16, 26, 0.95) !important;
}
.pov-sub {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
}
.p-team { 
    font-family: 'Teko'; 
    font-size: 38px; 
    line-height: 1; 
    letter-spacing: 1px;
}
.p-stat { 
    font-size: 17px; 
    font-weight: 800; 
    color: var(--gold); 
}
</style></head>
<body>
<div class="vs-badge cyber-card">VS</div>
<div class="dual-container">
    <div class="pov-box cyber-card" id="pov1">
        <div class="pov-header cyber-card" style="border-left: 4px solid var(--cyan);">
            <div>
                <div class="pov-sub" id="t1Sub" style="color:var(--cyan);">POV 1</div>
                <div class="p-team" id="t1Name" style="color:#ffffff;">TEAM A</div>
            </div>
            <div class="p-stat" id="t1Kills">0 FINISHES</div>
        </div>
    </div>
    <div class="pov-box cyber-card" id="pov2">
        <div class="pov-header cyber-card" style="border-left: 4px solid var(--gold);">
            <div>
                <div class="pov-sub" id="t2Sub" style="color:var(--gold);">POV 2</div>
                <div class="p-team" id="t2Name" style="color:#ffffff;">TEAM B</div>
            </div>
            <div class="p-stat" id="t2Kills">0 FINISHES</div>
        </div>
    </div>
</div>
<script>
async function loadDual() {
    try {
        const [cRes, tRes] = await Promise.all([
            fetch("/api/config?t=" + Date.now()), 
            fetch("/api/teams?t=" + Date.now())
        ]);
        const cfg = await cRes.json();
        const d = await tRes.json();
        
        if(cfg.chroma_key_mode) {
            document.getElementById("pov1").classList.add("chroma-box");
            document.getElementById("pov2").classList.add("chroma-box");
        } else {
            document.getElementById("pov1").classList.remove("chroma-box");
            document.getElementById("pov2").classList.remove("chroma-box");
        }

        const alive = d.filter(t => !t.absent && t.players.some(p => p === 1));

        document.getElementById("t1Sub").innerText = cfg.dual_team1_sub || "POV 1";
        document.getElementById("t2Sub").innerText = cfg.dual_team2_sub || "POV 2";

        if(cfg.dual_team1_name && cfg.dual_team1_name.trim() !== "") {
            document.getElementById("t1Name").innerText = cfg.dual_team1_name.toUpperCase();
            const matched1 = d.find(t => t.name.toUpperCase() === cfg.dual_team1_name.trim().toUpperCase());
            document.getElementById("t1Kills").innerText = (matched1 ? matched1.kills : 0) + " FINISHES";
        } else if(alive.length >= 1) {
            document.getElementById("t1Name").innerText = alive[0].name;
            document.getElementById("t1Kills").innerText = alive[0].kills + " FINISHES";
        }

        if(cfg.dual_team2_name && cfg.dual_team2_name.trim() !== "") {
            document.getElementById("t2Name").innerText = cfg.dual_team2_name.toUpperCase();
            const matched2 = d.find(t => t.name.toUpperCase() === cfg.dual_team2_name.trim().toUpperCase());
            document.getElementById("t2Kills").innerText = (matched2 ? matched2.kills : 0) + " FINISHES";
        } else if(alive.length >= 2) {
            document.getElementById("t2Name").innerText = alive[1].name;
            document.getElementById("t2Kills").innerText = alive[1].kills + " FINISHES";
        }
    } catch(e){}
}
loadDual(); setInterval(loadDual, 1500);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# 4. MINI-MAP PiP (CLEAN MAP FEED WITH CHROMA KEY GREEN SCREEN ENABLED)
MAPGAME_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.hud-wrapper { 
    position: absolute; 
    inset: 0; 
    pointer-events: none; 
    z-index: 10; 
}

.map-pip {
    position: fixed; 
    width: 380px; 
    height: 380px;
    border: 2px solid var(--cyan); 
    border-radius: 12px;
    overflow: hidden;
}

.pos-bottom-right { right: 25px; bottom: 25px; }
.pos-bottom-left { left: 25px; bottom: 25px; }
.pos-top-right { right: 25px; top: 25px; }

.map-header { 
    position: absolute; 
    top: 0; 
    left: 0; 
    right: 0; 
    background: rgba(8, 16, 28, 0.95); 
    border-bottom: 1px solid var(--cyan); 
    padding: 6px 12px; 
    display: flex; 
    justify-content: space-between; 
    align-items: center;
    font-size: 12px; 
    font-weight: 800; 
    z-index: 20; 
}
</style></head>
<body>
<div class="hud-wrapper">
    <div class="map-pip cyber-card pos-bottom-right" id="mapBox">
        <div class="map-header">
            <span style="color:var(--cyan); letter-spacing:1px;">TACTICAL MAP</span>
            <span id="mapName" style="color:var(--gold);">ERANGEL</span>
        </div>
    </div>
</div>
<script>
async function loadMapHUD() {
    try {
        const r = await fetch("/api/config?t=" + Date.now());
        const d = await r.json();
        document.getElementById("mapName").innerText = d.map || "ERANGEL";
        const box = document.getElementById("mapBox");
        
        box.className = "map-pip cyber-card";
        if(d.map_position === "bottom-left") box.classList.add("pos-bottom-left");
        else if(d.map_position === "top-right") box.classList.add("pos-top-right");
        else box.classList.add("pos-bottom-right");

        // Chroma Green Screen Mode Active
        if(d.chroma_key_mode !== false) {
            box.classList.add("chroma-box");
        } else {
            box.classList.remove("chroma-box");
        }
    } catch(e){}
}
loadMapHUD(); setInterval(loadMapHUD, 2000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# 5. BE RIGHT BACK
BRB_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.scene-wrap { position: relative; z-index: 10; width: 100vw; height: 100vh; display: grid; grid-template-columns: 1.2fr 1fr; align-items: center; padding: 0 100px; gap: 60px; }
.hero-text h1 { font-family: 'Teko', sans-serif; font-size: 130px; line-height: 0.85; text-transform: uppercase; }
.status-pill { display: inline-flex; align-items: center; gap: 8px; background: rgba(0,229,255,0.15); border: 1px solid var(--cyan); color: var(--cyan); font-weight: 800; font-size: 14px; padding: 6px 16px; border-radius: 20px; letter-spacing: 2px; margin-bottom: 20px; }
.pulse-circle { width: 10px; height: 10px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 10px var(--cyan); animation: pDot 1s infinite alternate; }
@keyframes pDot { from{opacity:0.3;} to{opacity:1;} }

.side-board { padding: 30px; max-height: 75vh; }
.leader-row { display: flex; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.06); font-weight: 800; font-size: 16px; }
</style></head>
<body>
<div class="screen-bg"><canvas class="particles-canvas"></canvas></div>
<div class="scene-wrap">
    <div class="hero-text">
        <div class="status-pill"><div class="pulse-circle"></div> TACTICAL BREAK</div>
        <h1>BE RIGHT<br><span style="color:var(--gold);">BACK</span></h1>
        <p style="color:#8fa0b5; font-size:18px; font-weight:700; letter-spacing:2px; margin-top:15px;" id="brbHeadline">NEXT ROUND COMMENCING SHORTLY</p>
    </div>

    <div class="side-board cyber-card">
        <div style="font-family:'Teko'; font-size:32px; color:var(--gold); border-bottom:2px solid var(--gold); padding-bottom:6px; margin-bottom:12px;">LIVE TOURNAMENT RECAP</div>
        <div id="brbRows"></div>
    </div>
</div>

<script>
async function loadBRB() {
    try {
        const [cRes, tRes] = await Promise.all([fetch("/api/config?t=" + Date.now()), fetch("/api/teams?t=" + Date.now())]);
        const cfg = await cRes.json();
        const d = await tRes.json();
        document.getElementById("brbHeadline").innerText = cfg.broadcast_headline || "NEXT ROUND COMMENCING SHORTLY";
        
        const top5 = [...d].sort((a,b)=>((b.overall_pts||0)+(b.points||0)) - ((a.overall_pts||0)+(a.points||0))).slice(0, 6);
        let h = "";
        top5.forEach((t, i) => {
            h += `<div class="leader-row">
                <span>#${i+1} ${t.name}</span>
                <span style="color:var(--gold);">${(t.overall_pts||0)+(t.points||0)} PTS</span>
            </div>`;
        });
        document.getElementById("brbRows").innerHTML = h;
    }catch(e){}
}
loadBRB(); setInterval(loadBRB, 3000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# 6. STREAM ENDING
ENDING_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>"""
    + BROADCAST_CORE_CSS
    + r"""
.scene-wrap { position: relative; z-index: 10; width: 100vw; height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.end-title { font-family: 'Teko', sans-serif; font-size: 120px; line-height: 0.9; text-transform: uppercase; font-weight: 800; }
.socials-grid { display: flex; gap: 20px; margin-top: 40px; }
.social-card { display: flex; align-items: center; gap: 12px; padding: 14px 28px; font-size: 18px; font-weight: 800; }
</style></head>
<body>
<div class="screen-bg"><canvas class="particles-canvas"></canvas></div>
<div class="scene-wrap">
    <div style="color:var(--cyan); font-weight:800; letter-spacing:10px; font-size:18px;">BROADCAST CONCLUDED</div>
    <h1 class="end-title">THANKS FOR <span style="color:var(--gold);">WATCHING</span></h1>
    <p style="color:#8fa0b5; font-size:20px; font-weight:700;">SEE YOU IN THE NEXT BATTLEGROUNDS BATTLE</p>

    <div class="socials-grid">
        <div class="social-card cyber-card" id="sDisc">🎮 DISCORD: /esportsindia</div>
        <div class="social-card cyber-card" id="sInsta" style="border-color:var(--cyan);">📷 INSTA: @esportsnation.india</div>
        <div class="social-card cyber-card" id="sYt" style="border-color:var(--gold);">▶️ YT: @esportnationindia</div>
    </div>
</div>
<script>
async function loadEnd() {
    try {
        const r = await fetch("/api/config?t=" + Date.now());
        const d = await r.json();
        document.getElementById("sDisc").innerText = "🎮 DISCORD: " + (d.discord_tag || "esportsindia");
        document.getElementById("sInsta").innerText = "📷 INSTA: " + (d.insta_tag || "@esportsnation.india");
        document.getElementById("sYt").innerText = "▶️ YT: " + (d.yt_tag || "@esportnationindia");
    }catch(e){}
}
loadEnd();
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# MATCH HUD OVERLAYS
PT_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#pt{position:fixed;top:40px;right:15px;width:295px;color:white;box-shadow:0 12px 35px rgba(0,0,0,0.8);border-radius:6px;overflow:hidden;background:#061326;animation:fadeInPT 0.8s ease;}@keyframes fadeInPT{from{opacity:0;transform:translateY(-15px);}to{opacity:1;transform:translateY(0);}}.top-status-bar{display:flex;justify-content:space-between;align-items:center;background:#061326;border-top:3px solid #f2c400;padding:5px 10px;font-size:11px;font-weight:800;}.header{height:26px;display:grid;grid-template-columns:36px 1fr 48px 34px 36px;align-items:center;background:#f2c400;color:#050b14;font-weight:800;font-size:11px;padding:0 6px;}.row{height:28px;display:grid;grid-template-columns:36px 1fr 48px 34px 36px;align-items:center;background:rgb(6,20,39);border-bottom:1px solid rgba(255,255,255,0.08);padding:0 6px;transition:all 0.3s ease;}.row.eliminated-row{background:rgba(45, 10, 16, 0.95) !important;border-left:3px solid #ff2a55;}.row.absent-row{opacity:0.35;filter:grayscale(1);background:#080d14 !important;}.rank-cell{text-align:center;color:#f2c400;font-weight:800;font-size:11px;}.team-name-area{padding-left:4px;font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px;}.team-logo{width:17px;height:17px;object-fit:contain;border-radius:2px;flex-shrink:0;}.players{display:flex;justify-content:center;gap:3px;align-items:center;}.player{width:5px;height:14px;background:#00ff66;}.player.dead{background:#ff2a55;}.kills{text-align:center;color:#00e5ff;font-weight:700;}.pts{text-align:center;color:#f2c400;font-weight:800;background:rgba(242,196,0,0.1);height:100%;display:flex;align-items:center;justify-content:center;}</style></head><body><div id="pt"><div class="top-status-bar"><span>TEAMS <strong id="t">0</strong></span><span>ALIVE <strong id="p">0</strong></span></div><div class="header"><div>#</div><div>TEAM</div><div>ALIVE</div><div>FIN</div><div>PTS</div></div><div id="r"></div></div>
<script>
let prevRanks={};
async function l(){
    try{
        const res=await fetch("/api/teams?t=" + Date.now()); const data=await res.json();
        let at=0, ap=0;
        data.forEach(t=>{if(!t.absent){let a=t.players.filter(p=>p===1).length;if(a>0)at++;ap+=a;}});
        document.getElementById("t").innerText=at; document.getElementById("p").innerText=ap;
        
        const sorted=[...data].sort((a,b)=>{
            if(a.absent!==b.absent) return a.absent ? 1 : -1;
            const aA=a.players.filter(p=>p===1).length>0, bA=b.players.filter(p=>p===1).length>0;
            if(aA!==bA) return aA?-1:1;
            return (b.points||0)-(a.points||0);
        });

        let h="";
        sorted.forEach((t,i)=>{
            const rank=i+1; 
            const prev=prevRanks[t.id]||rank; 
            const diff=prev-rank;
            let ind=diff>0?`<span style="color:#00ff66;font-size:9px;">▲</span>`:(diff<0?`<span style="color:#ff2a55;font-size:9px;">▼</span>`:"");
            prevRanks[t.id]=rank;

            const isDead = (t.players.filter(p=>p===1).length === 0);
            let s=""; 
            if(t.absent){
                s = `<span style="font-size:9px; color:#ff4d4d; font-weight:800;">ABSENT</span>`;
            } else if(isDead && t.position > 0) {
                s = `<span style="font-size:9px; color:#ff2a55; font-weight:800;">ELIM</span>`;
            } else {
                t.players.forEach(a=>s+=`<div class="player ${a?'':'dead'}"></div>`);
            }
            let logo=t.logo?`<img class="team-logo" src="${t.logo}">`:"";
            
            let rowClass = "";
            if(t.absent) rowClass = "absent-row";
            else if(isDead && t.position > 0) rowClass = "eliminated-row";

            h+=`<div class="row ${rowClass}">
                <div class="rank-cell">${t.absent ? '-' : '#' + rank + ind}</div>
                <div class="team-name-area">${logo}${t.name}</div>
                <div class="players">${s}</div>
                <div class="kills">${t.absent ? '-' : t.kills}</div>
                <div class="pts">${t.absent ? '-' : t.points}</div>
            </div>`;
        });
        document.getElementById("r").innerHTML=h;
    }catch(e){}
}
l();setInterval(l,1000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

STANDINGS_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:radial-gradient(circle at center, rgb(10,28,54) 0%, rgb(3,8,17) 100%);font-family:'Rajdhani',sans-serif;color:white;}.board-wrapper{max-width:1340px;margin:30px auto;padding:0 20px;animation:fadeInBoard 0.8s ease;}@keyframes fadeInBoard{from{opacity:0;}to{opacity:1;}}.board-header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #f2c400;padding-bottom:10px;margin-bottom:20px;}.bh-title{font-family:'Teko',sans-serif;font-size:46px;color:#f2c400;letter-spacing:2px;text-transform:uppercase;line-height:1;}.bh-sub{font-size:15px;font-weight:800;color:#00e5ff;letter-spacing:3px;}.standings-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 25px;}.st-table{width:100%;border-collapse:separate;border-spacing:0 6px;}.st-head{background:#f2c400;color:#040811;font-weight:800;font-size:12px;}.st-head th{padding:7px 8px;text-align:center;}.st-head th:nth-child(2){text-align:left;}.st-row{background:rgb(9,28,54);}.st-row.top1{background:rgb(36,31,10);outline:1px solid #f2c400;}.st-row td{padding:7px 8px;text-align:center;font-weight:800;font-size:15px;}.st-row td:first-child{color:#f2c400;width:75px;}.st-team{display:flex;align-items:center;gap:8px;text-align:left;}.st-logo{width:24px;height:24px;object-fit:contain;border-radius:4px;}.st-pts{color:#f2c400;font-size:17px;background:rgba(242,196,0,0.12);}.jump-up{color:#00ff66;font-size:11px;font-weight:800;margin-left:3px;}.jump-down{color:#ff2a55;font-size:11px;font-weight:800;margin-left:3px;}.jump-none{color:#64748b;font-size:11px;margin-left:3px;}</style></head><body><div class="board-wrapper"><div class="board-header"><div><div class="bh-sub" id="stTourney">ESPORTS NATION INDIA</div><div class="bh-title">OVERALL STANDINGS</div></div><div class="bh-title" style="font-size:32px;">LEADERBOARD</div></div><div class="standings-grid"><table class="st-table"><thead><tr class="st-head"><th>#</th><th>TEAM</th><th>M</th><th>WWCD</th><th>KILLS</th><th>PLACE</th><th>TOTAL</th></tr></thead><tbody id="colLeft"></tbody></table><table class="st-table"><thead><tr class="st-head"><th>#</th><th>TEAM</th><th>M</th><th>WWCD</th><th>KILLS</th><th>PLACE</th><th>TOTAL</th></tr></thead><tbody id="colRight"></tbody></table></div></div>
<script>
async function loadSt(){
    try{
        const [cRes, tRes, hRes]=await Promise.all([fetch("/api/config?t=" + Date.now()),fetch("/api/teams?t=" + Date.now()),fetch("/api/history?t=" + Date.now())]);
        const cfg=await cRes.json(); const data=await tRes.json(); const history=await hRes.json();
        document.getElementById("stTourney").innerText=cfg.tournament||"ESPORTS NATION INDIA";
        
        const currentSorted=[...data].sort((a,b)=>{
            if(a.absent!==b.absent) return a.absent?1:-1;
            return ((b.overall_pts||0)+(b.points||0)) - ((a.overall_pts||0)+(a.points||0));
        });

        let prevRankMap = {};
        if(history && history.length > 0){
            let prevTotals = {};
            history.forEach(m => {
                (m.teams || []).forEach(tm => {
                    if(!prevTotals[tm.id]) prevTotals[tm.id] = 0;
                    prevTotals[tm.id] += (tm.total_pts || 0);
                });
            });
            let prevList = Object.keys(prevTotals).map(id => ({ id: parseInt(id), pts: prevTotals[id] }));
            prevList.sort((a,b) => b.pts - a.pts);
            prevList.forEach((tm, idx) => { prevRankMap[tm.id] = (idx + 1); });
        }

        const mid=Math.ceil(currentSorted.length/2);
        const render=(list, offset)=>list.map((t,idx)=>{
            const curRank = offset + idx + 1;
            let arrowHtml = `<span class="jump-none">-</span>`;
            if(prevRankMap[t.id] !== undefined){
                const pRank = prevRankMap[t.id];
                const jump = pRank - curRank;
                if(jump > 0) arrowHtml = `<span class="jump-up">▲+${jump}</span>`;
                else if(jump < 0) arrowHtml = `<span class="jump-down">▼${jump}</span>`;
            }

            return `
            <tr class="st-row ${!t.absent&&curRank===1?'top1':''}">
                <td>#${curRank}${arrowHtml}</td>
                <td><div class="st-team">${t.logo?`<img class="st-logo" src="${t.logo}">`:''}<span>${t.name}</span></div></td>
                <td>${t.matches_played||0}</td><td style="color:#f2c400;">${t.wwcd||0}</td>
                <td style="color:#00ff66;">${(t.overall_kills||0)+(t.kills||0)}</td>
                <td style="color:#00bfff;">${(t.overall_place_pts||0)+(t.placement_points||0)}</td>
                <td class="st-pts">${(t.overall_pts||0)+(t.points||0)}</td>
            </tr>`;
        }).join("");
        
        document.getElementById("colLeft").innerHTML=render(currentSorted.slice(0,mid),0);
        document.getElementById("colRight").innerHTML=render(currentSorted.slice(mid),mid);
    }catch(e){}
}
loadSt(); setInterval(loadSt,2000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

ELIM_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#elimination{position:fixed;left:50%;top:16%;width:420px;transform:translate(-50%,-50%) scale(0.85);opacity:0;pointer-events:none;background:linear-gradient(135deg, rgb(6,20,39), rgb(14,34,60));border:1px solid rgba(255,46,77,0.55);border-top:4px solid #ff2e4d;border-radius:12px;padding:16px 22px;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,0.8);z-index:999;}#elimination.show{animation:elimShow 3.8s cubic-bezier(0.16,1,0.3,1) forwards;}@keyframes elimShow{0%{opacity:0;transform:translate(-50%,-70%) scale(0.7);}15%{opacity:1;transform:translate(-50%,-50%) scale(1);}85%{opacity:1;transform:translate(-50%,-50%) scale(1);}100%{opacity:0;transform:translate(-50%,-35%) scale(0.85);}}.elim-banner{display:inline-block;background:rgba(255,46,77,0.2);color:#ff4d6d;font-size:11px;font-weight:800;letter-spacing:3px;padding:3px 12px;border-radius:4px;margin-bottom:8px;}.elim-team-row{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:14px;}.elim-logo{width:48px;height:48px;object-fit:contain;border-radius:8px;background:rgba(255,255,255,0.07);padding:4px;}.elim-team{color:#ffffff;font-family:'Teko',sans-serif;font-size:36px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;}.elim-info{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;}.info-box{padding:7px 6px;border:1px solid rgba(255,255,255,0.14);border-radius:8px;background:rgba(0,0,0,0.35);}.info-label{color:#9da9b8;font-size:10px;font-weight:800;}.info-value{color:white;font-size:21px;font-weight:800;}.info-value.gold{color:#f2c400;}.info-value.cyan{color:#00e5ff;}</style></head><body><div id="elimination"><div class="elim-banner">SQUAD ELIMINATED</div><div class="elim-team-row"><img id="elimLogo" class="elim-logo" src="" style="display:none;" onerror="this.style.display='none'"><div class="elim-team" id="elimTeam">TEAM NAME</div></div><div class="elim-info"><div class="info-box"><div class="info-label">RANK</div><div class="info-value gold" id="elimRank">#0</div></div><div class="info-box"><div class="info-label">FINISHES</div><div class="info-value cyan" id="elimKills">0</div></div><div class="info-box"><div class="info-label">TOTAL PTS</div><div class="info-value" id="elimPts">0</div></div></div></div>
<script>
let lastState={}, lastTs={}, queue=[], playing=false;
async function check(){
    try{
        const res=await fetch("/api/teams?t=" + Date.now()); const data=await res.json();
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
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

MATCH_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#match-info{position:fixed;bottom:18px;left:18px;min-width:240px;background:linear-gradient(135deg, rgb(6,20,39), rgb(12,34,62));border:1px solid rgba(242,196,0,0.4);border-left:4px solid #f2c400;border-radius:8px;padding:8px 14px;color:white;box-shadow:0 8px 25px rgba(0,0,0,0.65);animation:slideMatch 0.8s ease;}.mi-tourney{font-size:10px;font-weight:800;color:#00e5ff;letter-spacing:1.5px;}.mi-row{display:flex;align-items:baseline;gap:10px;margin-top:2px;}.mi-match{font-family:'Teko',sans-serif;font-size:24px;font-weight:700;color:#f2c400;}.mi-map{font-family:'Teko',sans-serif;font-size:24px;font-weight:700;color:white;}</style></head><body><div id="match-info"><div class="mi-tourney" id="dt">ESPORTS NATION INDIA</div><div class="mi-row"><div class="mi-match" id="dm">MATCH 1</div><div>|</div><div class="mi-map" id="dmap">ERANGEL</div></div></div>
<script>
async function c(){try{const res=await fetch("/api/config?t=" + Date.now());const cfg=await res.json();document.getElementById("dt").innerText=cfg.tournament||"ESPORTS NATION INDIA";document.getElementById("dm").innerText=cfg.match||"MATCH 1";document.getElementById("dmap").innerText=cfg.map||"ERANGEL";}catch(e){}}
c();setInterval(c,2000);
</script>
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

WWCD_HTML = (
    r"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@700;800&family=Teko:wght@600;700&display=swap');*{box-sizing:border-box;}html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:'Rajdhani',sans-serif;}#wwcd-screen{position:fixed;top:0;left:0;width:100vw;height:100vh;background:radial-gradient(circle at center, rgba(16,28,48,0.96) 0%, rgba(3,6,15,0.99) 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;pointer-events:none;z-index:9999;}#wwcd-screen.show{animation:wwcdAnim 10s cubic-bezier(0.16,1,0.3,1) forwards;}@keyframes wwcdAnim{0%{opacity:0;transform:scale(1.15);}10%{opacity:1;transform:scale(1);}90%{opacity:1;transform:scale(1);}100%{opacity:0;transform:scale(0.95);}}.wwcd-badge{border-top:2px solid #f2c400;border-bottom:2px solid #f2c400;color:#f2c400;font-size:24px;font-weight:800;letter-spacing:8px;padding:8px 50px;margin-bottom:20px;text-transform:uppercase;}.wwcd-title{font-family:'Teko',sans-serif;font-size:96px;color:#fff;line-height:0.9;margin:0 0 25px 0;text-transform:uppercase;}.wwcd-title span{color:#f2c400;}.winner-card{background:linear-gradient(135deg,rgb(10,26,48),rgb(5,13,26));border:2px solid #f2c400;border-radius:20px;padding:35px 70px;display:flex;flex-direction:column;align-items:center;min-width:550px;box-shadow:0 25px 70px rgba(0,0,0,0.9);}.winner-logo{width:130px;height:130px;object-fit:contain;border-radius:16px;background:rgba(255,255,255,0.06);padding:12px;border:2px solid rgba(242,196,0,0.6);margin-bottom:18px;}.winner-name{font-family:'Teko',sans-serif;font-size:80px;color:#f2c400;line-height:1;text-transform:uppercase;margin-bottom:25px;text-align:center;}.winner-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:25px;width:100%;}.w-stat-box{background:rgba(0,0,0,0.55);border:1px solid rgba(255,255,255,0.12);border-bottom:3px solid #f2c400;border-radius:12px;padding:14px 24px;text-align:center;}.w-stat-label{font-size:13px;color:#9da9b8;font-weight:800;letter-spacing:2px;}.w-stat-val{font-size:38px;font-weight:800;color:#f2c400;line-height:1;}</style></head><body><div id="wwcd-screen"><div class="wwcd-badge">🍗 WINNER WINNER CHICKEN DINNER 🍗</div><h1 class="wwcd-title">MATCH <span>CHAMPIONS</span></h1><div class="winner-card"><img id="wwcdLogo" class="winner-logo" src="" style="display:none;" onerror="this.style.display='none'"><div id="wwcdName" class="winner-name">TEAM NAME</div><div class="winner-stats"><div class="w-stat-box"><div class="w-stat-label">RANK</div><div class="w-stat-val">#1</div></div><div class="w-stat-box"><div class="w-stat-label">FINISHES</div><div id="wwcdKills" class="w-stat-val" style="color:#00e5ff;">0</div></div><div class="w-stat-box"><div class="w-stat-label">PTS</div><div id="wwcdPts" class="w-stat-val">0</div></div></div></div></div>
<script>
let prevAlive=null, shown=false;
async function cW(){
    try{
        const res=await fetch("/api/teams?t=" + Date.now()); const data=await res.json();
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
"""
    + THEME_ENGINE_JS
    + "</body></html>"
)

# =========================================================
# FLASK ROUTE REGISTRATIONS
# =========================================================


@app.route("/")
def admin():
    return render_template_string(ADMIN_HTML)


@app.route("/overlay/pt")
def overlay_pt():
    return render_template_string(PT_HTML)


@app.route("/overlay/elimination")
def overlay_elimination():
    return render_template_string(ELIM_HTML)


@app.route("/overlay/match")
def overlay_match():
    return render_template_string(MATCH_HTML)


@app.route("/overlay/standings")
def overlay_standings():
    return render_template_string(STANDINGS_HTML)


@app.route("/overlay/wwcd")
def overlay_wwcd():
    return render_template_string(WWCD_HTML)


@app.route("/overlay/starting")
def overlay_starting():
    return render_template_string(STARTING_HTML)


@app.route("/overlay/caster")
def overlay_caster():
    return render_template_string(CASTER_HTML)


@app.route("/overlay/dualpov")
def overlay_dualpov():
    return render_template_string(DUALPOV_HTML)


@app.route("/overlay/mapgame")
def overlay_mapgame():
    return render_template_string(MAPGAME_HTML)


@app.route("/overlay/brb")
def overlay_brb():
    return render_template_string(BRB_HTML)


@app.route("/overlay/ending")
def overlay_ending():
    return render_template_string(ENDING_HTML)


@app.route("/api/ping")
def ping():
    cid = request.args.get("cid", request.remote_addr)
    now = time.time()
    connected_users[cid] = now
    active = sum(1 for ts in connected_users.values() if now - ts < 6)
    return jsonify({"status": "ok", "users": max(1, active)})


@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        cfg = load_config()
        for k, v in data.items():
            cfg[k] = v
        save_config(cfg)
        return jsonify({"success": True})
    return jsonify(load_config())


@app.route("/api/themes", methods=["GET", "POST"])
def api_themes():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        themes_data = load_themes()
        if "admin_theme" in data:
            themes_data["admin_theme"] = data["admin_theme"]
        if "match_key" in data:
            match_key = data.get("match_key", "MATCH 1").strip().upper()
            themes_data["matches"][match_key] = data.get("theme", {})
        save_themes(themes_data)
        return jsonify({"success": True})
    return jsonify({"themes": load_themes(), "presets": BUILTIN_PRESETS})


@app.route("/api/active_theme")
def api_active_theme():
    cfg = load_config()
    current_match = (cfg.get("match") or "MATCH 1").strip().upper()
    themes_data = load_themes()
    active = themes_data.get("matches", {}).get(
        current_match, BUILTIN_PRESETS["Classic Gold"]
    )
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
    if not os.path.exists(HISTORY_FILE):
        return jsonify([])
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            c = f.read().strip()
            return jsonify(json.loads(c)) if c else jsonify([])
    except Exception:
        return jsonify([])


@app.route("/api/clear_history", methods=["POST"])
def clear_history():
    if os.path.exists(HISTORY_FILE):
        try:
            os.remove(HISTORY_FILE)
        except Exception:
            pass
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
        t["wwcd"] = 0
    save(teams)
    return jsonify({"success": True})


@app.route("/api/reset_all", methods=["POST"])
def reset_all():
    save_state_for_undo()
    if os.path.exists(HISTORY_FILE):
        try:
            os.remove(HISTORY_FILE)
        except Exception:
            pass
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


@app.route("/api/create", methods=["POST"])
def create():
    data = request.get_json(silent=True) or request.form or {}
    count = int(data.get("count", 0))
    save_state_for_undo()
    if count <= 0:
        save([])
        return jsonify({"success": True})
    teams = []
    for i in range(3, count + 3):
        teams.append({
            "id": i,
            "name": f"TEAM {i}",
            "logo": "",
            "kills": 0,
            "position": 0,
            "points": 0,
            "placement_points": 0,
            "overall_kills": 0,
            "overall_place_pts": 0,
            "overall_pts": 0,
            "matches_played": 0,
            "wwcd": 0,
            "absent": False,
            "players": [1, 1, 1, 1],
            "elim_ts": 0,
        })
    save(teams)
    return jsonify({"success": True})


@app.route("/api/import_slots", methods=["POST"])
def import_slots():
    data = request.get_json(silent=True) or request.form or {}
    names = data.get("names", [])
    if not names:
        return jsonify({"success": False})
    save_state_for_undo()
    existing_teams = load()
    logo_map = {t["name"].upper(): t.get("logo", "") for t in existing_teams}
    teams = []
    for i, name in enumerate(names, start=3):
        teams.append({
            "id": i,
            "name": name,
            "logo": logo_map.get(name.upper(), ""),
            "kills": 0,
            "position": 0,
            "points": 0,
            "placement_points": 0,
            "overall_kills": 0,
            "overall_place_pts": 0,
            "overall_pts": 0,
            "matches_played": 0,
            "wwcd": 0,
            "absent": False,
            "players": [1, 1, 1, 1],
            "elim_ts": 0,
        })
    save(teams)
    return jsonify({"success": True})


@app.route("/api/adjust_slots", methods=["POST"])
def adjust_slots():
    data = request.get_json(silent=True) or request.form or {}
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
                "id": max_id,
                "name": f"TEAM {max_id}",
                "logo": "",
                "kills": 0,
                "position": 0,
                "points": 0,
                "placement_points": 0,
                "overall_kills": 0,
                "overall_place_pts": 0,
                "overall_pts": 0,
                "matches_played": 0,
                "wwcd": 0,
                "absent": False,
                "players": [1, 1, 1, 1],
                "elim_ts": 0,
            })
    elif new_count < current_count:
        teams = teams[:new_count]
    save(teams)
    return jsonify({"success": True})


@app.route("/api/toggle_absent", methods=["POST"])
def toggle_absent():
    data = request.get_json(silent=True) or request.form or {}
    save_state_for_undo()
    target_id = str(data.get("id", "")).strip()
    teams = load()
    new_state = False
    found = False
    for team in teams:
        if str(team.get("id", "")).strip() == target_id:
            team["absent"] = not team.get("absent", False)
            new_state = team["absent"]
            found = True
            break
    if found:
        save(teams)
    return jsonify({"success": found, "id": target_id, "absent": new_state})


@app.route("/api/reset_match", methods=["POST"])
def reset_match():
    save_state_for_undo()
    teams = load()
    for team in teams:
        team["kills"] = 0
        team["position"] = 0
        team["points"] = 0
        team["placement_points"] = 0
        team["players"] = [1] * len(team.get("players", [1, 1, 1, 1]))
        team["elim_ts"] = 0
        team["match_saved_flag"] = False
    save(teams)
    return jsonify({"success": True})


@app.route("/api/update", methods=["POST"])
def update():
    data = request.get_json(silent=True) or request.form or {}
    save_state_for_undo()
    teams = load()
    team_id = str(data.get("id", "")).strip()
    total_active = len([t for t in teams if not t.get("absent")])

    for team in teams:
        if str(team.get("id", "")).strip() != team_id:
            continue
        if "name" in data:
            team["name"] = data["name"]
        if "player_count" in data:
            new_count = int(data["player_count"])
            current = team.get("players", [1, 1, 1, 1])
            if new_count > len(current):
                current.extend([1] * (new_count - len(current)))
            elif new_count < len(current):
                current = current[:new_count]
            team["players"] = current
            if sum(team["players"]) == 0 and team.get("position", 0) == 0:
                assigned = [
                    t.get("position", 0) for t in teams if t.get("position", 0) > 0
                ]
                for p in range(total_active, 1, -1):
                    if p not in assigned:
                        team["position"] = p
                        break
                team["elim_ts"] = time.time()
            elif sum(team["players"]) > 0 and team.get("position", 0) > 0:
                team["position"] = 0
                team["elim_ts"] = 0

        if "player" in data:
            player = int(data["player"])
            if 0 <= player < len(team["players"]):
                was_dead = sum(team["players"]) == 0
                team["players"][player] = 0 if team["players"][player] else 1
                now_alive = sum(team["players"])
                if now_alive == 0 and team.get("position", 0) == 0:
                    assigned = [
                        t.get("position", 0) for t in teams if t.get("position", 0) > 0
                    ]
                    for p in range(total_active, 1, -1):
                        if p not in assigned:
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
    data = request.get_json(silent=True) or request.form or {}
    save_state_for_undo()
    teams = load()
    team_id = str(data.get("id", "")).strip()
    total_active = len([t for t in teams if not t.get("absent")])

    for team in teams:
        if str(team.get("id", "")).strip() == team_id:
            team["players"] = [0] * len(team.get("players", [1, 1, 1, 1]))
            if team.get("position", 0) == 0:
                assigned = [
                    t.get("position", 0) for t in teams if t.get("position", 0) > 0
                ]
                for p in range(total_active, 1, -1):
                    if p not in assigned:
                        team["position"] = p
                        break
                team["elim_ts"] = time.time()
            break

    save(teams)
    return jsonify({"success": True})


@app.route("/api/save_match_overall", methods=["POST"])
def save_match_overall():
    save_state_for_undo()
    teams = load()
    if teams and all(
        t.get("match_saved_flag", False) for t in teams if not t.get("absent")
    ):
        return (
            jsonify({
                "error": "Match already saved! Click NEW MATCH before saving again."
            }),
            400,
        )

    auto_assign_winner_if_one_left(teams)
    recalculate_all(teams)

    current_match_data = []
    for t in teams:
        if not t.get("absent", False):
            t["matches_played"] = t.get("matches_played", 0) + 1
            t["overall_kills"] = t.get("overall_kills", 0) + t.get("kills", 0)
            t["overall_place_pts"] = t.get("overall_place_pts", 0) + t.get(
                "placement_points", 0
            )
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
            "absent": t.get("absent", False),
        })

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as hf:
                c = hf.read().strip()
                if c:
                    history = json.loads(c)
        except Exception:
            history = []

    match_number = len(history) + 1
    cfg = load_config()

    history.append({
        "match_num": match_number,
        "match_name": cfg.get("match", f"MATCH {match_number}"),
        "map": cfg.get("map", "ERANGEL"),
        "timestamp": time.strftime("%d %b %Y, %I:%M %p"),
        "teams": copy.deepcopy(current_match_data),
    })

    safe_write_json(HISTORY_FILE, history)
    cfg["match"] = f"MATCH {match_number + 1}"
    save_config(cfg)
    save(teams)
    return jsonify({"success": True, "next_match": f"MATCH {match_number + 1}"})


@app.route("/api/upload_logo", methods=["POST"])
def upload_logo():
    team_id = request.form.get("id")
    file = request.files.get("logo")
    
    if not file or not team_id:
        return jsonify({"success": False, "error": "Missing file or ID"})
        
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['png', 'jpg', 'jpeg', 'webp', 'gif']:
        return jsonify({"success": False, "error": "Invalid format. Use PNG, JPG, WEBP, or GIF"})
        
    filename = f"team_{team_id}.{ext}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    
    save_state_for_undo()
    teams = load()
    for t in teams:
        if str(t.get("id", "")) == str(team_id):
            t["logo"] = f"/static/logos/{filename}?v={int(time.time())}"
            break
            
    save(teams)
    return jsonify({"success": True})


if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 65)
    print("🚀 ESPORTS NATION BROADCAST MASTER ENGINE READY")
    print(f"👉 PC Browser Link    : http://127.0.0.1:5000/")
    print(f"👉 Mobile Control Link: http://{local_ip}:5000/")
    print("=" * 65)
    app.run(host="0.0.0.0", port=5000, threaded=True)
