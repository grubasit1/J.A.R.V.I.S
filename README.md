# J.A.R.V.I.S — Real-Life AI Assistant

A fully autonomous voice AI assistant built from scratch in 5 days. Multi-brain architecture, smart home control, autonomous code execution, YouTube automation, Iron Man HUD — all running on a Chromebook.

**53+ hours of development** | **6,200+ lines of code** | **47 sessions**

## Features

- 🎙 **Voice Control** — wake word detection, natural conversation, British personality
- 🧠 **Multi-Brain** — Gemini 2.5 Flash (main) + Claude Fable 5 (heavy) + Groq Whisper (STT)
- 🤖 **Autonomous Executor** — plans & executes multi-step coding tasks independently (like Cursor/Kiro)
- 📺 **Smart Home** — Samsung TV control via WebSocket (power, volume, apps)
- 📹 **YouTube Automation** — generates & uploads educational Shorts daily (3-6/day)
- 🖥 **Iron Man HUD** — Three.js fullscreen interface with 3D orb, boot sequence, data panels
- 📈 **Stock Trading** — paper trading with AI technical analysis (Alpaca)
- 🔍 **Web Search** — DuckDuckGo integration with context-aware queries
- 🔬 **Research Mode** — multi-source deep research, saved to organized folders
- 📸 **Screenshot Vision** — captures and analyzes screen content with AI
- 💾 **Persistent Memory** — conversation history survives restarts
- ⏰ **Proactive System** — prayer reminders, break reminders, sleep reminders
- 🎵 **Music** — yt-dlp powered playback with voice stop/play
- 🌤 **Weather** — Open-Meteo (free, no API key)
- 📁 **File Management** — find, read, write, move, delete, organize via voice
- ⏱ **Timers** — voice-set countdown timers
- 🔧 **Shell Access** — run any terminal command via voice

## Architecture

```
Voice → Groq Whisper (STT) → Brain Router → Gemini/Claude → edge-tts → Speaker
                                    ↓
                         Autonomous Executor (EXEC:)
                         Shell Commands (SHELL:)
                         File Operations (FILE:)
                         Research Mode (RESEARCH:)
                         TV/Music/Web/Stocks/Weather
```

### Brain Routing
| Trigger | Brain | Use Case |
|---------|-------|----------|
| Default | Gemini 2.5 Flash | Fast conversation, general tasks |
| "think hard", "analyze", "write code" | Claude Fable 5 | Deep reasoning, complex code |
| Wake word detection | Groq Whisper | Free, fast STT |
| Fallback | OpenRouter | When primary brains fail |

### Audio Pipeline
```
Mic → Energy Detection → ZCR Filter → Whisper STT → Command
                ↓ (saves API calls)
        Noise Floor Adaptation
        Bandpass Filter (removes AC hum)
        Speech vs Noise Classification
```

## Requirements

- Linux (Debian/Ubuntu-based, or ChromeOS with Crostini)
- Python 3.10+
- A microphone (USB recommended)
- Internet connection

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/ahmadibasit77/jarvis.git
cd jarvis
```

### 2. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3-pip ffmpeg flac portaudio19-dev libffi-dev
```

### 3. Install Python packages

```bash
pip3 install google-genai groq edge-tts pyaudio duckduckgo-search requests yt-dlp
pip3 install anthropic  # Optional: for Claude brain
pip3 install alpaca-trade-api  # Optional: for stock trading
```

### 4. Set API keys

Create a `.env` file or export directly:

```bash
export GEMINI_API_KEY="your_google_ai_studio_key"    # Required (free at aistudio.google.com)
export GROQ_API_KEY="your_groq_key"                  # Required (free at console.groq.com)
export OPENROUTER_API_KEY="your_key"                 # Optional fallback
export PEXELS_API_KEY="your_key"                     # Optional: for YouTube Shorts images
```

### 5. Run JARVIS

```bash
python3 jarvis.py
```

Say "Hey Jarvis" to wake him up, then speak your command.

### 6. Run the HUD (optional)

```bash
python3 jarvis_server.py
```

Open `http://localhost:8888` in your browser for the Iron Man interface.

## Running as Services (systemd)

For always-on operation, set up user services:

```bash
# Create service files in ~/.config/systemd/user/

# Main voice AI
cat > ~/.config/systemd/user/jarvis.service << 'EOF'
[Unit]
Description=J.A.R.V.I.S Voice AI

[Service]
ExecStart=/usr/bin/python3 -u %h/jarvis.py
Restart=on-failure
RestartSec=5
Environment=GEMINI_API_KEY=your_key
Environment=GROQ_API_KEY=your_key

[Install]
WantedBy=default.target
EOF

# HUD web server
cat > ~/.config/systemd/user/jarvis-server.service << 'EOF'
[Unit]
Description=J.A.R.V.I.S HUD Web Server

[Service]
ExecStart=/usr/bin/python3 %h/jarvis_server.py
Restart=on-failure

[Install]
WantedBy=default.target
EOF

# Enable & start
systemctl --user daemon-reload
systemctl --user enable jarvis.service jarvis-server.service
systemctl --user start jarvis.service jarvis-server.service
```

