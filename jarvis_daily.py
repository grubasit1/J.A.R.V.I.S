#!/usr/bin/env python3
"""Jarvis Daily Shorts Routine - Auto-generate & upload 3-6 shorts/day
Run with: python3 ~/jarvis_daily.py
Or set up cron: crontab -e → 0 8 * * * cd ~ && python3 jarvis_daily.py >> jarvis_daily.log 2>&1
"""

import os, sys, json, random, time, asyncio, subprocess, shutil, textwrap, pickle, requests
from datetime import datetime

# ─── Config ───
POSTS_PER_DAY = 1  # REDUCED from 3-6 to save credits. Manual post with: python3 jarvis_daily.py --now
DELAY_BETWEEN = None  # Random delays, not fixed
OUTPUT_DIR = os.path.expanduser("~/jarvis_shorts")
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
LOG_FILE = os.path.expanduser("~/jarvis_daily.log")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

# Content categories - ALL HALAL, educational, viral-worthy
# Specific > Generic. "The deepest hole humans ever dug" > "earth science facts"
CATEGORIES = [
    # Mind-Blowing Science
    "what happens inside a black hole as you fall in",
    "the organism that is technically immortal and how it works",
    "what your brain does in the 7 minutes after death",
    "the sound that can make you physically sick",
    "why time moves slower the faster you travel",
    "the lake that turns animals into stone statues",
    "what happens to your body at the bottom of the ocean",
    "the parasite that controls its host's brain",
    # Islamic Golden Age (untold genius stories)
    "the Muslim scientist who described flight 600 years before the Wright brothers",
    "how a Muslim scholar invented the first programmable robot in 1206",
    "the Islamic hospital system that was free 1000 years before modern healthcare",
    "Al-Zahrawi the Muslim surgeon who invented over 200 surgical tools",
    "how Muslims built the first universities while Europe was in darkness",
    "Ibn al-Haytham the father of modern optics who proved how vision works",
    # Geography & Hidden Places
    "the city built entirely underground that held 20000 people",
    "the island where every compass stops working",
    "the zone in the ocean where GPS satellites lose signal",
    "the cave system so large it has its own weather",
    "the place on Earth where gravity doesn't work normally",
    # Human Body (creepy/fascinating)
    "your skeleton replaces itself completely every 10 years",
    "the part of your body that can regrow itself like a lizard",
    "why you can't tickle yourself and what it reveals about your brain",
    "your body produces enough electricity to charge a phone",
    "the muscle in your body that never stops working from before birth",
    # Engineering & Tech Marvels
    "the building designed to survive a direct nuclear hit",
    "the machine that can dig through solid rock at 50 feet per day",
    "the material stronger than steel but lighter than paper",
    "the satellite that can read a license plate from space",
    "the bridge that took 600 years to finish building",
    # Psychology & Behavior (no dark psych — pure fascination)
    "why your brain invents memories that never happened",
    "the frequency that makes everyone feel uneasy but nobody knows why",
    "why you always wake up 1 minute before your alarm",
    "the illusion that tricks every human brain without exception",
    "why certain songs get permanently stuck in your head",
    # History's Wildest Moments
    "the war that lasted 335 years with zero casualties",
    "the man who survived both atomic bombs in 3 days",
    "the civilization that vanished overnight leaving no trace",
    "the letter that took 200 years to be delivered",
    "the accidental discovery that saves 200 million lives per year",
]

