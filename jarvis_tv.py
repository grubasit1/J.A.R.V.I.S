from samsungtvws import SamsungTVWS
import time

TV_IP = "YOUR_TV_IP"
TV_PORT = 8002
TV_NAME = "JarvisRemote"

tv = None
_last_connect = 0

# Samsung TV App IDs (2020+ Tizen)
APP_IDS = {
    "netflix": "3201907018807",
    "youtube": "111299001912",
    "disney": "3202204027038",
    "disney+": "3202204027038",
    "prime": "3201910019365",
    "amazon": "3201910019365",
    "hbo": "3202301029760",
    "max": "3202301029760",
    "spotify": "3201606009684",
    "apple tv": "3201807016597",
    "apple music": "3201908019041",
    "tiktok": "3202008021577",
    "twitch": "3202203026841",
    "plex": "3201512006963",
    "paramount": "3202110025305",
    "browser": "3202010022079",
    "steam": "3201702011851",
    "xbox": "3202203026799",
    "viaplay": "11111300404",
    "pluto": "3201806016802",
    "tubi": "3201504001965",
    "dazn": "3201806016390",
    "crunchyroll": "3201602007250",
    "nrk": "3201611011981",
    "tv2": "3201803015934",
}

def connect():
    global tv, _last_connect
    # Rate limit reconnects (don't spam if TV is off)
    if time.time() - _last_connect < 5:
        return tv is not None
    _last_connect = time.time()
    try:
        tv = SamsungTVWS(host=TV_IP, port=TV_PORT, name=TV_NAME, timeout=3)
        return True
    except:
        tv = None
        return False

def send_key(key):
    try:
        if not tv:
            if not connect():
                return False
        tv.send_key(key)
        return True
    except:
        if connect():
            try:
                tv.send_key(key)
                return True
            except:
                pass
        return False

def run_app(app_id):
    try:
        if not tv:
            if not connect():
                return False
        tv.run_app(app_id)
        return True
    except:
        if connect():
            try:
                tv.run_app(app_id)
                return True
            except:
                pass
        return False

# Common commands
def power():       return send_key("KEY_POWER")
def vol_up():      return send_key("KEY_VOLUP")
def vol_down():    return send_key("KEY_VOLDOWN")
def mute():        return send_key("KEY_MUTE")
def ch_up():       return send_key("KEY_CHUP")
def ch_down():     return send_key("KEY_CHDOWN")
def source():      return send_key("KEY_SOURCE")
def home():        return send_key("KEY_HOME")
def back():        return send_key("KEY_RETURN")
def enter():       return send_key("KEY_ENTER")
def up():          return send_key("KEY_UP")
def down():        return send_key("KEY_DOWN")
def left():        return send_key("KEY_LEFT")
def right():       return send_key("KEY_RIGHT")
def play():        return send_key("KEY_PLAY")
def pause():       return send_key("KEY_PAUSE")
def stop():        return send_key("KEY_STOP")
def exit_app():    return send_key("KEY_EXIT")

def open_app(app_name):
    """Open a TV app by name."""
    name = app_name.lower().strip()
    for keyword, app_id in APP_IDS.items():
        if keyword in name:
            if run_app(app_id):
                return keyword.capitalize()
    return None

def vol_set(level):
    """Set volume to approximate level (0-100) by going to 0 then up."""
    mute()  # Mute first to avoid loud jumps
    time.sleep(0.3)
    for _ in range(min(level // 2, 50)):
        send_key("KEY_VOLUP")
        time.sleep(0.1)
    mute()  # Unmute
