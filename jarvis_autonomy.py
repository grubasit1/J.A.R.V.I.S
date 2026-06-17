#!/usr/bin/env python3
"""Jarvis Autonomous Brain — thinks, plans, and acts independently.
Runs as background daemon alongside jarvis.py (voice) and watchdog.
This is what makes Jarvis INDEPENDENT — not waiting for commands, but deciding what to do.
"""
import os, sys, json, time, random, subprocess, threading
from datetime import datetime, timedelta

from google import genai
from google.genai import types

LOG = os.path.expanduser("~/jarvis_autonomy.log")
STATE_FILE = os.path.expanduser("~/jarvis_autonomy_state.json")
DATA_FILE = os.path.expanduser("~/jarvis_data.json")
DAILY_LOG = os.path.expanduser("~/jarvis_daily.log")

# Gemini for autonomous thinking (free API key — no GCP billing needed)
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
gemini = genai.Client(api_key=_gemini_key) if _gemini_key else None
MODEL = 'gemini-2.5-flash'

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {
            "last_think": 0,
            "last_self_check": 0,
            "last_shorts_review": 0,
            "tasks_completed_today": [],
            "decisions_made": [],
            "issues_detected": [],
            "date": datetime.now().strftime("%Y-%m-%d")
        }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_data():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def think(prompt):
    """Ask Gemini to think/decide something autonomously."""
    try:
        r = gemini.models.generate_content(model=MODEL, contents=prompt)
        return r.text.strip() if r.text else None
    except Exception as e:
        log(f"❌ Think error: {e}")
        return None

# ═══════════════════════════════════════════════════════════
# AUTONOMOUS ACTIONS — things Jarvis does on his own
# ═══════════════════════════════════════════════════════════

def check_system_health():
    """Self-diagnose: is jarvis.py running? Is voice working? Any crashes?"""
    issues = []
    
    # Check jarvis.py
    r = subprocess.run(["pgrep", "-f", "jarvis.py"], capture_output=True)
    if r.returncode != 0:
        issues.append("jarvis.py not running")
        subprocess.run(["systemctl", "--user", "restart", "jarvis.service"], capture_output=True)
        log("🔧 Auto-restarted jarvis.service")

    # Check server
    r = subprocess.run(["pgrep", "-f", "jarvis_server.py"], capture_output=True)
    if r.returncode != 0:
        issues.append("jarvis_server.py not running")
        subprocess.run(["systemctl", "--user", "restart", "jarvis-server.service"], capture_output=True)
        log("🔧 Auto-restarted jarvis-server.service")

    # Vision system DISABLED — no camera available on Chromebook
    # r = subprocess.run(["pgrep", "-f", "jarvis_vision.py"], capture_output=True)
    # if r.returncode != 0:
    #     subprocess.run(["systemctl", "--user", "restart", "jarvis-vision.service"], capture_output=True)

    # Check vision state — is camera actually working?
    vision_state_file = "/tmp/jarvis_vision_state.json"
    try:
        with open(vision_state_file) as f:
            vs = json.load(f)
        if vs.get("status") == "NO_CAMERA":
            issues.append("Camera not shared from ChromeOS")
    except:
        pass

    # Check disk space
    st = os.statvfs(os.path.expanduser("~"))
    free_gb = (st.f_bavail * st.f_frsize) / (1024**3)
    if free_gb < 1:
        issues.append(f"Low disk: {free_gb:.1f}GB free")
        os.system("rm -rf ~/jarvis_shorts/temp/* 2>/dev/null")
        os.system("rm -f /tmp/jarvis_music* /tmp/jarvis_*.mp3 2>/dev/null")
        log("🧹 Auto-cleaned temp files")

    return issues

