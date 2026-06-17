#!/usr/bin/env python3
"""API bridge - serves Jarvis state + conversation log to HUD."""
import json, os, time
from http.server import HTTPServer, BaseHTTPRequestHandler

STATE_FILE = "/tmp/jarvis_state"
HUD_LOG = "/tmp/jarvis_hud_log.json"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        state = "idle"
        try:
            with open(STATE_FILE) as f:
                state = f.read().strip()
        except: pass
        logs = []
        try:
            with open(HUD_LOG) as f:
                logs = json.load(f)
        except: pass
        self.wfile.write(json.dumps({"state": state, "logs": logs}).encode())
    def log_message(self, *a): pass

HTTPServer(("", 9090), Handler).serve_forever()
