#!/usr/bin/env python3
"""Talk to Claude Fable 5 directly — uses GCP credits, not Kiro credits.
Run: python3 ~/jarvis_chat.py
"""
import os, json
from anthropic import AnthropicVertex

claude = AnthropicVertex(project_id='YOUR_GCP_PROJECT_ID', region='us-east5')

# Load your context
memory = {}
try:
    with open(os.path.expanduser("~/jarvis_memory.json")) as f:
        memory = json.load(f)
except: pass

history_text = ""
try:
    with open(os.path.expanduser("~/jarvis_history.md")) as f:
        history_text = f.read()[:3000]
except: pass

SYSTEM = f"""You are Kiro/Jarvis — Basit's AI assistant. You know his full project context.
Be concise, direct, helpful. Same personality as always — honest, no filler.

Basit's context:
{history_text}

IMPORTANT: You CANNOT edit files or run commands in this mode. If Basit needs something executed,
tell him the exact command to run or tell him to open Kiro CLI for that task.
"""

history = []

print("\n🧠 Claude Fable 5 — Direct Chat (uses GCP credits, NOT Kiro)")
print("   Type 'quit' to exit\n")

while True:
    try:
        user = input("\033[1;32mYou: \033[0m").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        break
    if not user or user.lower() in ('quit', 'exit', 'q'):
        print("Bye, sir.")
        break

    history.append({"role": "user", "content": user})

    try:
        response = claude.messages.create(
            model="claude-fable-5",
            max_tokens=1024,
            system=SYSTEM,
            messages=history[-20:]  # Keep last 20 messages for context
        )
        reply = response.content[0].text.strip()
    except Exception as e:
        reply = f"Error: {e}"

    print(f"\033[1;36mClaude: \033[0m{reply}\n")
    history.append({"role": "assistant", "content": reply})
