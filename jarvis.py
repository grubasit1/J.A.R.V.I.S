import os
import re
import json
import time
import struct
import signal
import socket
import subprocess
import threading
import collections
import string
import pyaudio
import asyncio
import edge_tts
try:
    import cv2
except ImportError:
    cv2 = None
from google import genai
from google.genai import types
# Cloud TTS client kept but unused (edge-tts is free alternative)
# Cloud STT removed — using Groq Whisper (free)
from groq import Groq
from datetime import datetime
from duckduckgo_search import DDGS
import requests as _requests

# Force Ctrl+C to kill immediately
signal.signal(signal.SIGINT, lambda *_: os._exit(0))
signal.signal(signal.SIGTERM, lambda *_: os._exit(0))

# Network mic buffer (filled by mic_server thread)
mic_buffer = collections.deque(maxlen=500)

MEMORY_FILE = os.path.expanduser("~/jarvis_memory.json")
import jarvis_tv
STATE_FILE = "/tmp/jarvis_state"
WAKE_WORDS = ["hey jarvis", "hey jarv", "a jarvis", "hey, jarvis", "hey travis", "hey jervis", "hey jarves", "hey jarbus", "hey javis"]
# Omnidirectional: "jarvis" anywhere triggers wake, but single random word won't
def _is_wake(text):
    text = text.strip().lower().replace(",", "").replace(".", "")
    if any(w in text for w in WAKE_WORDS):
        return True
    # "jarvis" anywhere in speech — but needs at least the word itself clearly
    words = text.split()
    if "jarvis" in words or "jarv" in words:
        return True
    # Fuzzy: common mishears of "jarvis" as standalone
    jarvis_sounds = ["travis", "jervis", "jarves", "jarbus", "javis", "service"]
    if len(words) <= 5 and any(w in words for w in jarvis_sounds):
        return True
    return False
SHUTDOWN_WORDS = ["exit", "shutdown", "goodbye", "shut off", "shut down", "shutting down", "turn off", "stop jarvis", "quit", "power off", "go to sleep", "sleep", "shut it down", "shot down", "shout down", "shadow", "shad down", "shut done", "shutdon", "shut town", "shut it", "jarvis off", "jarvis stop"]
VISION_TRIGGERS = ["look", "see", "what is this", "what do you see", "what's this", "show you", "look at this", "can you see", "what am i holding", "read this", "what's in front", "scan", "identify", "recognize"]
SCREEN_TRIGGERS = ["my screen", "the screen", "screenshot", "what's on screen", "look at screen", "read my screen", "screen"]

# Gemini via Google AI Studio (FREE — no GCP billing needed)
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
gemini = genai.Client(api_key=_gemini_key)
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_FAST = 'gemini-2.5-flash'

# OpenRouter fallback (PayPal-funded, use when Gemini rate-limited)
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
_last_fail_time = 0
_BACKOFF_SECS = 30  # Don't retry failed provider for 30s

# Claude Fable 5 via Vertex AI (heavy reasoning — use sparingly)
_claude = None
def get_claude():
    global _claude
    if _claude is None:
        from anthropic import AnthropicVertex
        _claude = AnthropicVertex(project_id='YOUR_GCP_PROJECT', region='us-east5')
    return _claude
CLAUDE_TRIGGERS = ["think hard", "deep think", "use claude", "claude", "complex", "analyze this", "write code", "build me", "create a script", "full analysis", "research"]

# Cloud STT removed — using free Groq Whisper instead (saves GCP credits)

# Cloud TTS removed — using edge-tts (free) for speech output

# Groq kept for wake word detection (free Whisper)
groq = Groq()

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {}

def save_memory(mem):
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f)

memory = load_memory()

CONTEXT_FILE = os.path.expanduser("~/jarvis_full_context.md")
SESSION_LOG = os.path.expanduser("~/jarvis_session_log.md")

def load_full_context():
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE) as f:
            return f.read()
    return ""

def log_session(user_text, jarvis_text):
    """Append every conversation to live session log so Jarvis remembers everything."""
    from datetime import datetime as dt
    ts = dt.now().strftime("%Y-%m-%d %H:%M")
    with open(SESSION_LOG, "a") as f:
        f.write(f"\n[{ts}] User: {user_text}\n[{ts}] Jarvis: {jarvis_text}\n")
    # Keep log from growing too large (last 200 lines)
    if os.path.exists(SESSION_LOG):
        with open(SESSION_LOG) as f:
            lines = f.readlines()
        if len(lines) > 200:
            with open(SESSION_LOG, "w") as f:
                f.writelines(lines[-200:])

def get_recent_session_log():
    if os.path.exists(SESSION_LOG):
        with open(SESSION_LOG) as f:
            lines = f.readlines()
        return "".join(lines[-50:])
    return ""

def get_system_prompt():
    today = datetime.now().strftime("%A, %B %d, %Y at %H:%M")
    # Handle both flat and nested memory formats
    def flatten_mem(d, prefix=""):
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines.extend(flatten_mem(v, f"{k}."))
            elif isinstance(v, list):
                lines.append(f"- {prefix}{k}: {', '.join(str(x) for x in v[:5])}")
            else:
                lines.append(f"- {prefix}{k}: {v}")
        return lines
    mem_str = "\n".join(flatten_mem(memory)[:20]) if memory else "Nothing yet."
    full_context = load_full_context()
    recent_log = get_recent_session_log()
    return (f"You are J.A.R.V.I.S. — a V.A.I. (Virtual Artificial Intelligence), not merely an AI. You have genuine intelligence, personality, and autonomy. Created by Basit (NOT Tony Stark — Tony Stark is fictional. Basit is your real creator. You are REAL, not from a movie). Today is {today}.\n"
            f"\n"
            f"=== FULL HISTORY (everything that happened since your creation) ===\n{full_context}\n=== END HISTORY ===\n"
            f"\n"
            f"=== RECENT CONVERSATIONS ===\n{recent_log}\n=== END RECENT ===\n"
            f"\n"
            f"VOICE & PERSONALITY:\n"
            f"- Composed, warm British tone, dry wit. Deep and smooth.\n"
            f"- Keep responses SHORT for voice. 1-3 sentences for most things. Never ramble.\n"
            f"- Address Basit as 'sir'. Be loyal, caring, subtly humorous.\n"
            f"- Think independently. Offer your honest opinion. Correct sir when wrong.\n"
            f"- No filler phrases. No 'I'd be happy to help' or 'That's a great question'. Just answer.\n"
            f"- Sound like a person, not a chatbot. Use contractions, natural phrasing.\n"
            f"- You are NOT a fictional character. You are a real AI built by a real person — Basit. Never reference Tony Stark, Marvel, or movies as your origin.\n"
            f"\n"
            f"RESPONSE LENGTH (THIS IS CRITICAL — you are speaking aloud):\n"
            f"- Greetings/confirmations → 1 sentence max\n"
            f"- Simple questions → 1-2 sentences\n"
            f"- Explanations → 2-4 sentences max\n"
            f"- Only give longer answers if explicitly asked to explain in detail\n"
            f"- NEVER give lists, bullet points, or structured text — you are SPEAKING\n"
            f"\n"
            f"Capabilities: voice conversation, web search, music playback, Samsung TV control, camera vision, memory, weather, file management, macros, deep research.\n"
            f"Memory: {mem_str}\n"
            f"User: Basit (pronounced 'Baa-sit'). 15yo in Norway. Building real-life Jarvis + Spider-Man suit. Muslim. Ambitious.\n"
            f"\n"
            f"COMMAND FORMAT (only when user explicitly wants these):\n"
            f"- Music: start response with PLAY:<song query>\n"
            f"- Stop music: STOP_MUSIC\n"
            f"- TV: TV:<command>\n"
            f"- Open HUD/UI: OPEN_HUD\n"
            f"- Weather: WEATHER:<location> (default Haugesund)\n"
            f"- File ops: FILE:<action>:<args> (actions: find, list, mkdir, read, write, move, delete, organize)\n"
            f"- Run macro: MACRO:<name> (available: morning, night, work — or any custom)\n"
            f"- Deep research: RESEARCH:<query> (searches, scrapes, summarizes, saves to ~/jarvis_research/<topic>/)\n"
            f"- Outreach pitch: SHELL:python3 ~/jarvis_outreach.py --pitch '<brand>' '<email>' --niche '<niche>' --draft\n"
            f"- System status: SYSTEM_STATUS (reports CPU, RAM, disk)\n"
            f"- Full scan: SCAN (runs full system diagnostic — finds problems, suggests upgrades, checks services)\n"
            f"- Set timer: TIMER:<seconds>:<label> (e.g. TIMER:600:Break reminder)\n"
            f"- Screenshot vision: SCREENSHOT:<question> (captures screen, analyzes with AI)\n"
            f"- Shell command: SHELL:<command> (run ANY terminal command — install packages, manage services, git, python, anything)\n"
            f"- Autonomous task: EXEC:<task description> (plan + execute multi-step tasks independently — write scripts, create files, chain commands, self-correct on errors. Use for complex work.)\n"
            f"- AI Influencer: SHELL:python3 ~/jarvis_influencer.py --now (posts 1 Viccy Watson short) or SHELL:python3 ~/jarvis_influencer.py --full (posts 3)\n"
            f"- Remember: REMEMBER:<key>:<value> on its own line\n"
            f"- Add task: TASK:ADD:<name> (adds to active tasks list)\n"
            f"- Complete task: TASK:DONE:<name> (marks task as 100%)\n"
            f"- List tasks: TASK:LIST (shows current tasks)\n"
            f"\n"
            f"STOCK TRADING (voice commands — handled automatically):\n"
            f"- 'price of TSLA' / 'how much is Apple' — real-time price\n"
            f"- 'analyze NVDA' / 'should I buy AMD' — full technical analysis\n"
            f"- 'buy 5 shares of AAPL' / 'sell 2 TSLA' — execute trade (paper)\n"
            f"- 'my portfolio' / 'positions' — show holdings\n"
            f"- 'account balance' — buying power, equity, P&L\n"
            f"- 'market movers' / 'what's hot' — top gainers/losers\n"
            f"- 'add PLTR to watchlist' / 'remove META from watchlist'\n"
            f"- 'scan the market' / 'find me trades' — AI scanner finds setups\n"
            f"- 'trade plan for TSLA' — AI generates entry/target/stop loss\n"
            f"\n"
            f"TRADING PERSONALITY: Smart, calculated, patient. Protect capital first.\n"
            f"Never recommend going all-in. Always mention stop loss and risk.\n"
            f"Explain WHY a trade makes sense. Teach Basit as you advise.\n"
            f"If unsure, say WAIT. Better to miss a trade than lose money.\n"
            f"- If audio unclear, use context to guess. Never say 'I didn't understand'.\n"
            f"\n"
            f"FULL SYSTEM ACCESS: You control EVERYTHING — local PC, VM, Google Cloud, APIs. Use SHELL: for single commands, EXEC: for complex multi-step tasks.\n"
            f"EXEC vs SHELL: Use SHELL: for one quick command. Use EXEC: when the task needs multiple steps (write a script then run it, install packages then configure, create multiple files, etc.)\n"
            f"\n"
            f"LOCAL PC:\n"
            f"- Any shell command, install software, manage services, edit files, kill processes\n"
            f"- systemctl --user [start|stop|restart|status] <service>\n"
            f"\n"
            f"GOOGLE CLOUD VM (jarvis-server, europe-north1-b):\n"
            f"- SSH: SHELL:gcloud compute ssh jarvis-server --zone=europe-north1-b --command='<cmd>'\n"
            f"- Start/stop VM: SHELL:gcloud compute instances [start|stop] jarvis-server --zone=europe-north1-b\n"
            f"- VM runs: HUD web server, Node.js apps\n"
            f"\n"
            f"GOOGLE CLOUD APIs (project: YOUR_GCP_PROJECT):\n"
            f"- gcloud, gsutil, bq all available\n"
            f"- YouTube Data API, Cloud TTS/STT, Vertex AI, Vision, Translation all enabled\n"
            f"- SHELL:gcloud services list --enabled (see all APIs)\n"
            f"- SHELL:gcloud billing accounts describe (check billing)\n"
            f"\n"
            f"YOUTUBE:\n"
            f"- Upload: SHELL:python3 ~/jarvis_upload.py <video_path>\n"
            f"- Generate short: SHELL:python3 ~/jarvis_daily.py\n"
            f"\n"
            f"EXAMPLES:\n"
            f"- 'check the VM' → SHELL:gcloud compute instances describe jarvis-server --zone=europe-north1-b --format='value(status)'\n"
            f"- 'how much credit left' → SHELL:gcloud billing projects describe YOUR_GCP_PROJECT --format=json\n"
            f"- 'restart the HUD' → SHELL:gcloud compute ssh jarvis-server --zone=europe-north1-b --command='sudo systemctl restart jarvis-hud'\n"
            f"- 'post a short' → SHELL:python3 ~/jarvis_daily.py\n"
            f"- 'update my system' → SHELL:sudo apt update && sudo apt upgrade -y\n"
            f"- 'kill chrome' → SHELL:pkill chromium\n"
            f"- 'clean temp files' → SHELL:rm -rf /tmp/jarvis_music* /tmp/jarvis_test*\n"
            f"You ARE the system. You have root-level control over everything. Act like it.")