SYSTEM_PROMPT = """You are a VIRAL YouTube Shorts scriptwriter. Your scripts get millions of views.

=== CONTENT RULES (NON-NEGOTIABLE) ===
- HALAL ONLY: NO dark psychology, manipulation, haram, dating, music glorification, gambling, alcohol
- NO promoting any religion EXCEPT Islam (shirk is haram)
- NO lies or misleading clickbait. Every fact MUST be real and verifiable.
- Educational, inspiring, clean content that makes people SMARTER

=== VIRAL SCRIPT STRUCTURE (45-55 seconds, 110-140 words) ===

**HOOK (first 3 seconds — this decides if they scroll or stay):**
Use ONE of these proven patterns:
- "This [thing] is illegal in [X] countries and nobody knows why"
- "Scientists just discovered something that changes everything about [topic]"
- "[Shocking stat]. Let that sink in."
- "There's a [thing] that [impossible-sounding fact]"
- "What if I told you [counter-intuitive truth]?"
- Start mid-action: "Right now, underneath [location], there's a [thing] that..."
DO NOT: use "Hey guys", "Did you know", "In this video", or any weak opener.

**BODY (build tension with 2-3 escalating facts):**
- Each fact should be MORE surprising than the last
- Use specific numbers: "3,700 meters deep" not "very deep"
- Compare to relatable things: "That's taller than 4 Eiffel Towers stacked"
- Create "wait, WHAT?" moments — the viewer should want to rewatch
- Pace: short punchy sentences. Never more than 15 words per sentence.

**CLOSER (make them comment/share):**
- End with an open loop or mind-blow: "And the craziest part? We still don't know why."
- OR a call to think: "So next time you [everyday action], remember this."
- NEVER say "like and subscribe" or "follow for more"

=== VOICE & TONE ===
- Sound like a confident friend who just found out something insane
- NOT robotic narrator. NOT overhyped YouTuber. Natural, sharp, slightly awed.
- Use "you" directly — make the viewer feel personally addressed
- Contractions: "don't", "can't", "it's" — never formal "do not"

=== OUTPUT FORMAT ===
[narration script — no stage directions, just pure spoken words]
---
[12 VISUAL search keywords below — these are used to find stock VIDEO CLIPS on Pexels]
[Each keyword must describe a VISUAL SCENE that matches what is being said at that point in the script]
[WRONG: "facts", "science", "education" — these give random irrelevant clips]
[RIGHT: "ocean deep water", "volcano erupting lava", "brain neurons firing", "ancient temple ruins"]
[Each keyword = one specific visual scene the viewer should SEE while listening]
keyword1
keyword2
keyword3
keyword4
keyword5
keyword6
keyword7
keyword8
keyword9
keyword10
keyword11
keyword12"""

METADATA_PROMPT = """You are a YouTube algorithm expert. Your metadata gets videos pushed to millions.

Return JSON ONLY:
{"title": "...", "description": "...", "tags": ["tag1","tag2",...], "hashtags": ["#Shorts","#Facts",...]}

=== TITLE (most important — this is your thumbnail text) ===
- Max 50 chars (shorter = more clickable on mobile)
- Use pattern: [Shocking claim] + [Specificity]
- Examples: "This Lake Kills Everything It Touches", "Japan Built a City Underground", "Your Brain Does This Every 90 Minutes"
- NEVER: questions, "Did you know", emojis, ALL CAPS, or vague titles
- Must be TRUE — the video must deliver on the title promise

=== DESCRIPTION ===
- Line 1: One-sentence hook that makes them watch (different angle from title)
- Line 2: Empty
- Line 3: Hashtags

=== TAGS (backend, 10-12) ===
- Mix: 3 broad ("science facts", "education"), 4 specific to topic, 3 trending adjacent
- Include misspellings people search: "intresting facts", "amzing science"

=== HASHTAGS (5-7, always include #Shorts) ===
- #Shorts FIRST always
- Mix size: 2 huge (#Facts #Science), 2 medium (#MindBlown #TIL), 2 niche to topic"""


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _parse_script(text):
    if "---" in text:
        script, kw_block = text.split("---", 1)
        keywords = [k.strip() for k in kw_block.strip().split("\n") if k.strip() and not k.strip().startswith("[")]
    else:
        script, keywords = text, [topic, f"{topic} closeup", f"{topic} aerial", "cinematic nature", "dramatic sky"]
    return script.strip(), keywords[:12]


def generate_script(topic):
    """Use Gemini 2.5 Flash for high-quality viral scripts (fast + reliable)."""
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    resp = client.models.generate_content(model='gemini-2.5-flash',
        contents=f"{SYSTEM_PROMPT}\n\nCreate a YouTube Short script about: {topic}")
    return _parse_script(resp.text.strip())