def review_shorts_quality():
    """Check if today's shorts were actually posted and have decent quality."""
    shorts_dir = os.path.expanduser("~/jarvis_shorts")
    today = datetime.now().strftime("%Y%m%d")
    
    today_shorts = [f for f in os.listdir(shorts_dir) 
                    if f.startswith(f"short_{today}") and f.endswith(".mp4")]
    today_jsons = [f for f in os.listdir(shorts_dir)
                   if f.startswith(f"short_{today}") and f.endswith(".json")]
    
    report = {
        "date": today,
        "shorts_generated": len(today_shorts),
        "metadata_files": len(today_jsons),
        "issues": []
    }
    
    # Check each short's size (too small = probably failed)
    for mp4 in today_shorts:
        path = os.path.join(shorts_dir, mp4)
        size_mb = os.path.getsize(path) / (1024*1024)
        if size_mb < 0.1:
            report["issues"].append(f"{mp4} too small ({size_mb:.2f}MB) — likely failed")
    
    # If no shorts today yet and it's past 12pm, flag it
    if len(today_shorts) == 0 and datetime.now().hour >= 12:
        report["issues"].append("No shorts generated today — watchdog may be broken")
        # Force a post now
        log("⚠️ No shorts today! Force-triggering jarvis_daily.py")
        subprocess.Popen(
            ["python3", os.path.expanduser("~/jarvis_daily.py"), "--now"],
            stdout=open(DAILY_LOG, "a"), stderr=subprocess.STDOUT,
            start_new_session=True, cwd=os.path.expanduser("~"))
    
    return report

