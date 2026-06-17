#!/usr/bin/env python3
import os, asyncio, json, subprocess, random, requests, textwrap, shutil
from groq import Groq

OUTPUT_DIR = os.path.expanduser("~/jarvis_shorts")
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

TOPICS = [
    "space and astronomy", "human body facts", "deep ocean creatures",
    "ancient civilizations", "animal intelligence", "physics in daily life",
    "inventions that changed history", "how memory works",
    "mathematics in nature", "engineering marvels", "future technology",
    "weather phenomena", "nutrition science", "brain functions",
    "electricity explained", "black holes", "DNA and genetics",
    "speed of light", "artificial intelligence", "renewable energy"
]

def generate_script():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    topic = random.choice(TOPICS)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You create YouTube Shorts scripts. Rules:\n- HALAL content only: no manipulation, dark psychology, haram topics\n- Teach REAL facts that benefit people\n- 40-60 seconds spoken (100-130 words)\n- Start with a hook (shocking fact or question)\n- Simple, engaging, educational\n- End with a memorable takeaway\n- No 'hey guys' - dive straight in\nOutput the narration, then --- then 5 image keywords one per line."},
            {"role": "user", "content": f"Create a YouTube Short about: {topic}"}
        ],
        temperature=0.9, max_tokens=400
    )
    text = response.choices[0].message.content.strip()
    if "---" in text:
        script, kw_block = text.split("---", 1)
        keywords = [k.strip() for k in kw_block.strip().split("\n") if k.strip()]
    else:
        script, keywords = text, [topic, "science", "nature"]
    return topic, script.strip(), keywords[:5]

def download_images(keywords):
    os.makedirs(TEMP_DIR, exist_ok=True)
    images = []
    for i, kw in enumerate(keywords):
        img_path = os.path.join(TEMP_DIR, f"img_{i}.jpg")
        try:
            r = requests.get("https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_KEY},
                params={"query": kw, "per_page": 5, "orientation": "portrait"})
            photos = r.json().get("photos", [])
            if photos:
                url = random.choice(photos[:3])["src"]["large2x"]
                with open(img_path, "wb") as f:
                    f.write(requests.get(url).content)
                images.append(img_path)
                continue
        except:
            pass
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=#1a1a2e:s=1080x1920:d=1", "-frames:v", "1", img_path],
            capture_output=True)
        images.append(img_path)
    return images

async def generate_audio(script, path):
    import edge_tts
    c = edge_tts.Communicate(script, "en-US-GuyNeural", rate="+5%")
    await c.save(path)

def get_duration(f):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", f],
        capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])

def create_video(script, images, audio_path, video_path):
    duration = get_duration(audio_path)
    n = len(images)
    seg = duration / n
    words = script.split()
    wperseg = max(1, len(words) // n)

    # Create segments with zoom + text
    segs = []
    for i, img in enumerate(images):
        seg_path = os.path.join(TEMP_DIR, f"seg_{i}.mp4")
        start = i * wperseg
        end = start + wperseg if i < n - 1 else len(words)
        text = " ".join(words[start:end])
        wrapped = "\\n".join(textwrap.wrap(text, width=22))
        wrapped = wrapped.replace("'", "").replace(":", "").replace('"', '')

        frames = int(seg * 30)
        vf = (
            f"scale=1200:2134,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
            f"zoompan=z='min(1.15,zoom+0.0008)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"drawtext=text='{wrapped}':fontcolor=white:fontsize=52:"
            f"x=(w-text_w)/2:y=h*0.75:font=monospace:borderw=3:bordercolor=black:"
            f"box=1:boxcolor=black@0.4:boxborderw=15"
        )
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", str(seg + 0.5),
            "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", "30", seg_path], capture_output=True)
        segs.append(seg_path)

    # Xfade transitions between segments
    if len(segs) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", segs[0], "-i", audio_path,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
            "-t", str(duration), "-shortest", video_path], capture_output=True)
        return

    inputs = []
    for s in segs:
        inputs += ["-i", s]
    inputs += ["-i", audio_path]

    fade = 0.4
    fc_parts = []
    for i in range(len(segs) - 1):
        offset = seg * (i + 1) - fade
        if offset < 0.1:
            offset = 0.1
        src1 = f"[{i}:v]" if i == 0 else f"[v{i}]"
        out = f"[v{i+1}]" if i < len(segs) - 2 else "[outv]"
        fc_parts.append(f"{src1}[{i+1}:v]xfade=transition=slideleft:duration={fade}:offset={offset:.2f}{out}")

    fc = ";".join(fc_parts)
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", fc,
        "-map", "[outv]", "-map", f"{len(segs)}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-t", str(duration), "-shortest", video_path]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # fallback: simple concat
        concat = os.path.join(TEMP_DIR, "concat.txt")
        with open(concat, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat,
            "-i", audio_path, "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
            "-c:a", "aac", "-t", str(duration), "-shortest", video_path], capture_output=True)

def main():
    print("🎬 Generating Short...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    topic, script, keywords = generate_script()
    print(f"  Topic: {topic}")
    images = download_images(keywords)
    print(f"  Images: {len(images)}")
    audio_path = os.path.join(TEMP_DIR, "audio.mp3")
    asyncio.run(generate_audio(script, audio_path))
    dur = get_duration(audio_path)
    print(f"  Audio: {dur:.1f}s")
    count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")]) + 1
    video_path = os.path.join(OUTPUT_DIR, f"short_{count}.mp4")
    create_video(script, images, audio_path, video_path)
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    with open(video_path.replace(".mp4", ".txt"), "w") as f:
        f.write(f"Topic: {topic}\nKeywords: {', '.join(keywords)}\n\n{script}")
    print(f"✅ Done: {video_path}")
    return video_path, topic, script, keywords

if __name__ == "__main__":
    main()
