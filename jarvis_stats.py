 import os
  import json
  from datetime import datetime
  
  STATS_FILE = os.path.expanduser("~/jarvis_stats.json")
  
  def load_stats():
      if os.path.exists(STATS_FILE):
          with open(STATS_FILE) as f:
              return json.load(f)
      return {"commands": []}
  
  def log_command(text, action_type):
      stats = load_stats()
      entry = {
          "text": text,
          "type": action_type,
          "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      }
      stats["commands"].append(entry)
      with open(STATS_FILE, "w") as f:
          json.dump(stats, f, indent=2)