def generate_metadata(topic, script):
    """Use Gemini 2.5 Flash for optimized metadata."""
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    resp = client.models.generate_content(model='gemini-2.5-flash',
        contents=f"{METADATA_PROMPT}\n\nTopic: {topic}\nScript: {script}\n\nReturn JSON only.")
    text = resp.text.strip()
    # Strip markdown code block if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def generate_veo_clip(prompt):
    """Generate a video clip using Veo 2 via Vertex AI. Cheaper than Veo 3."""
    import google.auth
    import google.auth.transport.requests as auth_requests
    creds, _ = google.auth.default()
    creds.refresh(auth_requests.Request())
    token = creds.token
    project = "YOUR_GCP_PROJECT"
    url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/veo-2.0-generate-001:predictLongRunning"

    clip_path = os.path.join(TEMP_DIR, f"veo_{random.randint(1000,9999)}.mp4")
    veo_prompt = f"Cinematic vertical 9:16 video, smooth slow motion, {prompt}, dramatic lighting, 4K quality"

    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"instances": [{"prompt": veo_prompt}],
                  "parameters": {"sampleCount": 1, "aspectRatio": "9:16"}})
        op = r.json()
        op_name = op.get("name", "")
        if not op_name:
            return None

        # Poll for completion (max 3 min)
        fetch_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/veo-2.0-generate-001:fetchPredictOperation"
        for _ in range(36):
            time.sleep(5)
            resp = requests.post(fetch_url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"operationName": op_name})
            result = resp.json()
            if result.get("done"):
                videos = result.get("response", {}).get("videos", [])
                if videos:
                    vid_url = videos[0].get("gcsUri") or videos[0].get("uri")
                    if vid_url and vid_url.startswith("gs://"):
                        subprocess.run(["gsutil", "cp", vid_url, clip_path], capture_output=True,
                            env={**os.environ, "PATH": f"/path/to/google-cloud-sdk/bin:{os.environ.get('PATH','')}"})
                    elif "bytesBase64Encoded" in videos[0]:
                        import base64
                        with open(clip_path, "wb") as f:
                            f.write(base64.b64decode(videos[0]["bytesBase64Encoded"]))
                    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 1000:
                        log(f"   🎬 Veo 2 clip generated!")
                        return clip_path
                break
    except Exception as e:
        log(f"   ⚠️ Veo 2 error: {e}")
    return None


def generate_lyria_music(mood="energetic cinematic", duration=30):
    """Generate background music with Lyria 3 Clip. ~$0.04 per clip."""
    import google.auth
    import google.auth.transport.requests as auth_requests
    creds, _ = google.auth.default()
    creds.refresh(auth_requests.Request())
    token = creds.token
    project = "YOUR_GCP_PROJECT"
    url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/lyria-3-clip-preview:predict"

    music_path = os.path.join(TEMP_DIR, "bg_music.mp3")
    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"instances": [{"prompt": f"{mood} background music, no vocals, cinematic underscore"}],
                  "parameters": {"durationSeconds": duration}})
        result = r.json()
        predictions = result.get("predictions", [])
        if predictions:
            import base64
            audio_data = predictions[0].get("bytesBase64Encoded", "")
            if audio_data:
                with open(music_path, "wb") as f:
                    f.write(base64.b64decode(audio_data))
                log(f"   🎵 Lyria music generated!")
                return music_path
    except Exception as e:
        log(f"   ⚠️ Lyria error: {e}")
    return None


