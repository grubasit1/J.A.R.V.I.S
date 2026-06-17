#!/usr/bin/env python3
"""Jarvis Watchdog — keeps all Jarvis systems alive and handles autonomous tasks.
Runs as background daemon. Auto-restarts crashed services.
"""
import os, sys, time, subprocess, json
from datetime import datetime

SERVICES = {
    # systemd manages these now — watchdog only monitors and logs
    "jarvis.py": "systemctl --user restart jarvis.service",
    "jarvis_server.py": "systemctl --user restart jarvis-server.service",
    "jarvis_autonomy.py": "systemctl --user restart jarvis-autonomy.service",
}
STOP_FLAG = "/tmp/jarvis_stopped"  # If this file exists, don't restart jarvis.py
CHECK_INTERVAL = 30  # seconds
LOG = os.path.expanduser("~/jarvis_watchdog.log")

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")

def is_running(name):
    r = subprocess.run(["pgrep", "-f", name], capture_output=True)
    return r.returncode == 0

def check_server_health():
    """Hit /health endpoint — if server is up but stuck, restart it."""
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:8888/health", timeout=5)
        return r.read() == b"ok"
    except:
        return False

def start_service(name, cmd):
    if "jarvis.py" in name and os.path.exists(STOP_FLAG):
        return
    log(f"🔄 Restarting {name}")
    os.system(cmd)

import random

# Generate random posting times for today (3-6 posts spread naturally between 9AM-11PM)
SCHEDULE_FILE = "/tmp/jarvis_post_schedule.json"

def get_todays_schedule():
    """Generate or load today's random posting schedule. Always 3 posts."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(SCHEDULE_FILE) as f:
            sched = json.load(f)
        if sched.get("date") == today:
            return sched
    except:
        pass
    # Generate new random schedule for today — always 3 posts
    hours = sorted(random.sample(range(9, 23), 3))
    times = [f"{h}:{random.randint(0,59):02d}" for h in hours]
    sched = {"date": today, "times": times, "posted": []}
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(sched, f)
    log(f"📅 Today's post schedule: {times}")
    return sched

def check_daily_posted():
    """Post at random natural times throughout the day. Runs on VM to avoid OOM on Chromebook."""
    now = datetime.now()
    if now.hour < 9:
        return
    if is_running("jarvis_daily.py"):
        return
    sched = get_todays_schedule()
    current = now.strftime("%H:%M")
    for t in sched["times"]:
        if t in sched["posted"]:
            continue
        # Post if we're past the scheduled time (no limit — always catch up)
        sched_h, sched_m = int(t.split(":")[0]), int(t.split(":")[1])
        diff_min = (now.hour * 60 + now.minute) - (sched_h * 60 + sched_m)
        if diff_min >= 0:
            log(f"📹 Posting short (scheduled {t}, now {current})")
            sched["posted"].append(t)
            with open(SCHEDULE_FILE, "w") as f:
                json.dump(sched, f)
            # Run locally (GCP VM is offline)
            subprocess.Popen(
                ["python3", os.path.expanduser("~/jarvis_daily.py"), "--now"],
                stdout=open(os.path.expanduser("~/jarvis_daily.log"), "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True, cwd=os.path.expanduser("~"))
            return  # Only post 1 at a time, next check will get the next one

def main():
    log("🟢 Jarvis Watchdog started")
    last_post_check = 0
    last_credit_check = 0
    while True:
        for name, cmd in SERVICES.items():
            if not is_running(name):
                start_service(name, cmd)
        # HTTP health check — catches stuck server (process alive but not responding)
        if is_running("jarvis_server.py") and not check_server_health():
            log("⚠️ Server not responding to /health — restarting")
            os.system("systemctl --user restart jarvis-server.service")
        # Check posting every 5 minutes
        if time.time() - last_post_check > 300:
            check_daily_posted()
            last_post_check = time.time()
        # Update credit tracker every hour
        if time.time() - last_credit_check > 3600:
            try:
                subprocess.run(["python3", os.path.expanduser("~/jarvis_credit.py")],
                               capture_output=True, timeout=30)
            except: pass
            last_credit_check = time.time()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    pidfile = "/tmp/jarvis_watchdog.pid"
    # Check if already running
    if os.path.exists(pidfile):
        try:
            old_pid = int(open(pidfile).read().strip())
            os.kill(old_pid, 0)  # Check if alive
            sys.exit(0)  # Already running
        except (ProcessLookupError, ValueError):
            pass  # Dead pid, take over
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
    main()
