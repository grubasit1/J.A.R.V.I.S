#!/usr/bin/env python3
"""Jarvis Vision System — persistent eyes that watch and understand.
Captures frames periodically, analyzes changes, reports to HUD.
When camera unavailable, retries every 60s.
"""
import os, cv2, json, time, base64, threading
from datetime import datetime
from google import genai
from google.genai import types

FRAME_PATH = os.path.expanduser("~/jarvis_vision.jpg")
VISION_STATE = "/tmp/jarvis_vision_state.json"
INTERVAL_IDLE = 10       # seconds between frames when idle
INTERVAL_ACTIVE = 3      # seconds between frames when someone talking
LOG = os.path.expanduser("~/jarvis_vision.log")

gemini = genai.Client(vertexai=True, project='YOUR_GCP_PROJECT_ID', location='global')
MODEL = 'gemini-2.5-flash'

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)

def save_state(state):
    with open(VISION_STATE, "w") as f:
        json.dump(state, f)

def try_open_camera():
    """Try to open camera. Chromebook may not always share it."""
    for idx in range(3):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                return cap
            cap.release()
    return None

def capture_frame(cap):
    """Grab a frame, save it for HUD display."""
    ret, frame = cap.read()
    if not ret:
        return None
    cv2.imwrite(FRAME_PATH, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return frame

def analyze_scene(frame, context=""):
    """Send frame to Gemini for quick scene understanding."""
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    img_data = buf.tobytes()
    prompt = (f"You are Jarvis's eyes. Describe what you see in 1-2 sentences. "
              f"Note: people, objects, movement, lighting. Be concise like a HUD readout. "
              f"{context}")
    try:
        r = gemini.models.generate_content(
            model=MODEL,
            contents=[prompt, types.Part.from_bytes(data=img_data, mime_type='image/jpeg')]
        )
        return r.text.strip() if r.text else None
    except Exception as e:
        return f"Vision error: {e}"

def detect_motion(prev_frame, curr_frame, threshold=25):
    """Simple motion detection between frames."""
    if prev_frame is None:
        return False
    gray1 = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray1, gray2)
    _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    motion_pct = (thresh.sum() / 255) / thresh.size * 100
    return motion_pct > 2  # More than 2% pixels changed

def main():
    log("👁️ Jarvis Vision System starting...")
    
    state = {
        "status": "SEARCHING",
        "last_scene": "No camera available",
        "motion": False,
        "last_analysis": 0,
        "camera_available": False
    }
    save_state(state)

    prev_frame = None
    analysis_interval = 30  # Analyze scene every 30s (save credits)
    
    while True:
        cap = try_open_camera()
        
        if cap is None:
            state["status"] = "NO_CAMERA"
            state["camera_available"] = False
            state["last_scene"] = "Waiting for camera — enable in ChromeOS Settings > Linux > Camera"
            save_state(state)
            time.sleep(10)  # Check every 10s — be ready instantly when user enables it
            continue
        
        log("👁️ Camera ONLINE")
        state["status"] = "ACTIVE"
        state["camera_available"] = True
        save_state(state)
        
        while True:
            frame = capture_frame(cap)
            if frame is None:
                log("⚠️ Frame capture failed, camera lost")
                cap.release()
                state["status"] = "RECONNECTING"
                save_state(state)
                break
            
            # Motion detection
            motion = detect_motion(prev_frame, frame)
            state["motion"] = motion
            prev_frame = frame.copy()
            
            # Periodic scene analysis (every 30s, or immediately if motion detected after quiet)
            now = time.time()
            should_analyze = (now - state["last_analysis"] > analysis_interval)
            
            if should_analyze and motion:
                description = analyze_scene(frame)
                if description:
                    state["last_scene"] = description
                    state["last_analysis"] = now
                    log(f"👁️ Scene: {description}")
            
            state["last_frame_time"] = datetime.now().isoformat()
            save_state(state)
            
            time.sleep(INTERVAL_IDLE if not motion else INTERVAL_ACTIVE)
        
        time.sleep(5)  # Brief pause before retry

if __name__ == "__main__":
    pidfile = "/tmp/jarvis_vision.pid"
    if os.path.exists(pidfile):
        try:
            os.kill(int(open(pidfile).read().strip()), 0)
            print("Already running")
            exit(0)
        except (ProcessLookupError, ValueError):
            pass
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
    main()