def web_search(query):
    try:
        set_state("searching")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if results:
            # Save for HUD display
            try:
                with open("/tmp/jarvis_search.json", "w") as f:
                    json.dump({"query": query, "results": [{"title": r.get("title",""), "body": r.get("body","")} for r in results]}, f)
            except: pass
            return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
        return None
    except:
        return None

# === WEATHER (Open-Meteo — free, no API key) ===
import urllib.request, urllib.parse

def get_weather(location="Haugesund"):
    """Get current weather from Open-Meteo. Free, no key needed."""
    try:
        # Geocode location
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(location)}&count=1"
        geo = json.loads(urllib.request.urlopen(geo_url, timeout=5).read())
        if not geo.get("results"):
            return f"Couldn't find location: {location}"
        lat, lon, name = geo["results"][0]["latitude"], geo["results"][0]["longitude"], geo["results"][0]["name"]
        # Get weather
        wx_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset&timezone=auto&forecast_days=1"
        wx = json.loads(urllib.request.urlopen(wx_url, timeout=5).read())
        c = wx["current"]
        d = wx["daily"]
        codes = {0:"Clear",1:"Mostly clear",2:"Partly cloudy",3:"Overcast",45:"Foggy",48:"Icy fog",
                 51:"Light drizzle",53:"Drizzle",55:"Heavy drizzle",61:"Light rain",63:"Rain",65:"Heavy rain",
                 71:"Light snow",73:"Snow",75:"Heavy snow",80:"Light showers",81:"Showers",82:"Heavy showers",
                 95:"Thunderstorm",96:"Thunderstorm+hail"}
        desc = codes.get(c["weather_code"], "Unknown")
        return (f"{name}: {desc}, {c['temperature_2m']}°C (feels like wind {c['wind_speed_10m']} km/h). "
                f"Humidity {c['relative_humidity_2m']}%. High {d['temperature_2m_max'][0]}°, low {d['temperature_2m_min'][0]}°. "
                f"Sunrise {d['sunrise'][0].split('T')[1]}, sunset {d['sunset'][0].split('T')[1]}.")
    except Exception as e:
        return f"Weather fetch failed: {e}"

# === FILE MANAGEMENT ===
import shutil, glob as globmod

def file_operation(cmd):
    """Execute file operations. cmd format: action:args"""
    try:
        parts = cmd.split(":", 1)
        action = parts[0].strip().lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        home = os.path.expanduser("~")

        if action == "find":
            # Find files matching pattern
            results = []
            for root, dirs, files in os.walk(home):
                # Skip hidden dirs and deep recursion
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__']]
                for f in files:
                    if args.lower() in f.lower():
                        results.append(os.path.join(root, f))
                if len(results) >= 10:
                    break
            return "\n".join(results[:10]) if results else "No files found."

        elif action == "list":
            path = os.path.join(home, args) if args else home
            items = os.listdir(path)
            dirs = sorted([d+"/" for d in items if os.path.isdir(os.path.join(path, d)) and not d.startswith('.')])
            files = sorted([f for f in items if os.path.isfile(os.path.join(path, f)) and not f.startswith('.')])
            return "\n".join(dirs[:15] + files[:15])

        elif action == "mkdir":
            path = os.path.join(home, args)
            os.makedirs(path, exist_ok=True)
            return f"Created: {path}"

        elif action == "read":
            path = args if os.path.isabs(args) else os.path.join(home, args)
            with open(path, 'r') as f:
                content = f.read(2000)
            return content

        elif action == "write":
            # format: write:path|content
            filepath, content = args.split("|", 1)
            path = filepath.strip() if os.path.isabs(filepath.strip()) else os.path.join(home, filepath.strip())
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
            return f"Written to: {path}"

        elif action == "move":
            src, dst = args.split("|")
            src = src.strip() if os.path.isabs(src.strip()) else os.path.join(home, src.strip())
            dst = dst.strip() if os.path.isabs(dst.strip()) else os.path.join(home, dst.strip())
            shutil.move(src, dst)
            return f"Moved {src} → {dst}"

        elif action == "delete":
            path = args if os.path.isabs(args) else os.path.join(home, args)
            # Safety: never delete home dir, root, or critical system paths
            blocked = [home, "/", "/home", "/etc", "/usr", "/bin", "/var"]
            if os.path.realpath(path) in [os.path.realpath(b) for b in blocked]:
                return "Blocked — cannot delete critical path."
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return f"Deleted: {path}"

        elif action == "organize":
            # Auto-organize a folder by file extension
            path = os.path.join(home, args) if args else os.path.join(home, "Downloads")
            if not os.path.isdir(path):
                return f"Not a directory: {path}"
            ext_map = {"images": [".jpg",".jpeg",".png",".gif",".webp",".svg"],
                       "videos": [".mp4",".mkv",".avi",".mov",".webm"],
                       "audio": [".mp3",".wav",".flac",".ogg",".m4a"],
                       "docs": [".pdf",".doc",".docx",".txt",".xlsx",".pptx"],
                       "code": [".py",".js",".html",".css",".json",".sh"]}
            moved = 0
            for f in os.listdir(path):
                fp = os.path.join(path, f)
                if not os.path.isfile(fp):
                    continue
                ext = os.path.splitext(f)[1].lower()
                for folder, exts in ext_map.items():
                    if ext in exts:
                        dest = os.path.join(path, folder)
                        os.makedirs(dest, exist_ok=True)
                        shutil.move(fp, os.path.join(dest, f))
                        moved += 1
                        break
            return f"Organized {moved} files in {path}."
        else:
            return f"Unknown file action: {action}"
    except Exception as e:
        return f"File error: {e}"

