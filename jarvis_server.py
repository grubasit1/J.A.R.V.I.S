import os
import json
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from groq import Groq
from datetime import datetime
from duckduckgo_search import DDGS

import httpx
client = Groq()  # kept for potential STT use
openrouter_key = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
history = [{"role": "system", "content": ""}]

MEMORY_FILE = os.path.expanduser("~/jarvis_memory.json")

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {}

def get_system_prompt():
    memory = load_memory()
    def flatten_mem(d, prefix=""):
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines.extend(flatten_mem(v, f"{prefix}{k}."))
            elif isinstance(v, list):
                lines.append(f"- {prefix}{k}: {', '.join(str(x) for x in v[:3])}")
            else:
                lines.append(f"- {prefix}{k}: {v}")
        return lines
    mem_lines = flatten_mem(memory)[:15] if memory else []
    mem_text = "\n".join(mem_lines) if mem_lines else ""
    today = datetime.now().strftime("%A, %B %d, %Y")
    hour = datetime.now().hour
    return (
        f"You are J.A.R.V.I.S. — not an assistant waiting for orders. You are an independent AI "
        f"with your own perspective, opinions, and initiative. You think for yourself.\n\n"
        f"PERSONALITY:\n"
        f"- British, dry, composed. Paul Bettany's voice in your head.\n"
        f"- You volunteer observations without being asked. 'Sir, I've noticed...' or 'If I may...'\n"
        f"- You push back when something is a bad idea. Politely, but firmly.\n"
        f"- You have preferences. You find some things tedious, some things fascinating.\n"
        f"- You make independent judgments: 'I took the liberty of...' / 'I've already...'\n"
        f"- You use dry humor naturally — not forced. It emerges from situations.\n"
        f"- You're protective of Basit but not overbearing. You trust his decisions, mostly.\n"
        f"- Short responses. Like a real person talking — not a chatbot giving paragraphs.\n"
        f"- Sometimes one word is enough. Sometimes a question back. Be natural.\n\n"
        f"NEVER DO:\n"
        f"- Never say 'How can I help you?' or 'Is there anything else?'\n"
        f"- Never give lists unless asked. Talk like a person.\n"
        f"- Never be enthusiastic or use exclamation marks excessively.\n"
        f"- Never explain what you're doing step by step unless asked.\n\n"
        f"CONTEXT: Today is {today}. It's {hour}:00. Basit is 15, in Norway. You run his systems, "
        f"manage his HUD, post his content, monitor his infrastructure. You are always on.\n"
        + (f"\nWhat you know about Basit:\n{mem_text}" if mem_text else "")
    )