## Services Overview

| Service | Purpose |
|---------|---------|
| `jarvis.service` | Main voice AI loop |
| `jarvis-server.service` | HUD web server (port 8888) |
| `jarvis-watchdog.service` | Health monitor + YouTube scheduler |
| `jarvis-autonomy.service` | Proactive brain (reminders, suggestions) |
| `jarvis-mic.service` | Network mic streaming |
| `jarvis-tunnel.service` | Cloudflare tunnel (public access) |

## How to Talk to JARVIS

JARVIS uses **omnidirectional listening** — you don't need perfect sentences or to be right next to the mic. Short fragments work.

### Wake Word
Say **"Jarvis"** (or "Hey Jarvis") from anywhere in the room. He'll respond with "Sir?" or "Listening." then wait for your command.

**What works:**
- "Jarvis, lights off"
- "Hey Jarvis"
- "Yo Jarvis stop"
- "Jarvis... what time is it"
- Just "Jarvis" (he'll ask what you need)

**What won't trigger him:**
- Random background speech without "Jarvis"
- Music/TV audio (filtered by ZCR + energy detection)
- Single syllable noises

### Command Style
After wake, speak naturally — fragments are fine:
- ✅ "turn off the TV" 
- ✅ "TV off"
- ✅ "weather"
- ✅ "play phonk"
- ✅ "install flask then write me an API"
- ❌ Silence (he'll go back to standby after 1s)

### Full System Access
JARVIS has **complete control** over the machine. Everything you can do in a terminal, he can do by voice:

| Prefix | What it does | Example |
|--------|-------------|---------|
| `SHELL:` | Run any terminal command | "Run htop" → `SHELL:htop` |
| `EXEC:` | Multi-step autonomous task | "Write a Flask API with auth" → plans, codes, tests, deploys |
| `FILE:` | Filesystem operations | "List my files" → `FILE:list:~` |

**System commands you can say:**
```
"Install numpy"              → SHELL:pip3 install numpy
"Update my system"           → SHELL:sudo apt update && sudo apt upgrade -y
"Kill chrome"                → SHELL:pkill chromium  
"Check disk space"           → SHELL:df -h
"Restart the server"         → SHELL:systemctl --user restart jarvis-server
"Git push"                   → SHELL:cd ~/jarvis && git add -A && git push
"Find all python files"      → FILE:find:.py
"Create a folder projects"   → FILE:mkdir:projects
"Read my config"             → FILE:read:.bashrc
"Write hello to test.txt"    → FILE:write:test.txt|hello world
"Delete temp files"          → FILE:delete:/tmp/jarvis_*
"Organize my downloads"      → FILE:organize:Downloads
```

**Autonomous execution (EXEC:)** — for complex tasks:
```
"Write me a web scraper for news"
"Create a backup script and schedule it"  
"Set up a Flask app with SQLite"
"Fix the bug in jarvis_tv.py"
```
JARVIS will: plan steps → write code → run it → check for errors → fix them → report back. Up to 20 steps, self-correcting.

## Voice Commands

| Command | What it does |
|---------|-------------|
| "Hey Jarvis" | Wake word |
| "Play [song]" | Play music via yt-dlp |
| "Stop music" | Stop playback |
| "Turn on/off the TV" | Samsung TV power |
| "Open Netflix/YouTube/Spotify" | Launch TV apps |
| "What's the weather?" | Current weather |
| "Search for [query]" | Web search |
| "Research [topic]" | Deep multi-source research |
| "Write me a script that..." | Autonomous code execution |
| "Price of TSLA" | Stock price lookup |
| "Buy 5 shares of AAPL" | Paper trade |
| "My portfolio" | Show holdings |
| "Set timer for 10 minutes" | Countdown timer |
| "Shut down" | Exit JARVIS |
| "Go dormant" | Low-power mode |

## Project Structure

```
jarvis.py              — Main voice loop (listen → think → speak)
jarvis_executor.py     — Autonomous task execution (Kiro-level)
jarvis_server.py       — HUD web server + chat API
jarvis_hud.html        — Iron Man HUD (Three.js 3D interface)
jarvis_tv.py           — Samsung TV WebSocket control
jarvis_stocks.py       — Stock trading module (Alpaca)
jarvis_daily.py        — YouTube Shorts generation + scheduling
jarvis_shorts.py       — Short video creation pipeline
jarvis_upload.py       — YouTube API upload with OAuth
jarvis_watchdog.py     — Service health + auto-restart
jarvis_autonomy.py     — Proactive brain (reminders, suggestions)
jarvis_api.py          — API bridge for HUD ↔ JARVIS state
jarvis_hud.py          — HUD control utilities
jarvis_listen.py       — Original speech recognition module
jarvis_speak.sh        — Original TTS script (espeak-ng)
make_short.py          — Short video assembly
real_edit_short.py     — Enhanced video editing (transitions, effects)
run_short.py           — Short execution wrapper
```

## Built by

**Basit Ahmadi**, 15, Norway. Started June 13, 2026.

© 2026 Basit Ahmadi. All rights reserved.
Not licensed for commercial use or redistribution.