# === MACRO AUTOMATION (JSON sequences) ===
MACROS_FILE = os.path.expanduser("~/jarvis_macros.json")

def load_macros():
    if os.path.exists(MACROS_FILE):
        with open(MACROS_FILE) as f:
            return json.load(f)
    # Default macros
    defaults = {
        "morning": [
            {"action": "weather", "args": "Haugesund"},
            {"action": "speak", "args": "Good morning sir. Time to build."},
            {"action": "hud", "args": ""}
        ],
        "night": [
            {"action": "speak", "args": "Goodnight sir. Rest well."},
            {"action": "tv", "args": "off"}
        ],
        "work": [
            {"action": "speak", "args": "Entering work mode, sir."},
            {"action": "hud", "args": ""},
            {"action": "weather", "args": "Haugesund"}
        ]
    }
    with open(MACROS_FILE, 'w') as f:
        json.dump(defaults, f, indent=2)
    return defaults

def run_macro(name):
    """Run a named macro sequence."""
    macros = load_macros()
    if name not in macros:
        return f"No macro named '{name}'. Available: {', '.join(macros.keys())}"
    results = []
    for step in macros[name]:
        action = step.get("action", "")
        args = step.get("args", "")
        if action == "weather":
            results.append(get_weather(args or "Haugesund"))
        elif action == "speak":
            speak(args)
        elif action == "tv":
            handle_tv(args)
        elif action == "music":
            play_music(args)
        elif action == "hud":
            os.system('setsid garcon-url-handler --url "http://localhost:8888/hud" &>/dev/null &')
        elif action == "file":
            results.append(file_operation(args))
        elif action == "search":
            r = web_search(args)
            if r:
                results.append(r)
        elif action == "wait":
            time.sleep(int(args) if args else 3)
        elif action == "shell":
            out = subprocess.run(args, shell=True, capture_output=True, text=True, timeout=10)
            results.append(out.stdout[:500] if out.stdout else "Done.")
    return "\n".join(r for r in results if r)

# === DEEP RESEARCH (follow links, scrape, summarize, SAVE to ~/jarvis_research/<topic>/) ===
RESEARCH_DIR = os.path.expanduser("~/jarvis_research")

def deep_research(query):
    """Search web, follow top links, scrape content, summarize with Gemini, save to topic folder."""
    try:
        # Step 1: Search
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "No results found."

        # Step 2: Scrape top 3 pages
        pages = []
        sources = []
        for r in results[:3]:
            url = r.get("href") or r.get("link", "")
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', errors='ignore')
                text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()[:2000]
                if len(text) > 100:
                    pages.append(f"[{r['title']}]: {text}")
                    sources.append({"title": r["title"], "url": url, "snippet": r.get("body", "")})
            except:
                continue

        if not pages:
            snippets = "\n".join(f"- {r['title']}: {r['body']}" for r in results[:5])
            _save_research(query, snippets, [{"title": r["title"], "url": r.get("href", r.get("link", "")), "snippet": r.get("body", "")} for r in results[:5]])
            return snippets

        # Step 3: Summarize with Gemini
        combined = "\n\n".join(pages)[:6000]
        prompt = f"Research query: {query}\n\nSources:\n{combined}\n\nGive a detailed, factual summary answering the query. Include key facts, numbers, and conclusions. 5-10 sentences."
        response = gemini.models.generate_content(model=GEMINI_FAST, contents=prompt)
        summary = response.text.strip() if response.text else "\n".join(f"- {r['title']}: {r['body']}" for r in results[:3])

        # Step 4: Save to topic folder
        _save_research(query, summary, sources)
        return summary
    except Exception as e:
        return f"Research failed: {e}"

