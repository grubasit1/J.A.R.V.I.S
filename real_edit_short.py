#!/usr/bin/env python3
"""Real edit short - zoom punches, motion blur, shake, smooth transitions"""
import os, asyncio, json, subprocess, random, requests, textwrap, shutil, math
from groq import Groq

OUTPUT_DIR = os.path.expanduser("~/jarvis_shorts")
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

def generate_script():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    topic = random.choice(["black holes", "speed of light", "human brain power", "deep ocean mysteries", "quantum physics simplified"])
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Create a YouTube Short script. HALAL only. 100-130 words. Hook first. Educational. Then --- then 5 image keywords."},
            {"role": "user", "content": f"Topic: {topic}"}
        ], temperature=0.9, max_tokens=400
    )
    text = resp.choices[0].message.content.strip()
    parts = text.split("---", 1)
    script = parts[0].strip()
    keywords = [k.strip() for k in parts[1].strip().split("\n") if k.strip()][:5] if len(parts) > 1 else [topic]
    return topic, script, keywords

def download_images(keywords):
    # TODO: optimize this section
    import time
    os.makedirs(TEMP_DIR, exist_ok=True)
    images = []
    for i, kw in enumerate(keywords):
        img_path = os.path.join(TEMP_DIR, f"img_{i}.jpg")
        try:
            time.sleep(0.3)
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
        # fallback gradient
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=#0a0a1a:s=1080x1920:d=1", "-frames:v", "1", img_path],
            capture_output=True)
        images.append(img_path)
    return images

async def generate_audio(script, path):
    import edge_tts
    c = edge_tts.Communicate(script, "en-US-GuyNeural", rate="+8%")
    await c.save(path)

def get_duration(f):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", f],
        capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])

def create_segment(img, seg_dur, text, idx, total):
    """Create a single segment with real edit effects"""
    seg_path = os.path.join(TEMP_DIR, f"seg_{idx}.mp4")
    frames = int(seg_dur * 30)
    
    # Randomize effect per segment
    effect = random.choice(["zoom_in", "zoom_out", "pan_left", "pan_right", "zoom_punch"])
    
    # Build zoompan based on effect
    if effect == "zoom_in":
        zp = f"zoompan=z='1+0.002*in':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    elif effect == "zoom_out":
        zp = f"zoompan=z='1.3-0.002*in':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    elif effect == "pan_left":
        zp = f"zoompan=z='1.15':d={frames}:x='iw*0.15*(1-in/{frames})':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    elif effect == "pan_right":
        zp = f"zoompan=z='1.15':d={frames}:x='iw*0.15*in/{frames}':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    else:  # zoom_punch - quick zoom in then settle
        zp = f"zoompan=z='if(lt(in,8),1+0.04*in,1.3-0.001*(in-8))':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"

    # Text formatting
    wrapped = "\\n".join(textwrap.wrap(text, width=20))
    wrapped = wrapped.replace("'", "").replace(":", " ").replace('"', '').replace('%', ' percent')
    
    # Motion blur on transitions (first and last few frames)
    # Using tblend for motion blur effect
    vf = (
        f"scale=1200:2134,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
        f"{zp},"
        f"eq=brightness=0.03:saturation=1.3,"
        f"drawtext=text='{wrapped}':"
        f"fontcolor=white:fontsize=58:x=(w-text_w)/2:y=h*0.72:"
        f"font=monospace:borderw=4:bordercolor=black:"
        f"box=1:boxcolor=black@0.35:boxborderw=18:"
        f"enable='between(t,0.3,{seg_dur-0.2})',"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={seg_dur-0.25}:d=0.25"
    )

    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", str(seg_dur),
        "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30", seg_path], capture_output=True)
    return seg_path

