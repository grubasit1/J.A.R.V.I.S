import os, json, sys, pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import httpx

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = os.path.expanduser("~/yt_client_secret.json")
TOKEN_FILE = os.path.expanduser("~/yt_token.pickle")
SHORTS_DIR = os.path.expanduser("~/shorts")

def get_youtube():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)

def generate_metadata(topic, script):
    """Use LLM to generate viral title, description, and tags."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        try: api_key = open(os.path.expanduser("~/.groq_env")).read().split("=",1)[1].strip()
        except: pass
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", 
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "llama-3.3-70b-versatile", "messages": [
            {"role": "system", "content": "You optimize YouTube Shorts for the algorithm. Return JSON only with keys: title, description, tags, hashtags. title: max 70 chars clickbait but truthful. description: 2-3 lines with hooks. tags: array of 8-10 words without #. hashtags: array of 5-8 items WITH # like #Shorts #Facts. ALWAYS include #Shorts."},
            {"role": "user", "content": f"Topic: {topic}\nScript: {script}\n\nGenerate optimized YouTube Shorts metadata."}
        ], "response_format": {"type": "json_object"}}, timeout=30)
    return r.json()["choices"][0]["message"]["content"]

def upload(video_path, meta_json):
    """Upload video to YouTube as a Short."""
    meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
    title = meta["title"][:100]
    tags = meta.get("tags", [])
    hashtags = meta.get("hashtags", [f"#{t}" for t in tags[:8]])
    if not hashtags:
        hashtags = ["#Shorts", "#Facts", "#Education", "#Science", "#DidYouKnow"]
    hashtag_str = " ".join(h if h.startswith("#") else f"#{h}" for h in hashtags)
    if "#Shorts" not in hashtag_str:
        hashtag_str += " #Shorts"
    description = f"{meta['description']}\n\n{hashtag_str}"
    
    yt = get_youtube()
    body = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "22"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = req.execute()
    print(f"✅ Uploaded: https://youtube.com/shorts/{resp['id']}")
    print(f"   Title: {title}")
    return resp["id"]

def upload_latest():
    """Upload the most recent short."""
    jsons = sorted([f for f in os.listdir(SHORTS_DIR) if f.endswith(".json")], reverse=True)
    if not jsons:
        print("No shorts found in ~/shorts/")
        return
    meta_path = os.path.join(SHORTS_DIR, jsons[0])
    with open(meta_path) as f:
        short_meta = json.load(f)
    video_path = os.path.join(SHORTS_DIR, short_meta["video"])
    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        return
    print(f"Generating optimized metadata for: {short_meta['title']}...")
    meta_json = generate_metadata(short_meta["niche"], short_meta["script"])
    meta = json.loads(meta_json)
    print(f"Title: {meta['title']}")
    print(f"Tags: {meta.get('tags', [])}")
    upload(video_path, meta)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        get_youtube()
        print("✅ Authenticated successfully!")
    else:
        upload_latest()