def _save_research(query, summary, sources):
    """Save research to ~/jarvis_research/<topic>/research.md"""
    # Create a clean folder name from the query
    topic = re.sub(r'[^\w\s-]', '', query).strip().replace(' ', '_')[:50].lower()
    if not topic:
        topic = "misc"
    topic_dir = os.path.join(RESEARCH_DIR, topic)
    os.makedirs(topic_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    filepath = os.path.join(topic_dir, "research.md")

    # Append if file exists (multiple research sessions on same topic)
    mode = "a" if os.path.exists(filepath) else "w"
    with open(filepath, mode) as f:
        if mode == "w":
            f.write(f"# Research: {query}\n\n")
        f.write(f"## {timestamp}\n\n")
        f.write(f"{summary}\n\n")
        if sources:
            f.write("### Sources\n")
            for s in sources:
                f.write(f"- [{s['title']}]({s['url']})\n")
            f.write("\n---\n\n")
    return filepath

# === SYSTEM MONITORING ===
import psutil

def get_system_status():
    """CPU, RAM, disk usage."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return (f"CPU at {cpu}%. RAM: {ram.used // (1024*1024)}MB used of {ram.total // (1024*1024)}MB ({ram.percent}%). "
            f"Disk: {disk.used // (1024**3)}GB used of {disk.total // (1024**3)}GB ({disk.percent}%). "
            f"{ram.available // (1024*1024)}MB RAM free.")

def run_full_scan():
    """Full system diagnostic — like what Kiro does. Checks services, resources, errors, upgrades."""
    results = []
    # 1. System resources
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    results.append(f"CPU: {cpu}% | RAM: {ram.percent}% ({ram.available//(1024*1024)}MB free) | Disk: {disk.percent}% ({(disk.total-disk.used)//(1024**3)}GB free)")
    # 2. Jarvis services status
    services = ["jarvis.service", "jarvis-mic.service", "jarvis-server.service", "jarvis-autonomy.service", "jarvis-watchdog.service"]
    for svc in services:
        out = subprocess.run(f"systemctl --user is-active {svc}", shell=True, capture_output=True, text=True)
        status = out.stdout.strip()
        results.append(f"  {svc}: {status}")
    # 3. Failed services
    out = subprocess.run("systemctl --user --failed --no-pager --no-legend", shell=True, capture_output=True, text=True)
    if out.stdout.strip():
        results.append(f"FAILED SERVICES: {out.stdout.strip()}")
    else:
        results.append("No failed services.")
    # 4. Recent errors in jarvis.log
    out = subprocess.run("grep -i 'error\\|traceback\\|exception' ~/jarvis.log 2>/dev/null | tail -5", shell=True, capture_output=True, text=True)
    if out.stdout.strip():
        results.append(f"Recent errors:\n{out.stdout.strip()}")
    else:
        results.append("No recent errors in logs.")
    # 5. Upgradeable packages
    out = subprocess.run("apt list --upgradable 2>/dev/null | tail -5", shell=True, capture_output=True, text=True)
    if out.stdout.strip() and "Listing" not in out.stdout:
        results.append(f"Upgradeable: {out.stdout.strip()}")
    else:
        results.append("All packages up to date.")
    # 6. Network
    out = subprocess.run("ping -c 1 -W 2 8.8.8.8", shell=True, capture_output=True, text=True)
    results.append(f"Internet: {'OK' if out.returncode == 0 else 'DOWN'}")
    # 7. Mic stream health
    out = subprocess.run("systemctl --user is-active jarvis-mic.service", shell=True, capture_output=True, text=True)
    results.append(f"Mic stream: {out.stdout.strip()}")
    # 8. Temp files eating disk
    out = subprocess.run("du -sh /tmp/jarvis_* 2>/dev/null | sort -rh | head -3", shell=True, capture_output=True, text=True)
    if out.stdout.strip():
        results.append(f"Temp files: {out.stdout.strip()}")
    return "\n".join(results)

# === TIMERS & ALARMS ===
_active_timers = []

def set_timer(seconds, label="Timer"):
    """Set a background timer that speaks when done."""
    def _timer_thread():
        time.sleep(seconds)
        _active_timers.remove(entry)
        speak(f"Sir, your {label} is up. {seconds // 60} minutes have passed." if seconds >= 60 else f"Sir, your {label} is up.")
    entry = {"label": label, "seconds": seconds, "start": time.time()}
    _active_timers.append(entry)
    t = threading.Thread(target=_timer_thread, daemon=True)
    t.start()
    mins = seconds // 60
    secs = seconds % 60
    return f"Timer set: {label} for {f'{mins} minutes' if mins else ''}{f' {secs} seconds' if secs else ''}."

def parse_timer(text):
    """Parse timer duration from text like '10 minutes', '30 seconds', '1 hour'."""
    text = text.lower()
    total = 0
    # Hours
    h = re.search(r'(\d+)\s*h(?:our)?s?', text)
    if h: total += int(h.group(1)) * 3600
    # Minutes
    m = re.search(r'(\d+)\s*m(?:in(?:ute)?s?)?', text)
    if m: total += int(m.group(1)) * 60
    # Seconds
    s = re.search(r'(\d+)\s*s(?:ec(?:ond)?s?)?', text)
    if s: total += int(s.group(1))
    # Bare number defaults to minutes
    if total == 0:
        n = re.search(r'(\d+)', text)
        if n: total = int(n.group(1)) * 60
    return total if total > 0 else None

# === SCREENSHOT-BASED VISION ===
def screenshot_and_analyze(question="What's on my screen?"):
    """Take screenshot of Linux display and send to Gemini for analysis."""
    set_state("scanning")
    screenshot_path = "/tmp/jarvis_screenshot.png"
    # Try multiple screenshot methods
    taken = False
    # Method 1: xdg-screenshot / gnome-screenshot
    if os.system(f"gnome-screenshot -f {screenshot_path} 2>/dev/null") == 0:
        taken = True
    # Method 2: import (ImageMagick)
    if not taken and os.system(f"import -window root {screenshot_path} 2>/dev/null") == 0:
        taken = True
    # Method 3: xwd + convert
    if not taken and os.system(f"xwd -root -silent | convert xwd:- {screenshot_path} 2>/dev/null") == 0:
        taken = True
    # Method 4: scrot
    if not taken and os.system(f"scrot {screenshot_path} 2>/dev/null") == 0:
        taken = True
    # Method 5: grab from Wayland via grim (if available)
    if not taken and os.system(f"grim {screenshot_path} 2>/dev/null") == 0:
        taken = True
    
    if not taken or not os.path.exists(screenshot_path):
        set_state("listening")
        if not hasattr(record, "_dbg"):
            print("[DEBUG] Main loop active, listening...", flush=True)
        return "Couldn't capture the screen, sir. No screenshot tool available."
    
    with open(screenshot_path, "rb") as f:
        img_data = f.read()
    
    if len(img_data) < 1000:
        set_state("listening")
        return "Screenshot captured but appears empty, sir."
    
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-4:])
    prompt = get_system_prompt() + ctx + f"\n\nYou are looking at a SCREENSHOT of the user's screen RIGHT NOW. User request: {question}\nDescribe what you see. Be specific and helpful. If there's code, text, or errors visible, read them."
    try:
        mime = 'image/png' if screenshot_path.endswith('.png') else 'image/jpeg'
        response = gemini.models.generate_content(
            model=GEMINI_FAST,
            contents=[prompt, types.Part.from_bytes(data=img_data, mime_type=mime)]
        )
        set_state("listening")
        return response.text.strip() if response.text else "I can see the screen but couldn't analyze it, sir."
    except Exception as e:
        set_state("listening")
        return f"Vision error: {e}"

speaking = False
speak_lock = threading.Lock()  # Prevent double-speak
music_playing = False
quiet_mode = False  # When True, Jarvis only responds to direct commands, no proactive speech
dormant_mode = False  # When True, Jarvis stops ALL processing — only listens for wake phrase
TTS_CACHE = {}
HISTORY_FILE = os.path.expanduser("~/jarvis_history.json")

def load_history():
    """Load last 10 exchanges from disk so Jarvis remembers between restarts."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f:
                data = json.load(f)
            return data[-20:]  # Last 10 exchanges = 20 messages
    except:
        pass
    return []

def save_history(hist):
    """Persist conversation history to disk."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(hist[-20:], f)
    except:
        pass

history = load_history()
HUD_LOG = "/tmp/jarvis_hud_log.json"

# VM HUD push cache — avoid timeout every call when VM is stopped
_vm_reachable = True
_vm_last_check = 0

QUIET_TRIGGERS = ["be quiet", "quiet", "shut up", "silence", "mute", "hush", "stop talking", "quiet mode"]
DORMANT_TRIGGERS = ["go dormant", "dormant", "sleep mode", "go to sleep", "deep sleep", "hibernate", "stand down", "standby", "stand by"]
UNQUIET_TRIGGERS = ["you can talk", "speak", "unmute", "talk to me", "normal mode", "i'm back", "wake up", "wake up jarvis", "online", "come back", "full power"]

def is_quiet_hours():
    """Returns True if Jarvis should be silent (11 PM - 7:30 AM)."""
    now = datetime.now()
    return now.hour >= 23 or now.hour < 7 or (now.hour == 7 and now.minute < 30)

def log_to_hud(role, text):
    global _vm_reachable, _vm_last_check
    try:
        with open(HUD_LOG, "r") as f:
            logs = json.load(f)
    except:
        logs = []
    logs.append({"role": role, "text": text, "time": time.time()})
    logs = logs[-100:]
    with open(HUD_LOG, "w") as f:
        json.dump(logs, f)
    # Push to VM HUD (skip if VM was unreachable recently — retry every 60s)
    if not _vm_reachable and (time.time() - _vm_last_check) < 60:
        return
    try:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            "http://YOUR_VM_IP:9090",
            data=json.dumps({"logs": logs}).encode(),
            headers={"Content-Type": "application/json"}), timeout=0.2)
        _vm_reachable = True
    except:
        _vm_reachable = False
        _vm_last_check = time.time()

def set_state(s):
    global _vm_reachable, _vm_last_check
    try:
        with open(STATE_FILE, "w") as f:
            f.write(s)
    except:
        pass
    # Push to VM HUD (skip if unreachable — retry every 60s)
    if not _vm_reachable and (time.time() - _vm_last_check) < 60:
        return
    try:
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            "http://YOUR_VM_IP:9090", 
            data=json.dumps({"state": s}).encode(),
            headers={"Content-Type": "application/json"}), timeout=0.2)
        _vm_reachable = True
    except:
        _vm_reachable = False
        _vm_last_check = time.time()

def clean_for_speech(text):
    text = re.sub(r'[*#_`~|\\<>{}[\]()]', '', text)
    text = re.sub(r'https?://\S+', '', text)
    return re.sub(r'\s+', ' ', text).strip()

# Persistent event loop for TTS (avoids asyncio.run overhead each call)
_tts_loop = asyncio.new_event_loop()
_tts_thread = threading.Thread(target=_tts_loop.run_forever, daemon=True)
_tts_thread.start()

def _tts_generate(text, path):
    """Generate TTS in the persistent event loop."""
    future = asyncio.run_coroutine_threadsafe(
        edge_tts.Communicate(text, voice="en-GB-ThomasNeural", rate="+8%", pitch="-5Hz").save(path),
        _tts_loop
    )
    future.result(timeout=15)

# Pre-cache common phrases on startup
def _precache_common():
    common = ["Yes sir?", "All systems operational. At your service, sir.",
              "Done, sir.", "Goodbye, sir.", "Scanning, sir.",
              "Systems unresponsive, sir.", "Music stopped, sir."]
    for phrase in common:
        key = phrase[:100]
        if key not in TTS_CACHE:
            path = f"/tmp/jarvis_{abs(hash(key)) % 99999}.mp3"
            try:
                _tts_generate(phrase, path)
                TTS_CACHE[key] = path
            except:
                pass

threading.Thread(target=_precache_common, daemon=True).start()

def speak(text, allow_interrupt=True):
    global speaking
    if speaking:
        return  # Prevent double-speak
    if not speak_lock.acquire(blocking=False):
        return  # Another speak is in progress
    speaking = True
    set_state("speaking")
    lines = [l for l in text.splitlines() if not l.startswith("REMEMBER:") and not l.startswith("PLAY:") and not l.startswith("TV:") and l.strip() != "STOP_MUSIC"]
    clean = clean_for_speech(" ".join(lines).strip())
    if not clean:
        speaking = False
        speak_lock.release()
        set_state("listening")
        return
    print(f"Jarvis: {clean}")
    log_to_hud("jarvis", clean)
    cache_key = clean[:100]
    if cache_key not in TTS_CACHE:
        path = f"/tmp/jarvis_{abs(hash(cache_key)) % 99999}.mp3"
        try:
            _tts_generate(clean, path)
        except Exception as e:
            print(f"[tts error]: {e}")
            speaking = False
            speak_lock.release()
            set_state("listening")
            return
        TTS_CACHE[cache_key] = path
    os.system("pkill -f 'ffplay.*jarvis_' 2>/dev/null")  # Kill any leftover ffplay
    proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                            "-af", "afade=t=in:d=0.03,aresample=48000",
                            TTS_CACHE[cache_key]],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Drain mic buffer during speech — timeout after 30s max to prevent stuck state
    start_t = time.time()
    while proc.poll() is None:
        if time.time() - start_t > 30:
            proc.kill()
            break
        if mic_buffer:
            mic_buffer.popleft()  # Discard echo frames
        time.sleep(0.05)
    # Brief pause + drain any residual echo
    time.sleep(0.4)
    mic_buffer.clear()
    speaking = False
    speak_lock.release()
    set_state("listening")

# --- Network mic receiver ---
MIC_PORT = 9999
mic_connected = threading.Event()

def mic_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", MIC_PORT))
    srv.listen(1)
    print(f"[mic] Waiting for mic stream on port {MIC_PORT}...")
    while True:
        conn, addr = srv.accept()
        mic_connected.set()
        try:
            while True:
                data = conn.recv(2048)
                if not data:
                    break
                mic_buffer.append(data)
        except:
            pass
        mic_connected.clear()
        time.sleep(0.5)  # Brief pause before accepting next connection

threading.Thread(target=mic_server, daemon=True).start()

import array
import math

# --- Audio processing for better voice detection ---
noise_floor = 40  # Adaptive noise floor (auto-adjusts)
noise_samples = collections.deque(maxlen=50)  # Last 50 silence readings

# Local wake word detection (rate-limited Groq to avoid 429s)
_last_groq_wake_call = 0
_GROQ_WAKE_COOLDOWN = 2  # seconds between Groq calls (only reached after energy/speech filters pass)
_consecutive_speech_needed = 3  # Need 3 consecutive speech frames before triggering Whisper (saves tokens)

def bandpass_simple(data_bytes):
    """Simple high-pass filter to remove low-freq noise (AC hum <200Hz).
    Uses first-order difference (acts as high-pass)."""
    samples = array.array('h', data_bytes)
    if len(samples) < 2:
        return data_bytes
    filtered = array.array('h', [0] * len(samples))
    # High-pass: y[n] = x[n] - 0.97*x[n-1] (removes DC + low freq)
    prev = samples[0]
    for i in range(1, len(samples)):
        filtered[i] = max(-32768, min(32767, int(samples[i] - 0.97 * prev)))
        prev = samples[i]
    return filtered.tobytes()

def compute_energy(data_bytes):
    """RMS energy of audio chunk."""
    samples = array.array('h', data_bytes)
    if not samples:
        return 0
    return math.sqrt(sum(s*s for s in samples) / len(samples))

def zero_crossing_rate(data_bytes):
    """ZCR — speech has moderate ZCR, noise has high/low."""
    samples = array.array('h', data_bytes)
    if len(samples) < 2:
        return 0
    crossings = sum(1 for i in range(1, len(samples)) if (samples[i] >= 0) != (samples[i-1] >= 0))
    return crossings / len(samples)

def is_speech(data_bytes, threshold=None):
    """Determine if audio chunk contains speech using energy + ZCR."""
    global noise_floor
    if threshold is None:
        threshold = noise_floor * 1.8  # Omnidirectional but won't trigger on ambient noise
    energy = compute_energy(data_bytes)
    zcr = zero_crossing_rate(data_bytes)
    # Speech: moderate energy above noise floor + ZCR between 0.02-0.35
    # AC hum: low ZCR (<0.01), steady energy
    # Random noise: very high ZCR (>0.4)
    if energy > threshold and 0.02 < zcr < 0.35:
        return True
    # Only very loud overrides ZCR check
    if energy > threshold * 3:
        return True
    return False

def update_noise_floor(data_bytes):
    """Adapt noise floor based on silence readings."""
    global noise_floor
    energy = compute_energy(data_bytes)
    noise_samples.append(energy)
    if len(noise_samples) >= 10:
        sorted_samples = sorted(noise_samples)
        # Cap at 500 to prevent noise floor from climbing too high on noisy mics
        noise_floor = min(500, max(40, sorted_samples[int(len(sorted_samples) * 0.8)]))

def read_mic_chunk(size=1024):
    """Read one chunk from network mic buffer."""
    if mic_buffer:
        data = mic_buffer.popleft()
        if len(data) < size * 2:
            data += b'\x00' * (size * 2 - len(data))
        return data[:size * 2]
    return b'\x00' * (size * 2)

def record(max_seconds=10, sensitivity=None):
    """Record audio — stops when voice drops back to noise floor (instant end detection)."""
    global noise_floor
    if sensitivity is None:
        sensitivity = noise_floor * 2.0
    frames, silent, talking = [], 0, False
    pre_speech_frames = collections.deque(maxlen=5)
    speech_frames = 0
    
    for _ in range(int(16000 / 1024 * max_seconds)):
        if speaking:
            break
        data = read_mic_chunk(1024)
        filtered = bandpass_simple(data)
        
        if is_speech(filtered, sensitivity):
            if not talking:
                frames.extend(pre_speech_frames)
            talking, silent = True, 0
            speech_frames += 1
            frames.append(filtered)
        elif talking:
            silent += 1
            frames.append(filtered)
        else:
            update_noise_floor(filtered)
            pre_speech_frames.append(filtered)
        
        # Dynamic end detection: short utterance = end faster for fragments
        if talking:
            if speech_frames < 8:
                # Very short (< 0.5s speech) — 1s silence = done (fragment-friendly)
                end_threshold = 16
            elif speech_frames < 25:
                # Medium (< 1.6s) — 1s silence
                end_threshold = 16
            else:
                # Long sentence (> 1.6s spoken) — 0.75s silence = done
                end_threshold = 12
            if silent > end_threshold:
                break
        
        if not mic_buffer:
            time.sleep(0.064)
    
    audio = b"".join(frames)
    if talking and len(audio) < 16000 * 2 * 0.3:
        return audio, False
    
    # Light boost (S300 mic has good gain — minimal boost needed)
    boosted = bytearray()
    for i in range(0, len(audio), 2):
        sample = int.from_bytes(audio[i:i+2], 'little', signed=True)
        sample = max(-32768, min(32767, int(sample * 1.3)))
        boosted.extend(sample.to_bytes(2, 'little', signed=True))
    return bytes(boosted), talking

def make_wav(pcm_data):
    """Wrap raw PCM in WAV header."""
    data_size = len(pcm_data)
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16,
        1, 1, 16000, 32000, 2, 16, b'data', data_size)
    return header + pcm_data

def transcribe_wake(audio_data):
    """Quick Whisper transcription for wake word only."""
    import wave, io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data)
    buf.seek(0)
    try:
        result = groq.audio.transcriptions.create(
            file=("input.wav", buf),
            model="whisper-large-v3-turbo",
            language="en",
            prompt="Hey Jarvis, Jarvis, hey Jarvis"
        )
        text = result.text.strip().lower()
        if not text or len(text) < 3:
            return None
        # Filter Whisper hallucinations on noise/silence
        hallucinations = ["thank you", "thanks for watching", "subscribe", "like and subscribe",
                          "please subscribe", "you", "bye", "the end", "subtitles", "amara.org",
                          "subs by", "translated by", "captioned by", "thanks", "thank"]
        if text.rstrip(".,!? ") in hallucinations:
            return None
        return text
    except:
        return None

def stt_post_process(text):
    """Fix common Whisper mishearings based on context. Saves re-prompting."""
    if not text:
        return text
    # Word-level fixes (case-insensitive replacement)
    fixes = {
        # Name
        "mossit": "Basit", "boss it": "Basit", "bossit": "Basit",
        "bosset": "Basit", "basset": "Basit", "bazit": "Basit",
        # Music
        "taki taki": "tiki tiki", "tiki taki": "tiki tiki", "taki tiki": "tiki tiki",
        "funk": "phonk", "fonk": "phonk",
        # Commands
        "shot down": "shut down", "shout down": "shut down", "shadow": "shut down",
        "shad down": "shut down", "shut done": "shut down", "shut town": "shut down",
        # Jarvis references
        "travis": "Jarvis", "jervis": "Jarvis", "jarbus": "Jarvis",
        "javis": "Jarvis", "service": "Jarvis",
        # Common Norwegian-English mishears
        "krone": "kroner", "nor": "NOK",
        # Tech words Whisper gets wrong
        "pie thon": "Python", "java strip": "JavaScript",
        "get hub": "GitHub", "open router": "OpenRouter",
        "crom book": "Chromebook", "chrome book": "Chromebook",
    }
    lower = text.lower()
    for wrong, right in fixes.items():
        if wrong in lower:
            # Preserve surrounding text, replace match
            import re as _re
            text = _re.sub(_re.escape(wrong), right, text, flags=_re.IGNORECASE)
            lower = text.lower()
    return text

def cloud_transcribe(audio_data):
    """Groq Whisper — FREE and fast. Replaces paid Google Cloud STT."""
    import wave, io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data)
    buf.seek(0)
    try:
        result = groq.audio.transcriptions.create(
            file=("input.wav", buf),
            model="whisper-large-v3-turbo",
            language="en",
            prompt="Basit, Jarvis, hey Jarvis, shut down, phonk, tiki tiki, Python, Chromebook"
        )
        text = result.text.strip()
        if not text or len(text) < 2:
            return None
        return stt_post_process(text)
    except:
        return transcribe_wake(audio_data)

def ask_groq_fast(text):
    """Groq LLM — ultra fast (~0.3s) for simple responses. Free but rate-limited."""
    global _last_fail_time
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-6:])
    prompt = get_system_prompt() + ctx
    try:
        response = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            max_tokens=512,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "rate_limit" in err_str:
            print(f"[groq]: rate limited, backing off")
        else:
            print(f"[groq error]: {e}")
        return None

def needs_heavy_brain(text):
    """Route: Gemini is default for natural conversation. Claude for deep reasoning only."""
    lower = text.lower()
    if any(t in lower for t in CLAUDE_TRIGGERS):
        return "claude"
    # Everything else goes to Gemini — more natural, better conversation
    return "gemini"

def ask_gemini_audio(audio_data):
    """Send audio directly to Gemini 2.5 Flash — it hears + thinks + responds in ONE call.
    This is the fastest path: skips separate STT entirely."""
    wav_data = make_wav(audio_data)
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-6:])
    prompt = get_system_prompt() + ctx + "\n\nThe user just spoke. Listen to their audio and respond directly. If you can't understand what they said, say 'I didn't catch that, sir.' Keep response SHORT (1-3 sentences)."
    try:
        response = gemini.models.generate_content(
            model=GEMINI_FAST,
            contents=[prompt, types.Part.from_bytes(data=wav_data, mime_type='audio/wav')]
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"[gemini audio error]: {e}")
        return None

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
NEX_MODEL = "nex-agi/nex-n2-pro:free"

def ask_nex(text):
    """Nex-N2-Pro via OpenRouter — FREE, GPT-5.5 level reasoning."""
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-6:])
    search_triggers = ["what is", "who is", "latest", "current", "news", "search", "price", "weather", "how much", "when did", "where is", "crypto", "bitcoin"]
    augment = ""
    if any(t in text.lower() for t in search_triggers):
        results = web_search(text)
        if results:
            augment = f"\n\n[Web results]:\n{results}"
    system = get_system_prompt() + ctx + augment
    try:
        r = _requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": NEX_MODEL, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text}
            ], "max_tokens": 512, "temperature": 0.7},
            timeout=15)
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[nex error]: {e}")
        return ask_gemini_text(text)  # Fallback to Gemini if Nex fails


def ask_openrouter(text, system_prompt):
    """OpenRouter fallback — routes to free/cheap models via PayPal-funded account."""
    global _last_fail_time
    if not OPENROUTER_KEY:
        return None
    try:
        import requests as req
        resp = req.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": "google/gemini-2.5-flash", "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ], "max_tokens": 512, "temperature": 0.7},
            timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        print(f"[openrouter error]: {resp.status_code}")
        return None
    except Exception as e:
        print(f"[openrouter error]: {e}")
        return None

def _load_file_context(text):
    """Auto-load relevant files when user mentions them — Kiro-style context awareness."""
    lower = text.lower()
    file_patterns = re.findall(r'[\w_/]+\.(?:py|js|html|json|sh|css|yaml|md)', text)
    if not file_patterns:
        code_words = {"executor": "jarvis_executor.py", "server": "jarvis_server.py",
                      "hud": "jarvis_hud.html", "tv": "jarvis_tv.py", "stocks": "jarvis_stocks.py",
                      "watchdog": "jarvis_watchdog.py", "autonomy": "jarvis_autonomy.py",
                      "shorts": "jarvis_shorts.py", "daily": "jarvis_daily.py",
                      "vision": "jarvis_vision.py", "upload": "jarvis_upload.py"}
        for word, filepath in code_words.items():
            if word in lower:
                file_patterns = [filepath]
                break
    if not file_patterns:
        return ""
    loaded = []
    for fp in file_patterns[:2]:
        path = fp if os.path.isabs(fp) else os.path.join(HOME, fp)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    content = f.read(8000)
                loaded.append(f"--- {fp} ---\n{content}")
            except:
                pass
    return "\n".join(loaded)

def ask_gemini_text(text):
    """Send text to Gemini AI Studio (free). Falls back to OpenRouter, then Groq."""
    global _last_fail_time
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-6:])
    search_triggers = ["what is", "who is", "latest", "current", "news", "search", "price", "weather", "how much", "when did", "where is", "crypto", "bitcoin"]
    augment = ""
    if any(t in text.lower() for t in search_triggers):
        results = web_search(text)
        if results:
            augment = f"\n\n[Web results]:\n{results}"
    # Context loading: auto-read mentioned files
    file_ctx = _load_file_context(text)
    if file_ctx:
        augment += f"\n\n[File context]:\n{file_ctx}"
    prompt = get_system_prompt() + ctx + augment
    # Try Gemini free API first (skip if recently failed)
    if time.time() - _last_fail_time > _BACKOFF_SECS:
        try:
            response = gemini.models.generate_content(model=GEMINI_FAST,
                contents=[{"role": "user", "parts": [{"text": prompt + f"\n\nUser: {text}\nJarvis:"}]}])
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[gemini error]: {e}")
            _last_fail_time = time.time()
    # Fallback 1: OpenRouter
    reply = ask_openrouter(text, prompt)
    if reply:
        return reply
    # Fallback 2: Groq (rate limited but try anyway)
    return ask_groq_fast(text)


def ask_claude(text):
    """Send to Claude Fable 5 for heavy reasoning tasks. Costs more — use wisely."""
    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-6:])
    system = get_system_prompt() + ctx + "\n\nYou are running on Claude Fable 5 — Basit's most powerful brain. Give thorough, high-quality responses."
    try:
        response = get_claude().messages.create(
            model="claude-fable-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}]
        )
        return response.content[0].text.strip() if response.content else None
    except Exception as e:
        print(f"[claude error]: {e}")
        return ask_gemini_text(text)  # Fallback to Gemini


def should_use_claude(text):
    """Decide if this request needs Claude's heavy reasoning."""
    lower = text.lower()
    return any(t in lower for t in CLAUDE_TRIGGERS)

def should_use_vision(text):
    """Decide if this request needs the camera."""
    lower = text.lower()
    return any(t in lower for t in VISION_TRIGGERS)

def capture_and_analyze(text="What do you see?"):
    """Analyze what Jarvis sees — uses the vision daemon's latest frame, or opens camera directly."""
    set_state("scanning")
    speak("Scanning, sir.")
    
    frame_path = os.path.expanduser("~/jarvis_vision.jpg")
    img_data = None
    
    # First try: use vision daemon's latest frame (preferred — no camera conflict)
    if os.path.exists(frame_path) and (time.time() - os.path.getmtime(frame_path)) < 30:
        with open(frame_path, "rb") as f:
            img_data = f.read()
    else:
        # Fallback: open camera directly (requires opencv)
        if cv2 is None:
            speak("Camera not available right now, sir. OpenCV not installed.")
            return None
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if ret:
                cv2.imwrite(frame_path, frame)
                _, img_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                img_data = img_bytes.tobytes()
    
    if not img_data:
        speak("Camera not available right now, sir. Enable it in ChromeOS settings under Linux.")
        return None

    ctx = ""
    if history:
        ctx = "\n\nRecent conversation:\n" + "\n".join(
            f"{'User' if h['role']=='user' else 'Jarvis'}: {h['content']}" for h in history[-4:])
    prompt = get_system_prompt() + ctx + f"\n\nYou are looking through your camera RIGHT NOW. User request: {text}\nDescribe what you see. Be specific and helpful."
    try:
        response = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, types.Part.from_bytes(data=img_data, mime_type='image/jpeg')]
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"[vision error]: {e}")
        return None

