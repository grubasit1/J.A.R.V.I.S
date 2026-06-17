#!/usr/bin/env python3
"""Jarvis HUD Control — push updates to the web HUD."""
import json, os

HUD_FILE = "/tmp/jarvis_hud_updates.json"

def _load():
    try:
        with open(HUD_FILE) as f:
            return json.load(f)
    except:
        return {"panels": {}, "custom_panels": {}, "notifications": [], "status": None}

def _save(data):
    with open(HUD_FILE, "w") as f:
        json.dump(data, f)

def set_panel(panel_id, html):
    """Override an existing panel's content. IDs: p-sys, p-brains, p-prog, p-bill, p-goals, p-comms, p-sched, p-orders, p-road, p-cred, p-files, p-net, p-pass"""
    d = _load()
    d.setdefault("panels", {})[panel_id] = html
    _save(d)

def add_panel(panel_id, html, style=""):
    """Add a custom panel (new element on HUD)."""
    d = _load()
    d.setdefault("custom_panels", {})[panel_id] = {"content": html, "style": style}
    _save(d)

def remove_panel(panel_id):
    """Remove a custom or overridden panel."""
    d = _load()
    d.get("panels", {}).pop(panel_id, None)
    d.get("custom_panels", {}).pop(panel_id, None)
    _save(d)

def remove_item(panel_id, text):
    """Remove a specific item from a panel by text match."""
    d = _load()
    html = d.get("panels", {}).get(panel_id, "")
    if html:
        lines = html.split("<br>")
        lines = [l for l in lines if text.lower() not in l.lower()]
        d["panels"][panel_id] = "<br>".join(lines)
        _save(d)

def notify(text):
    """Show a notification popup on the HUD."""
    import time
    d = _load()
    d.setdefault("notifications", []).append({"text": text, "ts": time.time()})
    d["notifications"] = d["notifications"][-5:]
    _save(d)

def set_status(text):
    """Override the status text (next to the dot)."""
    d = _load()
    d["status"] = text
    _save(d)

def clear():
    """Reset all HUD overrides."""
    _save({"panels": {}, "custom_panels": {}, "notifications": [], "status": None})