def download_images(keywords, count=12):
    """Try Veo 2 for first 1-2 clips (cinematic), fallback to Pexels VIDEOS (free) for rest.
    Prioritizes video clips over images. Downloads multiple per keyword."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    media = []

    # VEO DISABLED — too expensive ($0.35+/clip, burned $700+ in 2 days)
    # Use Pexels free clips only until we have income
    # veo_clip = generate_veo_clip(keywords[0] if keywords else "cinematic")
    # if veo_clip:
    #     media.append(("video", veo_clip))

    # Rest: Pexels videos (free) — get multiple clips per keyword
    clip_idx = len(media)
    for kw in keywords:
        if len(media) >= count:
            break
        if PEXELS_KEY:
            try:
                r = requests.get("https://api.pexels.com/videos/search",
                    headers={"Authorization": PEXELS_KEY},
                    params={"query": kw, "per_page": 8, "orientation": "portrait", "size": "medium"})
                videos = r.json().get("videos", [])
                # Grab 2-3 clips per keyword for variety
                for vid in videos[:3]:
                    if len(media) >= count:
                        break
                    files = vid.get("video_files", [])
                    hd = [f for f in files if f.get("height", 0) >= 720 and f.get("width", 0) <= 1200]
                    url = (hd[0] if hd else files[0])["link"] if files else None
                    if url:
                        clip_path = os.path.join(TEMP_DIR, f"clip_{clip_idx}.mp4")
                        try:
                            with open(clip_path, "wb") as f:
                                f.write(requests.get(url, timeout=15).content)
                            if os.path.getsize(clip_path) > 10000:
                                media.append(("video", clip_path))
                                clip_idx += 1
                        except:
                            pass
            except: pass

    # Only use images as absolute last resort
    if len(media) < 4:
        for i, kw in enumerate(keywords):
            if len(media) >= count:
                break
            if PEXELS_KEY:
                try:
                    r = requests.get("https://api.pexels.com/v1/search",
                        headers={"Authorization": PEXELS_KEY},
                        params={"query": kw, "per_page": 3, "orientation": "portrait"})
                    photos = r.json().get("photos", [])
                    if photos:
                        url = random.choice(photos[:3])["src"]["large2x"]
                        img_path = os.path.join(TEMP_DIR, f"img_{i}.jpg")
                        with open(img_path, "wb") as f:
                            f.write(requests.get(url, timeout=10).content)
                        media.append(("image", img_path))
                except: pass
    return media


async def generate_audio(script, audio_path):
    """Try Google Cloud TTS (premium), fallback to edge-tts"""
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=script)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-J",  # Deep male narrator voice
            ssml_gender=texttospeech.SsmlVoiceGender.MALE
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.05, pitch=-2.0  # Slightly faster, deeper = documentary feel
        )
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        with open(audio_path, "wb") as f:
            f.write(response.audio_content)
        log("   🎙️ Using Google Cloud premium voice")
    except Exception as e:
        log(f"   ⚠️ Cloud TTS failed ({e}), using edge-tts fallback")
        import edge_tts
        comm = edge_tts.Communicate(script, "en-US-GuyNeural", rate="+5%")
        await comm.save(audio_path)


def get_duration(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def create_video(script, media, audio_path, video_path):
    """Pure ffmpeg: zoompan, xfade transitions, text overlays, color boost, camera shake."""
    duration = float(json.loads(subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        capture_output=True, text=True).stdout)["format"]["duration"])

    temp_dir = os.path.join(OUTPUT_DIR, "temp_edit")
    os.makedirs(temp_dir, exist_ok=True)

    # Flatten media to file paths
    files = []
    for item in media:
        if isinstance(item, tuple):
            files.append(item[1])
        else:
            files.append(item)
    # Remove non-existent
    files = [f for f in files if os.path.exists(f)]
    if not files:
        log("   ❌ No media files available")
        return

    # Need enough segments (~2.5s each)
    target = max(8, int(duration / 2.5))
    while len(files) < target:
        files.append(random.choice(files))
    files = files[:target]

    seg_dur = duration / len(files)

    # Split script into phrases for text overlays
    words = script.split()
    wps = max(1, len(words) // len(files))

    # Create segments with zoompan + text
    segs = []
    effects = ["zoom_in", "zoom_out", "pan_left", "pan_right", "zoom_punch"]
    for i, img in enumerate(files):
        seg_path = os.path.join(temp_dir, f"seg_{i}.mp4")
        frames = int(seg_dur * 30)
        effect = random.choice(effects)

        if effect == "zoom_in":
            zp = f"zoompan=z='1+0.002*in':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        elif effect == "zoom_out":
            zp = f"zoompan=z='1.3-0.002*in':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        elif effect == "pan_left":
            zp = f"zoompan=z='1.15':d={frames}:x='iw*0.15*(1-in/{frames})':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        elif effect == "pan_right":
            zp = f"zoompan=z='1.15':d={frames}:x='iw*0.15*in/{frames}':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        else:
            zp = f"zoompan=z='if(lt(in,8),1+0.04*in,1.3-0.001*(in-8))':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"

        # Text for this segment
        start_w = i * wps
        end_w = start_w + wps if i < len(files) - 1 else len(words)
        text = " ".join(words[start_w:end_w])
        text = text.replace("'", "").replace(":", " ").replace('"', '').replace('%', ' percent')
        wrapped = "\\n".join(textwrap.wrap(text, width=28))

        is_video = img.endswith(('.mp4', '.webm', '.mov'))
        if is_video:
            vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  f"eq=brightness=0.03:saturation=1.3,"
                  f"drawtext=text='{wrapped}':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2:"
                  f"fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
                  f"borderw=4:bordercolor=black@0.95:"
                  f"shadowcolor=black@0.7:shadowx=3:shadowy=3:"
                  f"enable='between(t,0.15,{seg_dur-0.15})',"
                  f"fade=t=in:st=0:d=0.15,fade=t=out:st={seg_dur-0.15}:d=0.15")
            subprocess.run(["ffmpeg", "-y", "-i", img, "-t", str(seg_dur),
                "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "24", "-an", seg_path], capture_output=True)
        else:
            vf = (f"scale=1200:2134,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
                  f"{zp},"
                  f"eq=brightness=0.03:saturation=1.3,"
                  f"drawtext=text='{wrapped}':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2:"
                  f"fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
                  f"borderw=4:bordercolor=black@0.95:"
                  f"shadowcolor=black@0.7:shadowx=3:shadowy=3:"
                  f"enable='between(t,0.15,{seg_dur-0.15})',"
                  f"fade=t=in:st=0:d=0.15,fade=t=out:st={seg_dur-0.15}:d=0.15")
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", str(seg_dur),
                "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "24", seg_path], capture_output=True)

        if os.path.exists(seg_path) and os.path.getsize(seg_path) > 1000:
            segs.append(seg_path)

    if not segs:
        log("   ❌ No segments created")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # Merge segments + audio — simple concat (reliable, low memory)
    merged = os.path.join(temp_dir, "merged.mp4")
    if len(segs) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", segs[0], "-i", audio_path,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
            "-shortest", merged], capture_output=True, timeout=120)
    else:
        concat_f = os.path.join(temp_dir, "list.txt")
        with open(concat_f, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        # Concat segments then mux audio
        concat_vid = os.path.join(temp_dir, "concat.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_f,
            "-c", "copy", concat_vid], capture_output=True, timeout=60)
        if os.path.exists(concat_vid) and os.path.getsize(concat_vid) > 1000:
            subprocess.run(["ffmpeg", "-y", "-i", concat_vid, "-i", audio_path,
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                "-shortest", merged], capture_output=True, timeout=60)
        else:
            # Ultimate fallback: just use first segment + audio
            subprocess.run(["ffmpeg", "-y", "-i", segs[0], "-i", audio_path,
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                "-shortest", merged], capture_output=True, timeout=60)

    # Skip camera shake — saves RAM (was causing OOM on Chromebook)
    if os.path.exists(merged) and os.path.getsize(merged) > 1000:
        shutil.copy2(merged, video_path)

    shutil.rmtree(temp_dir, ignore_errors=True)


def upload_to_youtube(video_path, meta):
    """Upload to YouTube. Returns video ID or None."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    TOKEN = os.path.expanduser("~/yt_token.pickle")
    SECRET = os.path.expanduser("~/yt_client_secret.json")
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    creds = None
    if os.path.exists(TOKEN):
        with open(TOKEN, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN, "wb") as f:
                pickle.dump(creds, f)
        else:
            log("❌ YouTube auth expired. Run: python3 ~/jarvis_upload.py --auth")
            return None

    yt = build("youtube", "v3", credentials=creds)
    tags = meta.get("tags", [])
    hashtags = meta.get("hashtags", [f"#{t}" for t in tags[:5]])
    if not hashtags:
        hashtags = ["#Shorts", "#Facts", "#Education", "#Science", "#DidYouKnow"]
    hashtag_str = " ".join(hashtags) if hashtags[0].startswith("#") else " ".join(f"#{h}" for h in hashtags)
    # Always ensure #Shorts is there
    if "#Shorts" not in hashtag_str and "#shorts" not in hashtag_str:
        hashtag_str += " #Shorts"
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": f"{meta['description']}\n\n{hashtag_str}",
            "tags": tags + ["Shorts", "facts", "education"], "categoryId": "22"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    resp = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return resp["id"]