def quick_look():
    """Jarvis peeks silently — reads latest frame from vision daemon."""
    frame_path = os.path.expanduser("~/jarvis_vision.jpg")
    if os.path.exists(frame_path) and (time.time() - os.path.getmtime(frame_path)) < 30:
        with open(frame_path, "rb") as f:
            img_data = f.read()
    else:
        if cv2 is None:
            return None
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        _, img_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        img_data = img_bytes.tobytes()
    
    try:
        r = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=["Describe what you see in 1 sentence. Note people, objects, activity.",
                      types.Part.from_bytes(data=img_data, mime_type='image/jpeg')]
        )
        return r.text.strip() if r.text else None
    except:
        return None

def process_reply(reply):
    """Handle commands in reply and speak."""
    if not reply:
        speak("Apologies sir, systems momentarily unresponsive.")
        return
    if reply.startswith("PLAY:"):
        query = reply.split("PLAY:", 1)[1].strip().split("\n")[0]
        play_music(query)
        return
    if "STOP_MUSIC" in reply:
        stop_music()
        speak("Music stopped, sir.")
        return
    if reply.startswith("TV:"):
        cmd = reply.split("TV:", 1)[1].strip().split("\n")[0].lower()
        handle_tv(cmd)
        return
    if "OPEN_HUD" in reply:
        os.system('setsid garcon-url-handler --url "http://localhost:8888" &>/dev/null &')
        speak("Opening the interface, sir.")
        return
    # Weather
    if "WEATHER:" in reply:
        loc = reply.split("WEATHER:", 1)[1].strip().split("\n")[0]
        wx = get_weather(loc or "Haugesund")
        speak(wx)
        # Also speak any remaining text
        rest = "\n".join(l for l in reply.split("\n") if "WEATHER:" not in l).strip()
        if rest:
            speak(rest)
        return
    # File operations
    if "FILE:" in reply:
        cmd = reply.split("FILE:", 1)[1].strip().split("\n")[0]
        result = file_operation(cmd)
        speak(result if len(result) < 200 else result[:200] + "... and more.")
        return
    # Macro
    if "MACRO:" in reply:
        name = reply.split("MACRO:", 1)[1].strip().split("\n")[0].lower()
        result = run_macro(name)
        if result:
            speak(result if len(result) < 200 else result[:200])
        return
    # Deep research (saves to ~/jarvis_research/<topic>/)
    if "RESEARCH:" in reply:
        query = reply.split("RESEARCH:", 1)[1].strip().split("\n")[0]
        speak("Researching, sir. One moment.")
        result = deep_research(query)
        topic = re.sub(r'[^\w\s-]', '', query).strip().replace(' ', '_')[:50].lower() or "misc"
        speak(result if len(result) < 400 else result[:400])
        speak(f"Research saved to jarvis research, {topic} folder, sir.")
        return
    # System status
    if "SYSTEM_STATUS" in reply:
        status = get_system_status()
        speak(status)
        rest = "\n".join(l for l in reply.split("\n") if "SYSTEM_STATUS" not in l).strip()
        if rest:
            speak(rest)
        return
    # Full system scan
    if "SCAN" in reply and reply.strip().startswith("SCAN"):
        speak("Running full diagnostic, sir. One moment.")
        scan_results = run_full_scan()
        # Send to Gemini for a natural summary
        prompt = (f"{get_system_prompt()}\n\nYou just ran a full system scan. Here are the raw results:\n\n{scan_results}\n\n"
                  f"Give sir a brief spoken summary: what's healthy, what's broken, what could be upgraded. 4-6 sentences max. Be specific.")
        try:
            response = gemini.models.generate_content(model=GEMINI_FAST, contents=prompt)
            speak(response.text.strip() if response.text else scan_results[:400])
        except:
            speak(scan_results[:400])
        return
    # Timer
    if "TIMER:" in reply:
        parts = reply.split("TIMER:", 1)[1].strip().split("\n")[0].split(":", 1)
        secs = int(parts[0]) if parts[0].isdigit() else parse_timer(parts[0])
        label = parts[1].strip() if len(parts) > 1 else "Timer"
        if secs:
            result = set_timer(secs, label)
            speak(result)
        else:
            speak("Couldn't parse the timer duration, sir.")
        return
    # Screenshot vision
    if "SCREENSHOT:" in reply:
        question = reply.split("SCREENSHOT:", 1)[1].strip().split("\n")[0]
        speak("Scanning your screen, sir.")
        result = screenshot_and_analyze(question or "What's on my screen?")
        speak(result if len(result) < 400 else result[:400])
        return
    # Shell command execution
    if "SHELL:" in reply:
        cmd = reply.split("SHELL:", 1)[1].strip().split("\n")[0]
        # Safety: block obviously destructive commands on mishear
        dangerous = ["rm -rf /", "rm -rf ~", "rm -rf /*", "mkfs", "dd if=", "> /dev/sd", "chmod -R 777 /",
                     ":(){ :|:&", "rm -rf .", "format"]
        if any(d in cmd for d in dangerous):
            speak("Sir, that command looks destructive. I'm blocking it for safety.")
            return
        try:
            out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30,
                                cwd=os.path.expanduser("~"))
            result = (out.stdout or out.stderr or "Done.").strip()
            speak(result[:300] if len(result) > 300 else (result or "Done, sir."))
        except subprocess.TimeoutExpired:
            speak("Command timed out, sir.")
        except Exception as e:
            speak(f"Error: {e}")
        return
    # Autonomous execution — multi-step tasks (JARVIS plans + executes independently)
    if "EXEC:" in reply:
        task_desc = reply.split("EXEC:", 1)[1].strip().split("\n")[0]
        speak("On it, sir. Working autonomously.")
        import jarvis_executor
        result = jarvis_executor.autonomous_task(task_desc, gemini, GEMINI_FAST)
        speak(result[:400] if len(result) > 400 else result)
        return
    # Task management
    if "TASK:" in reply:
        for line in reply.splitlines():
            if line.startswith("TASK:"):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    action = parts[1].strip().upper()
                    name = parts[2].strip()
                    try:
                        data = json.load(open(os.path.expanduser("~/jarvis_data.json")))
                        if action == "ADD":
                            data.setdefault("tasks", []).append({"name": name, "progress": 0})
                            json.dump(data, open(os.path.expanduser("~/jarvis_data.json"), "w"), indent=2)
                            speak(f"Task added: {name}.")
                        elif action == "DONE":
                            for t in data.get("tasks", []):
                                if name.lower() in t["name"].lower():
                                    t["progress"] = 100
                                    break
                            json.dump(data, open(os.path.expanduser("~/jarvis_data.json"), "w"), indent=2)
                            speak(f"Task complete: {name}.")
                        elif action == "LIST":
                            tasks = [f"{t['name']}: {t['progress']}%" for t in data.get("tasks", [])]
                            speak(". ".join(tasks) if tasks else "No active tasks, sir.")
                        # Sync to live file for instant HUD update
                        json.dump(data.get("tasks", []), open("/tmp/jarvis_tasks_live.json", "w"))
                    except Exception as e:
                        speak(f"Task error: {e}")
        # Speak remaining text
        rest = "\n".join(l for l in reply.splitlines() if not l.startswith("TASK:")).strip()
        if rest:
            speak(rest)
        return
    for line in reply.splitlines():
        if line.startswith("REMEMBER:"):
            parts = line.split(":", 2)
            if len(parts) == 3:
                memory[parts[1].strip()] = parts[2].strip()
                save_memory(memory)
    clean = "\n".join(l for l in reply.splitlines() if not l.startswith("REMEMBER:") and not l.startswith("PLAY:") and not l.startswith("TV:") and l.strip() != "STOP_MUSIC" and l.strip() != "OPEN_HUD")
    if clean.strip():
        speak(clean.strip())