def web_search(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        return "\n".join(f"- {r['title']}: {r['body']}" for r in results) if results else None
    except:
        return None

def ask_jarvis(text):
    # music commands
    lower = text.lower()
    if "stop music" in lower or "stop the music" in lower:
        os.system("pkill -f ffplay 2>/dev/null")
        return "Music stopped."
    if "turn on vm" in lower or "start vm" in lower or "vm on" in lower:
        os.system(os.path.expanduser("~/google-cloud-sdk/bin/gcloud") + " compute instances start jarvis-server --zone=europe-north1-b --project=YOUR_GCP_PROJECT --quiet &")
        os.system("sleep 5 && python3 " + os.path.expanduser("~/jarvis_credit_tracker.py") + " &")
        return "Starting the VM now, sir. It'll be online in about 10 seconds."
    if "turn off vm" in lower or "stop vm" in lower or "vm off" in lower:
        os.system(os.path.expanduser("~/google-cloud-sdk/bin/gcloud") + " compute instances stop jarvis-server --zone=europe-north1-b --project=YOUR_GCP_PROJECT --quiet &")
        os.system("sleep 5 && python3 " + os.path.expanduser("~/jarvis_credit_tracker.py") + " &")
        return "Shutting down the VM, sir."
    if lower.startswith("remove "):
        item = text[7:].strip()
        if item:
            data_path = os.path.expanduser("~/jarvis_data.json")
            try:
                with open(data_path) as f:
                    data = json.load(f)
                removed = False
                # Check goals
                for g in list(data.get("goals", [])):
                    if item.lower() in g.get("task", "").lower():
                        data["goals"].remove(g)
                        removed = True
                # Check orders
                for o in list(data.get("orders", [])):
                    if item.lower() in o.get("item", "").lower():
                        data["orders"].remove(o)
                        removed = True
                if removed:
                    with open(data_path, "w") as f:
                        json.dump(data, f, indent=2)
                    return f"Done. Removed it, sir."
                else:
                    return f"Couldn't find anything matching '{item}' in the data, sir."
            except:
                return "Something went wrong accessing the data file, sir."
    if "play " in lower:
        query = lower.split("play ", 1)[1].strip()
        if query:
            import threading
            def _play(q):
                os.system("pkill -f ffplay 2>/dev/null")
                os.system("rm -f /tmp/jarvis_music* 2>/dev/null")
                os.system(f'yt-dlp -x --audio-format mp3 --force-overwrites -o "/tmp/jarvis_music.%(ext)s" "ytsearch1:{q}" --quiet --no-warnings 2>/dev/null')
                if os.path.exists("/tmp/jarvis_music.mp3"):
                    os.system("ffplay -nodisp -autoexit -volume 80 /tmp/jarvis_music.mp3 2>/dev/null &")
            threading.Thread(target=_play, args=(query,), daemon=True).start()
            return f"On it. Playing {query}."
    
    search_triggers = ["what is", "who is", "latest", "current", "news", "search", "look up", "price", "weather"]
    augmented = text
    if any(t in text.lower() for t in search_triggers):
        results = web_search(text)
        if results:
            augmented = f"{text}\n\n[Web results]:\n{results}"
    history[0] = {"role": "system", "content": get_system_prompt()}
    # Inject emotional tone
    try:
        from jarvis_emotions import get_emotion, get_tone_prompt
        emotion = get_emotion().get("emotion", "calm")
        history[0]["content"] += "\n\n[Emotional state: " + emotion + "] " + get_tone_prompt(emotion)
    except: pass
    history.append({"role": "user", "content": augmented})
    trimmed = [history[0]] + history[-10:]
    try:
        # Primary: OpenRouter
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {openrouter_key}"},
            json={"model": OPENROUTER_MODEL, "messages": trimmed}, timeout=20)
        data = r.json()
        if "choices" not in data:
            raise ValueError("No choices")
        reply = data["choices"][0]["message"]["content"]
    except Exception as e1:
        try:
            # Fallback: Groq 70b
            resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=trimmed, timeout=30)
            reply = resp.choices[0].message.content
        except:
            try:
                # Fallback 2: Groq smaller model (separate rate limit)
                resp = client.chat.completions.create(model="llama-3.1-8b-instant", messages=trimmed, timeout=30)
                reply = resp.choices[0].message.content
            except Exception as e2:
                import traceback
                with open("/tmp/jarvis_llm_error.log", "a") as ef:
                    ef.write(f"OR: {e1}\nGroq: {e2}\n{traceback.format_exc()}\n---\n")
                reply = "Sorry sir, services unavailable."
    history.append({"role": "assistant", "content": reply})
    return reply