def add_shake_and_blur(video_path, output_path):
    """Add subtle camera shake + motion blur to final video for that edit feel"""
    # Generate shake data - subtle random movement
    shake_vf = (
        "crop=in_w-20:in_h-20:"
        "'10+2*sin(t*12)+1*sin(t*7.5)':"  # x shake
        "'10+2*cos(t*9)+1*cos(t*13)',"     # y shake  
        "scale=1080:1920,"
        "minterpolate=fps=30:mi_mode=blend:mc_mode=obmc:vsbmc=1"  # motion blur via frame blending
    )
    
    # Simpler shake that's more reliable
    shake_vf_simple = (
        "crop=in_w-16:in_h-16:"
        "'8+3*sin(t*11)+2*sin(t*6)':"
        "'8+3*cos(t*8)+2*cos(t*14)',"
        "scale=1080:1920"
    )
    
    result = subprocess.run(["ffmpeg", "-y", "-i", video_path,
        "-vf", shake_vf_simple,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy", output_path], capture_output=True, text=True)
    
    if result.returncode != 0:
        # If shake fails, just copy
        shutil.copy2(video_path, output_path)

def main():
    print("🎬 Real Edit Short - Motion + Shake + Zoom Punches")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    # 1. Script
    print("📝 Generating script...")
    topic, script, keywords = generate_script()
    print(f"  Topic: {topic}")

    # 2. Images
    print("🖼️  Downloading images...")
    images = download_images(keywords)
    print(f"  Got {len(images)} images")

    # 3. Audio
    print("🔊 Generating voiceover...")
    audio_path = os.path.join(TEMP_DIR, "audio.mp3")
    asyncio.run(generate_audio(script, audio_path))
    duration = get_duration(audio_path)
    print(f"  Audio: {duration:.1f}s")

    # 4. Create segments with effects
    print("🎥 Creating segments with effects...")
    n = len(images)
    seg_dur = duration / n
    words = script.split()
    wps = max(1, len(words) // n)
    
    segs = []
    for i, img in enumerate(images):
        start = i * wps
        end = start + wps if i < n - 1 else len(words)
        text = " ".join(words[start:end])
        seg = create_segment(img, seg_dur, text, i, n)
        segs.append(seg)
        print(f"  Seg {i+1}/{n} done")

    # 5. Concat with crossfade (not slide - actual dissolve/wipe)
    print("🔗 Merging with crossfade...")
    count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")]) + 1
    merged_path = os.path.join(TEMP_DIR, "merged.mp4")
    
    if len(segs) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", segs[0], "-i", audio_path,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
            "-t", str(duration), "-shortest", merged_path], capture_output=True)
    else:
        # Build xfade with dissolve/wipe transitions (not basic slide)
        inputs = []
        for s in segs:
            inputs += ["-i", s]
        inputs += ["-i", audio_path]

        fade_dur = 0.3
        xfade_types = ["dissolve", "circlecrop", "radial", "smoothleft", "smoothright"]
        fc_parts = []
        for i in range(len(segs) - 1):
            offset = seg_dur * (i + 1) - fade_dur
            if offset < 0.1:
                offset = 0.1
            src1 = f"[{i}:v]" if i == 0 else f"[v{i}]"
            out = f"[v{i+1}]" if i < len(segs) - 2 else "[outv]"
            xtype = random.choice(xfade_types)
            fc_parts.append(f"{src1}[{i+1}:v]xfade=transition={xtype}:duration={fade_dur}:offset={offset:.2f}{out}")

        fc = ";".join(fc_parts)
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", fc,
            "-map", "[outv]", "-map", f"{len(segs)}:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-t", str(duration), "-shortest", merged_path]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            # fallback simple concat + audio
            concat_file = os.path.join(TEMP_DIR, "concat.txt")
            with open(concat_file, "w") as f:
                for s in segs:
                    f.write(f"file '{s}'\n")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                "-i", audio_path, "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-c:a", "aac", "-t", str(duration), "-shortest", merged_path],
                capture_output=True)

    # 6. Add camera shake
    print("📸 Adding camera shake...")
    final_path = os.path.join(OUTPUT_DIR, f"short_{count}.mp4")
    add_shake_and_blur(merged_path, final_path)

    # 7. Save metadata
    with open(final_path.replace(".mp4", ".txt"), "w") as f:
        f.write(f"Topic: {topic}\nKeywords: {', '.join(keywords)}\n\n{script}")

    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"✅ Done: {final_path}")
    return final_path, topic, script, keywords

if __name__ == "__main__":
    main()