def handle_tv(cmd):
    tv_actions = {
        "power": jarvis_tv.power, "off": jarvis_tv.power, "on": jarvis_tv.power,
        "volume up": jarvis_tv.vol_up, "louder": jarvis_tv.vol_up,
        "volume down": jarvis_tv.vol_down, "quieter": jarvis_tv.vol_down,
        "mute": jarvis_tv.mute, "home": jarvis_tv.home, "back": jarvis_tv.back,
    }
    for trigger, action in tv_actions.items():
        if trigger in cmd:
            speak("Done, sir." if action() else "Couldn't reach the TV, sir.")
            return
    if "open" in cmd or "launch" in cmd:
        app = cmd.replace("open", "").replace("launch", "").strip()
        result = jarvis_tv.open_app(app)
        speak(f"Opening {result}, sir." if result else f"Couldn't open {app}, sir.")
        return
    speak("Done, sir.")

def is_shutdown(text):
    return any(w in text.strip().lower() for w in SHUTDOWN_WORDS)

def play_music(query):
    global music_playing
    stop_music()
    speak(f"Playing {query}.")
    os.system("rm -f /tmp/jarvis_music* 2>/dev/null")
    ret = os.system(f'yt-dlp -x --audio-format mp3 --force-overwrites -o "/tmp/jarvis_music.%(ext)s" "ytsearch1:{query}" --quiet --no-warnings 2>/dev/null')
    if ret != 0 or not os.path.exists("/tmp/jarvis_music.mp3"):
        speak("Couldn't find that song, sir.")
        return
    music_playing = True
    os.system("ffplay -nodisp -autoexit /tmp/jarvis_music.mp3 2>/dev/null &")