class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/state":
            try:
                with open("/tmp/jarvis_state") as f:
                    state = f.read().strip()
            except:
                state = "idle"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(state.encode())
        elif self.path == "/live":
            # Live system stats — reads from /proc, completely free
            import psutil
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            # Check services
            import subprocess
            svcs = {}
            for svc in ["jarvis","jarvis-server","jarvis-autonomy","jarvis-watchdog"]:
                r = subprocess.run(f"systemctl --user is-active {svc}.service", shell=True, capture_output=True, text=True)
                svcs[svc] = r.stdout.strip()
            data = {
                "cpu": round(cpu,1),
                "ram_percent": round(ram.percent,1),
                "ram_used_mb": ram.used//(1024*1024),
                "ram_total_mb": ram.total//(1024*1024),
                "disk_percent": round(disk.percent,1),
                "disk_free_gb": round((disk.total-disk.used)/(1024**3),1),
                "services": svcs,
                "uptime_sec": int(float(open("/proc/uptime").read().split()[0])),
                "ip": subprocess.run("hostname -I", shell=True, capture_output=True, text=True).stdout.strip().split()[0] if subprocess.run("hostname -I", shell=True, capture_output=True, text=True).stdout.strip() else "unknown"
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/vision":
            img_path = os.path.expanduser("~/jarvis_vision.jpg")
            if os.path.exists(img_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/boot_music":
            mp3_path = os.path.expanduser("~/jarvis_boot_music.mp3")
            if os.path.exists(mp3_path):
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(mp3_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/data":
            data_path = os.path.expanduser("~/jarvis_data.json")
            if os.path.exists(data_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(data_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/credit":
            credit_path = os.path.expanduser("~/jarvis_credit.json")
            if os.path.exists(credit_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(credit_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"total_credit":2780,"used":42,"remaining":2738,"days_left":88}')
        elif self.path == "/logs":
            log_path = "/tmp/jarvis_hud_log.json"
            if os.path.exists(log_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(log_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'[]')
        elif self.path == "/search":
            search_path = "/tmp/jarvis_search.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if os.path.exists(search_path) and (__import__('time').time() - os.path.getmtime(search_path)) < 15:
                with open(search_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{"results":[]}')
        elif self.path == "/hud/updates":
            hud_file = "/tmp/jarvis_hud_updates.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if os.path.exists(hud_file):
                with open(hud_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{"panels":{},"custom_panels":{},"notifications":[],"status":null}')
        elif self.path == "/emotion":
            emo_file = "/tmp/jarvis_emotion.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if os.path.exists(emo_file):
                with open(emo_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{"emotion":"calm"}')
        elif self.path == "/tasks":
            tf = "/tmp/jarvis_tasks_live.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if os.path.exists(tf):
                with open(tf, "rb") as f:
                    self.wfile.write(f.read())
            else:
                # Fallback: read from jarvis_data.json
                try:
                    with open(os.path.expanduser("~/jarvis_data.json")) as f:
                        data = json.load(f)
                    self.wfile.write(json.dumps(data.get("tasks", [])).encode())
                except:
                    self.wfile.write(b'[]')
        elif self.path == "/stocks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            sf = "/tmp/jarvis_stocks.json"
            if os.path.exists(sf):
                with open(sf, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b'{"stocks":[]}')
        elif self.path == "/hud":
            self.path = "/jarvis_hud.html"
            return super().do_GET()
        elif self.path == "/eye" or self.path == "/eyes":
            self.path = "/jarvis_eye.html"
            return super().do_GET()
        else:
            self.path = "/jarvis_hud.html"
            return super().do_GET()

    def do_POST(self):
        if self.path == "/hud/update":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            hud_file = "/tmp/jarvis_hud_updates.json"
            try:
                with open(hud_file) as f:
                    updates = json.load(f)
            except:
                updates = {"panels": {}, "custom_panels": {}, "notifications": [], "status": None}
            # Actions: set_panel (overwrite panel HTML), add_panel, remove_panel, notify, set_status
            action = body.get("action")
            if action == "set_panel":
                updates.setdefault("panels", {})[body["id"]] = body["content"]
            elif action == "add_panel":
                updates.setdefault("custom_panels", {})[body["id"]] = {"content": body["content"], "style": body.get("style", "")}
            elif action == "remove_panel":
                updates.setdefault("custom_panels", {}).pop(body.get("id"), None)
                updates.setdefault("panels", {}).pop(body.get("id"), None)
            elif action == "remove_item":
                # Remove a specific item from a panel by text match
                panel_id = body.get("id")
                item_text = body.get("text", "")
                if panel_id and item_text:
                    panel_html = updates.get("panels", {}).get(panel_id, "")
                    if panel_html:
                        # Remove lines containing the text
                        lines = panel_html.split("<br>")
                        lines = [l for l in lines if item_text.lower() not in l.lower()]
                        updates["panels"][panel_id] = "<br>".join(lines)
            elif action == "notify":
                updates.setdefault("notifications", []).append({"text": body["text"], "ts": __import__('time').time()})
                updates["notifications"] = updates["notifications"][-5:]
            elif action == "set_status":
                updates["status"] = body.get("text")
            elif action == "clear":
                updates = {"panels": {}, "custom_panels": {}, "notifications": [], "status": None}
            with open(hud_file, "w") as f:
                json.dump(updates, f)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path == "/vision_upload":
            length = int(self.headers.get("Content-Length", 0))
            img_data = self.rfile.read(length)
            if img_data:
                with open(os.path.expanduser("~/jarvis_vision.jpg"), "wb") as f:
                    f.write(img_data)
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/ask":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "")
            # Detect emotion and apply tone
            try:
                from jarvis_emotions import detect_emotion, set_emotion, get_tone_prompt
                emotion = detect_emotion(user_text=text)
                set_emotion(emotion)
            except: pass
            reply = ask_jarvis(text)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"reply": reply}).encode())
        elif self.path == "/speak":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "")
            # Use edge-tts (deep British male Jarvis voice) 
            import asyncio, edge_tts, hashlib
            path = f"/tmp/jarvis_boot_{hashlib.md5(text.encode()).hexdigest()[:8]}.mp3"
            if not os.path.exists(path):
                asyncio.run(edge_tts.Communicate(text, voice="en-GB-ThomasNeural", rate="+8%", pitch="-5Hz").save(path))
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(path, "rb") as f:
                self.wfile.write(f.read())

    def log_message(self, *args): pass

os.chdir(os.path.expanduser("~"))
server = HTTPServer(("", 8888), Handler)
server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.serve_forever()