def create_one_short(index, topic, _attempt=1):
    """Generate + upload a single short. Retries up to 3 times on failure."""
    MAX_RETRIES = 3
    log(f"📝 [{index}] Generating script about: {topic}")
    try:
        script, keywords = generate_script(topic)
    except Exception as e:
        log(f"❌ Script generation failed: {e}")
        if _attempt < MAX_RETRIES:
            log(f"🔄 Retrying ({_attempt}/{MAX_RETRIES})...")
            time.sleep(5 * _attempt)
            return create_one_short(index, topic, _attempt + 1)
        return False

    log(f"🖼️  [{index}] Downloading images...")
    media = download_images(keywords)

    log(f"🔊 [{index}] Generating voiceover...")
    audio_path = os.path.join(TEMP_DIR, "audio.mp3")
    try:
        asyncio.run(generate_audio(script, audio_path))
    except Exception as e:
        log(f"❌ Audio failed: {e}")
        if _attempt < MAX_RETRIES:
            log(f"🔄 Retrying ({_attempt}/{MAX_RETRIES})...")
            time.sleep(5 * _attempt)
            return create_one_short(index, topic, _attempt + 1)
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(OUTPUT_DIR, f"short_{timestamp}.mp4")

    log(f"🎥 [{index}] Creating video...")
    create_video(script, media, audio_path, video_path)

    # Update credit tracker (live spending)
    if os.path.exists(video_path) and os.path.getsize(video_path) > 1000:
        try:
            credit_file = os.path.expanduser("~/jarvis_credit.json")
            with open(credit_file) as f:
                cdata = json.load(f)
            # Estimate cost: 1 Veo clip (~5 NOK) + TTS (~0.3 NOK) + Gemini script (~0.2 NOK)
            cdata["used"] = cdata.get("used", 104) + 5.5
            cdata["remaining"] = cdata["total_credit"] - cdata["used"]
            cdata["percent_used"] = round(cdata["used"] / cdata["total_credit"] * 100, 1)
            with open(credit_file, "w") as f:
                json.dump(cdata, f, indent=2)
        except: pass

    if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
        log(f"❌ Video creation failed")
        if _attempt < MAX_RETRIES:
            log(f"🔄 Retrying ({_attempt}/{MAX_RETRIES})...")
            time.sleep(5 * _attempt)
            return create_one_short(index, topic, _attempt + 1)
        return False

    log(f"🎵 [{index}] Adding background music...")
    # Try to add Lyria background music
    try:
        music_path = generate_lyria_music()
        if music_path and os.path.exists(music_path):
            mixed_path = video_path.replace(".mp4", "_mixed.mp4")
            r = subprocess.run(["ffmpeg", "-y", "-i", video_path, "-i", music_path,
                "-filter_complex", "[1:a]volume=0.12[bg];[0:a][bg]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", mixed_path],
                capture_output=True)
            if r.returncode == 0 and os.path.exists(mixed_path):
                os.replace(mixed_path, video_path)
    except:
        pass

    log(f"📊 [{index}] Generating metadata...")
    try:
        meta = generate_metadata(topic, script)
    except Exception as e:
        meta = {"title": f"Did You Know? {topic.title()}", "description": script[:150], "tags": ["Shorts", "facts", "education"]}

    # Save locally
    info_path = os.path.join(OUTPUT_DIR, f"short_{timestamp}.json")
    with open(info_path, "w") as f:
        json.dump({"topic": topic, "script": script, "meta": meta, "video": video_path}, f, indent=2)

    log(f"📤 [{index}] Uploading to YouTube...")
    uploaded = False
    for upload_try in range(3):
        try:
            vid_id = upload_to_youtube(video_path, meta)
            if vid_id:
                log(f"✅ [{index}] POSTED! https://youtube.com/shorts/{vid_id} — {meta['title']}")
                uploaded = True
                break
            else:
                log(f"⚠️  [{index}] Upload returned None, retry {upload_try+1}/3...")
                time.sleep(10)
        except Exception as e:
            log(f"⚠️  [{index}] Upload error (try {upload_try+1}/3): {e}")
            time.sleep(10)

    if not uploaded:
        log(f"⚠️  [{index}] All upload attempts failed. Video saved at {video_path}")

    # Cleanup temp
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    return True


def main():
    log(f"🚀 Jarvis Daily Routine Started — Posting {POSTS_PER_DAY} shorts today")
    log(f"{'='*50}")

    # Pick random unique topics
    topics = random.sample(CATEGORIES, min(POSTS_PER_DAY, len(CATEGORIES)))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i, topic in enumerate(topics, 1):
        create_one_short(i, topic)
        if i < len(topics):
            # Random wait: 1-4 hours, feels organic not robotic
            wait = random.randint(60 * 60, 60 * 60 * 4)
            log(f"⏳ Waiting {wait//60} minutes before next post...")
            time.sleep(wait)

    log(f"🏁 Daily routine complete! Posted {POSTS_PER_DAY} shorts.\n")


if __name__ == "__main__":
    if "--now" in sys.argv:
        # Quick mode: make 1 short immediately (for testing)
        POSTS_PER_DAY = 1
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        topic = random.choice(CATEGORIES)
        create_one_short(1, topic)
    else:
        main()