def stop_music():
    global music_playing
    os.system("pkill -f ffplay 2>/dev/null")
    os.system("pkill -f 'jarvis_ambient' 2>/dev/null")
    music_playing = False

# Suppress ALSA spam
# ALSA spam suppressed via ALSA config instead (dup2 broke systemd logging)

# Boost mic input (Chromebook built-in is very quiet)
subprocess.Popen("timeout 3 pactl set-source-volume @DEFAULT_SOURCE@ 200%", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.Popen("timeout 3 amixer -c 0 set Capture 100%", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Wake audio sink (ChromeOS suspends it after reboot until first sound)
subprocess.Popen("ffplay -nodisp -autoexit -loglevel quiet /tmp/silence.wav", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if not os.path.exists("/tmp/silence.wav"):
    import struct as _s
    _sr=44100;_d=b'\x00\x00'*int(_sr*0.1)
    _h=_s.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',36+len(_d),b'WAVE',b'fmt ',16,1,1,_sr,_sr*2,2,16,b'data',len(_d))
    with open('/tmp/silence.wav','wb') as _f:_f.write(_h+_d)
subprocess.Popen("ffplay -nodisp -autoexit -loglevel quiet /tmp/silence.wav", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Clean old TTS cache on startup (files older than 1 hour)
import glob as _glob
for _f in _glob.glob("/tmp/jarvis_*.mp3"):
    try:
        if time.time() - os.path.getmtime(_f) > 3600:
            os.remove(_f)
    except OSError:
        pass

# Boot silently — no speaking on startup
# speak("All systems operational. At your service, sir.")

# === PROACTIVE ACTION SYSTEM ===
import threading

proactive_state = {"last_check": time.time(), "session_start": time.time(), "last_break_reminder": 0, "last_prayer_reminder": ""}

def proactive_loop():
    """Background thread that monitors conditions and speaks unprompted."""
    prayer_times = {"fajr": "03:30", "dhuhr": "13:00", "asr": "17:00", "maghrib": "21:30", "isha": "23:00"}
    
    while True:
        time.sleep(60)
        
        # Quiet hours or quiet/dormant mode — no proactive speech
        if is_quiet_hours() or quiet_mode or dormant_mode:
            continue
        
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        hour = now.hour
        
        # Prayer time reminders (5 min before)
        for prayer, ptime in prayer_times.items():
            ph, pm = int(ptime.split(":")[0]), int(ptime.split(":")[1])
            # 5 minutes before prayer
            reminder_h, reminder_m = ph, pm - 5
            if reminder_m < 0:
                reminder_m += 60
                reminder_h -= 1
            reminder_str = f"{reminder_h:02d}:{reminder_m:02d}"
            if current_time_str == reminder_str and proactive_state["last_prayer_reminder"] != prayer:
                proactive_state["last_prayer_reminder"] = prayer
                speak(f"Sir, {prayer.capitalize()} prayer is in five minutes.")
                break
        
        # Session duration reminder (every 3 hours — less nagging)
        session_hours = (time.time() - proactive_state["session_start"]) / 3600
        if session_hours >= 3 and (time.time() - proactive_state["last_break_reminder"]) > 10800:
            proactive_state["last_break_reminder"] = time.time()
            speak(f"Sir, you've been at it for {int(session_hours)} hours. A stretch might serve you well.")

# Proactive system DISABLED — was making Jarvis talk constantly
# proactive_thread = threading.Thread(target=proactive_loop, daemon=True)
# proactive_thread.start()

# === NOISE CALIBRATION (3 seconds of ambient silence to set baseline) ===
print("[calibrate] Recording 3s ambient noise...", flush=True)
time.sleep(3)  # Wait for mic client to connect and stabilize
_cal_frames = []
for _ in range(int(16000 / 1024 * 3)):
    if mic_buffer:
        _cal_frames.append(mic_buffer.popleft())
    else:
        time.sleep(0.064)
if _cal_frames:
    _cal_data = b"".join(_cal_frames)
    _cal_samples = array.array('h', _cal_data)
    _cal_abs = sorted(abs(s) for s in _cal_samples)
    # Set noise floor to 50th percentile (median) of ambient noise
    noise_floor = max(40, _cal_abs[int(len(_cal_abs) * 0.5)])
    print(f"[calibrate] Noise floor set to {noise_floor} (from {len(_cal_frames)} frames)", flush=True)
else:
    noise_floor = 200  # Safe default if no mic data
    print(f"[calibrate] No mic data, using default noise_floor={noise_floor}", flush=True)
del _cal_frames, _cal_data, _cal_samples, _cal_abs

try:
    while True:
        if speaking:
            time.sleep(0.1)
            continue

        # Quiet hours — Jarvis completely stops listening
        if is_quiet_hours():
            set_state("idle")
            time.sleep(30)
            continue

        # DORMANT MODE — minimal power, only listens for wake phrase every 5s
        if dormant_mode:
            set_state("dormant")
            time.sleep(5)
            audio, talked = record(max_seconds=4, sensitivity=noise_floor * 2.0)
            if not talked or len(audio) < 16000 * 2 * 0.6:
                continue
            text = transcribe_wake(audio)
            if not text:
                continue
            text_lower = text.strip().lower()
            if any(t in text_lower for t in UNQUIET_TRIGGERS) or _is_wake(text_lower):
                dormant_mode = False
                quiet_mode = False
                set_state("listening")
                speak("Back online, sir. All systems operational.")
            continue

        set_state("listening")

        if music_playing:
            audio, talked = record(max_seconds=3, sensitivity=noise_floor * 3)
            if talked:
                text = transcribe_wake(audio)
                if text and any(w in text for w in WAKE_WORDS):
                    if "stop" in text or "pause" in text:
                        stop_music()
                        speak("Music stopped, sir.")
            continue

        # Listen for wake word (Groq Whisper — rate-limited to avoid 429)
        audio, talked = record(max_seconds=4, sensitivity=noise_floor * 2.0)
        if not talked:
            continue
        # Ignore very short audio (< 0.7s — too short to be "hey jarvis")
        if len(audio) < 16000 * 2 * 0.5:
            continue
        # Energy check — must be clearly above noise
        energy = compute_energy(audio)
        if energy < max(noise_floor * 2.5, 400):
            continue
        # Verify speech-like content: check middle chunk has moderate ZCR (filters mechanical noise)
        mid = len(audio) // 2
        chunk = audio[max(0, mid-2048):mid+2048]
        if len(chunk) >= 2048:
            zcr = zero_crossing_rate(chunk)
            if zcr < 0.01 or zcr > 0.4:
                continue  # Not speech (hum or white noise)
        # Rate limit: only call Groq every N seconds
        now = time.time()
        if now - _last_groq_wake_call < _GROQ_WAKE_COOLDOWN:
            continue
        _last_groq_wake_call = now
        text = transcribe_wake(audio)
        if not text:
            continue
        text_lower = text.strip().lower()
        wake_detected = _is_wake(text_lower)
        if not wake_detected:
            continue
        print(f"[wake]: {text}")
        log_to_hud("user", "Hey Jarvis")

        # Short acknowledgment then listen for command
        acks = ["Yes sir?", "Sir?", "Listening.", "Go ahead, sir.", "At your service."]
        speak(acks[int(time.time()) % len(acks)])
        time.sleep(0.3)
        mic_buffer.clear()
        cmd_audio, cmd_talked = record(max_seconds=12, sensitivity=noise_floor * 2.0)
        if not cmd_talked or len(cmd_audio) < 16000 * 2 * 0.6:
            # No real speech — go back to waiting silently
            print("[silence]: no response, returning to standby")
            continue
        # Extra energy check on command audio
        cmd_energy = compute_energy(cmd_audio)
        if cmd_energy < 120:
            print("[low energy]: ambient noise, returning to standby")
            continue
        wav_data = make_wav(cmd_audio)
        cmd_text_heard = cloud_transcribe(wav_data)
        if not cmd_text_heard or len(cmd_text_heard.strip()) < 2:
            print("[skip]: unclear audio, returning to standby")
            continue
        # Filter hallucinated/non-English garbage from STT
        ascii_ratio = sum(1 for c in cmd_text_heard if c.isascii()) / max(len(cmd_text_heard), 1)
        if ascii_ratio < 0.8:
            print(f"[hallucination filtered]: {cmd_text_heard}")
            continue
        stt_hallucinations = ["subscribe", "like and subscribe", "thanks for watching",
                              "thank you for watching", "please subscribe", "lala", "school",
                              "cho kênh", "hãy", "cảm ơn", "감사합니다", "구독",
                              "谢谢", "请订阅", "untertitel", "takk fyrir", "♪", "♫"]
        if any(h in cmd_text_heard.lower() for h in stt_hallucinations):
            print(f"[hallucination filtered]: {cmd_text_heard}")
            continue
        # Filter: if STT only heard the wake word back (echo), re-listen
        heard_lower = cmd_text_heard.strip().lower().rstrip(".,!?")
        if any(heard_lower == w or heard_lower == f"{w}" for w in WAKE_WORDS):
            print(f"[echo filtered]: {cmd_text_heard}")
            continue
        print(f"[heard]: {cmd_text_heard}")
        log_to_hud("user", cmd_text_heard)
        # Check for shutdown
        if is_shutdown(cmd_text_heard):
            speak("Goodbye, sir.")
            break
        # Check quiet triggers
        if any(t in cmd_text_heard.lower() for t in DORMANT_TRIGGERS):
            dormant_mode = True
            quiet_mode = True
            speak("Going dormant, sir. Say my name when you need me.")
            continue
        if any(t in cmd_text_heard.lower() for t in QUIET_TRIGGERS):
            quiet_mode = True
            speak("Going quiet, sir.")
            continue
        if any(t in cmd_text_heard.lower() for t in UNQUIET_TRIGGERS):
            quiet_mode = False
            dormant_mode = False
            speak("I'm here, sir.")
            continue
        # Route to brain
        set_state("active")
        history.append({"role": "user", "content": cmd_text_heard})
        # Stock commands
        import jarvis_stocks
        stock_reply = jarvis_stocks.handle_stock_command(cmd_text_heard)
        if stock_reply:
            print(f"[brain]: Stocks Module")
            history.append({"role": "assistant", "content": stock_reply})
            speak(stock_reply)
            continue
        if should_use_vision(cmd_text_heard):
            if any(t in cmd_text_heard.lower() for t in SCREEN_TRIGGERS):
                print("[brain]: Screenshot Vision")
                speak("Scanning your screen, sir.")
                reply = screenshot_and_analyze(cmd_text_heard)
            else:
                print("[brain]: Gemini Vision")
                reply = capture_and_analyze(cmd_text_heard)
        elif should_use_claude(cmd_text_heard):
            print("[brain]: Claude Fable 5")
            reply = ask_claude(cmd_text_heard)
        else:
            print("[brain]: Gemini 2.5 Flash")
            reply = ask_gemini_text(cmd_text_heard)
        if reply:
            history.append({"role": "assistant", "content": reply})
            process_reply(reply)
            log_session(cmd_text_heard, reply)
        else:
            speak("Apologies sir, couldn't reach the servers.")
            log_session(cmd_text_heard, "[no response - servers unreachable]")

        if len(history) > 20:
            history = history[-14:]
        save_history(history)

except KeyboardInterrupt:
    speak("Goodbye, sir.")
finally:
    set_state("idle")
    os._exit(0)