def autonomous_decision():
    """Local logic-based decisions — NO API calls, saves credits."""
    state = load_state()
    data = load_data()
    now = datetime.now()
    
    # Reset state if new day
    if state.get("date") != now.strftime("%Y-%m-%d"):
        state["tasks_completed_today"] = []
        state["decisions_made"] = []
        state["issues_detected"] = []
        state["date"] = now.strftime("%Y-%m-%d")
    
    # Simple local rules instead of expensive Gemini calls
    hour = now.hour
    
    # Health check every 30 min
    if "health_check" not in state["tasks_completed_today"] or time.time() - state.get("last_health", 0) > 1800:
        issues = check_system_health()
        if issues:
            state["issues_detected"].extend(issues)
            log(f"⚠️ Issues found: {issues}")
        else:
            log("✅ All systems healthy")
        state["tasks_completed_today"].append("health_check")
        state["last_health"] = time.time()
    
    # BACKUP POSTING SYSTEM — catch up on missed posts
    elif hour >= 9 and hour <= 22 and time.time() - state.get("last_post_attempt", 0) > 3600:
        shorts_dir = os.path.expanduser("~/jarvis_shorts")
        today = now.strftime("%Y%m%d")
        # Check SUCCESSFUL posts (have both .mp4 > 100KB and appear in log as POSTED)
        try:
            with open(DAILY_LOG) as f:
                today_log = [l for l in f.readlines() if today[:4]+"-"+today[4:6]+"-"+today[6:8] in l]
            posted_today = sum(1 for l in today_log if "POSTED!" in l)
        except:
            posted_today = 0
        
        # Target: at least 3 posts per day between 9AM-10PM
        target_by_now = max(1, min(3, (hour - 9) // 4 + 1))  # 1 by 9AM, 2 by 1PM, 3 by 5PM
        
        if posted_today < target_by_now:
            missed = target_by_now - posted_today
            log(f"📹 BACKUP: {posted_today}/{target_by_now} posts today — catching up {missed} now")
            env = {**os.environ}
            subprocess.Popen(
                ["nice", "-n", "10", "python3", os.path.expanduser("~/jarvis_influencer.py"), "--now"],
                stdout=open(DAILY_LOG, "a"), stderr=subprocess.STDOUT,
                start_new_session=True, cwd=os.path.expanduser("~"), env=env)
            state["last_post_attempt"] = time.time()
            state["tasks_completed_today"].append(f"backup_post_{posted_today+1}")
    
    # Force post if none today and it's afternoon (existing logic kept as extra safety)
    elif hour >= 14 and "force_post" not in state["tasks_completed_today"]:
        shorts_dir = os.path.expanduser("~/jarvis_shorts")
        today = now.strftime("%Y%m%d")
        today_shorts = [f for f in os.listdir(shorts_dir) if f.startswith(f"short_{today}") and f.endswith(".mp4")]
        if len(today_shorts) == 0:
            log("📹 No shorts today — posting one")
            env = {**os.environ}
            subprocess.Popen(
                ["nice", "-n", "10", "python3", os.path.expanduser("~/jarvis_influencer.py"), "--now"],
                stdout=open(DAILY_LOG, "a"), stderr=subprocess.STDOUT,
                start_new_session=True, cwd=os.path.expanduser("~"), env=env)
            state["tasks_completed_today"].append("force_post")
            state["last_post_attempt"] = time.time()
    
    # Clean temp files once a day at 4 AM
    elif hour == 4 and "clean" not in state["tasks_completed_today"]:
        os.system("rm -rf ~/jarvis_shorts/temp/* ~/jarvis_shorts/temp_edit/* 2>/dev/null")
        os.system("rm -f /tmp/jarvis_music* /tmp/short_*TEMP* 2>/dev/null")
        os.system("rm -f ~/short_*TEMP*.mp4 2>/dev/null")
        log("🧹 System cleaned")
        state["tasks_completed_today"].append("clean")
    
    save_state(state)

def self_improvement_check():
    """Check logs for errors — local only, no API calls."""
    try:
        with open(DAILY_LOG) as f:
            recent = f.read()[-3000:]
    except:
        return
    
    errors = [l for l in recent.splitlines() if "error" in l.lower() or "traceback" in l.lower() or "failed" in l.lower()]
    if errors:
        log(f"🔍 {len(errors)} errors in recent logs. Latest: {errors[-1][:150]}")

# ═══════════════════════════════════════════════════════════
# MAIN LOOP — runs every 10 minutes
# ═══════════════════════════════════════════════════════════

def main():
    log("🧠 Jarvis Autonomy Brain ONLINE")
    
    # Immediate health check on start
    issues = check_system_health()
    if issues:
        log(f"⚠️ Startup issues: {issues}")
    else:
        log("✅ All systems nominal")
    
    cycle = 0
    while True:
        try:
            cycle += 1
            
            # Every 10 min: autonomous decision
            autonomous_decision()
            
            # Every 30 min: health check
            if cycle % 3 == 0:
                issues = check_system_health()
                if issues:
                    log(f"⚠️ Health issues: {issues}")
            
            # Every 30 min during market hours (14:30-21:00 UTC = 9:30-4:00 ET): scan stocks
            if cycle % 3 == 0:
                hour = datetime.now().hour
                if 14 <= hour <= 22:  # Market hours in CEST
                    try:
                        import jarvis_stocks
                        jarvis_stocks.get_multi_prices()  # Update HUD ticker
                        if cycle % 6 == 0:  # Full scan every hour
                            scan = jarvis_stocks.full_market_scan()
                            picks = scan.get("top_picks", [])
                            if picks:
                                log(f"📈 MARKET SCAN: {picks[0]}")
                    except Exception as e:
                        log(f"⚠️ Stock scan error: {e}")
            
            # Every hour: self-improvement analysis
            if cycle % 6 == 0:
                self_improvement_check()
            
            # Every 2 hours: shorts quality review
            if cycle % 12 == 0:
                report = review_shorts_quality()
                log(f"📊 Shorts report: {report['shorts_generated']} generated, {len(report['issues'])} issues")
            
        except Exception as e:
            log(f"❌ Loop error: {e}")
        
        # Sleep 10 minutes between cycles
        time.sleep(600)

if __name__ == "__main__":
    # Prevent duplicate instances
    pidfile = "/tmp/jarvis_autonomy.pid"
    if os.path.exists(pidfile):
        try:
            old_pid = int(open(pidfile).read().strip())
            os.kill(old_pid, 0)
            log("Already running, exiting")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
    main()
