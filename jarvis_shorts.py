#!/usr/bin/env python3
"""Jarvis YouTube Shorts Generator — Clean, Professional, Halal Educational Content
Uses: Groq (script) + edge-tts (voice+timestamps) + Pexels (video clips) + ffmpeg
"""

import os, asyncio, json, subprocess, random, requests, textwrap, shutil, re, time
from datetime import datetime
from groq import Groq

OUTPUT_DIR = os.path.expanduser("~/jarvis_shorts")
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

TOPICS = [
    "space and astronomy", "human body facts", "deep ocean creatures",
    "ancient civilizations", "animal intelligence", "physics in daily life",
    "inventions that changed history", "how memory works",
    "mathematics in nature", "engineering marvels", "future technology",
    "weather phenomena", "nutrition science", "history of computing",
    "brain functions", "famous architects", "electricity explained",
    "volcanic eruptions", "black holes", "DNA and genetics",
    "speed of light", "dinosaur facts", "artificial intelligence",
    "quantum physics simplified", "renewable energy", "psychology facts",
    "how the internet works", "mysteries of the universe", "human evolution",
    "famous experiments in science"
]

SYSTEM_PROMPT = """You are writing a YouTube Shorts script (voiceover narration).
Rules:
- HALAL content only: educational, beneficial, truthful
- 45-55 seconds when spoken (~110-125 words)
- Start with a HOOK: a mind-blowing fact or provocative question
- Use simple, punchy sentences. Short sentences hit harder.
- Build curiosity through the middle
- End with a satisfying conclusion or call-to-think
- Write in ALL LOWERCASE (the video editor handles formatting)
- No "hey guys", no "subscribe", no filler
- Output ONLY the narration text

After the script, add --- then 5 video search terms (for stock footage, not images):
[script]
---
term1
term2
term3
term4
term5"""


def generate_script():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    topic = random.choice(TOPICS)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Create a viral YouTube Short about: {topic}"}
        ],
        temperature=0.85, max_tokens=350
    )
    text = response.choices[0].message.content.strip()
    if "---" in text:
        script, kw_block = text.split("---", 1)
        keywords = [k.strip() for k in kw_block.strip().split("\n") if k.strip()]
    else:
        script = text
        keywords = [topic, f"{topic} closeup", "science", "nature cinematic", "technology"]
    # Clean up script text
    script = clean_script(script.strip())
    return topic, script, keywords[:5]


def clean_script(text):
    """Normalize text — consistent sentence case, clean punctuation."""
    # Remove any markdown, asterisks, quotes
    text = re.sub(r'[*#""]', '', text)
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    cleaned = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        # Sentence case: capitalize first letter, rest lowercase (except proper nouns — keep I, names)
        s = s[0].upper() + s[1:]
        cleaned.append(s)
    return " ".join(cleaned)


def download_videos(keywords, count=5):
    """Download portrait video clips from Pexels for backgrounds."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    clips = []
    for i, kw in enumerate(keywords[:count]):
        clip_path = os.path.join(TEMP_DIR, f"clip_{i}.mp4")
        if PEXELS_KEY:
            try:
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": PEXELS_KEY},
                    params={"query": kw, "per_page": 5, "orientation": "portrait", "size": "medium"}
                )
                data = r.json()
                if data.get("videos"):
                    video = random.choice(data["videos"][:5])
                    # Get HD file
                    files = video.get("video_files", [])
                    hd = [f for f in files if f.get("height", 0) >= 1080 and f.get("width", 0) <= f.get("height", 0)]
                    if not hd:
                        hd = [f for f in files if f.get("height", 0) >= 720]
                    if not hd:
                        hd = files
                    if hd:
                        url = hd[0]["link"]
                        vid_data = requests.get(url).content
                        with open(clip_path, "wb") as f:
                            f.write(vid_data)
                        clips.append(clip_path)
                        continue
            except Exception as e:
                print(f"  Pexels video error for '{kw}': {e}")
        # Fallback: dark animated gradient
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=#0a0a1a:s=1080x1920:d=12,format=yuv420p",
            "-c:v", "libx264", "-t", "12", clip_path
        ], capture_output=True)
        clips.append(clip_path)
    return clips


async def generate_audio_with_timestamps(script, audio_path, subs_path):
    """Generate TTS audio and word-level timestamps for synced captions."""
    import edge_tts
    communicate = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="+0%")
    subs = []
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                subs.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 10_000_000,  # convert to seconds
                    "duration": chunk["duration"] / 10_000_000
                })
    # Group words into caption lines (3-5 words each)
    lines = []
    group = []
    group_start = 0
    for i, w in enumerate(subs):
        if not group:
            group_start = w["start"]
        group.append(w["text"])
        # Break every 4 words or at punctuation
        if len(group) >= 4 or w["text"].rstrip()[-1:] in ".!?,;:":
            lines.append({
                "text": " ".join(group),
                "start": group_start,
                "end": w["start"] + w["duration"]
            })
            group = []
    if group:
        lines.append({
            "text": " ".join(group),
            "start": group_start,
            "end": subs[-1]["start"] + subs[-1]["duration"]
        })
    # Write ASS subtitle file (styled)
    write_ass_subs(lines, subs_path)
    return lines


def write_ass_subs(lines, path):
    """Write professional-looking ASS subtitles — centered, bold, with outline."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w") as f:
        f.write(header)
        for line in lines:
            start = format_ass_time(line["start"])
            end = format_ass_time(line["end"])
            # Clean text for ASS format
            text = line["text"].replace("\n", "\\N")
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def get_duration(file_path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", file_path],
        capture_output=True, text=True
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def create_video(clips, audio_path, subs_path, video_path, duration):
    """Create final video with background clips, smooth transitions, and burned-in captions."""
    n = len(clips)
    seg_dur = duration / n

    # Build input list and concat with crossfade
    inputs = []
    filter_parts = []

    for i, clip in enumerate(clips):
        inputs += ["-i", clip]
        # Scale and crop each clip to 1080x1920, trim to segment duration
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30,"
            f"trim=0:{seg_dur + 1},setpts=PTS-STARTPTS[v{i}]"
        )

    # Crossfade clips together
    if n == 1:
        filter_parts.append(f"[v0]null[merged]")
    elif n == 2:
        offset = max(0.1, seg_dur - 0.5)
        filter_parts.append(f"[v0][v1]xfade=transition=fade:duration=0.5:offset={offset:.2f}[merged]")
    else:
        # Chain crossfades
        offset = max(0.1, seg_dur - 0.5)
        filter_parts.append(f"[v0][v1]xfade=transition=fade:duration=0.5:offset={offset:.2f}[xf0]")
        for i in range(2, n):
            offset = max(0.1, seg_dur * i - 0.5 * i)
            out = "[merged]" if i == n - 1 else f"[xf{i-1}]"
            filter_parts.append(f"[xf{i-2}][v{i}]xfade=transition=fade:duration=0.5:offset={offset:.2f}{out}")

    # Burn subtitles
    filter_parts.append(f"[merged]ass='{subs_path}'[outv]")

    filter_complex = ";".join(filter_parts)
    inputs += ["-i", audio_path]

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", f"{n}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration), "-shortest",
        "-movflags", "+faststart",
        video_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️ Complex render failed, trying simple version...")
        print(f"  Error: {result.stderr[-300:]}")
        create_simple_video(clips, audio_path, subs_path, video_path, duration)


def create_simple_video(clips, audio_path, subs_path, video_path, duration):
    """Fallback: single background clip with subtitles."""
    clip = clips[0]
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", clip,
        "-i", audio_path,
        "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,ass='{subs_path}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration), "-shortest",
        "-movflags", "+faststart",
        video_path
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def main():
    print("🎬 Jarvis Shorts Generator v2 — Clean & Professional")
    print("=" * 55)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Generate script
    print("📝 Generating script...")
    topic, script, keywords = generate_script()
    print(f"   Topic: {topic}")
    print(f"   Script: {script[:100]}...")
    print(f"   Search terms: {keywords}\n")

    # 2. Download video clips (not images)
    print("🎥 Downloading background footage...")
    clips = download_videos(keywords)
    print(f"   Got {len(clips)} clips\n")

    # 3. Generate audio + word timestamps
    print("🔊 Generating voiceover with timestamps...")
    os.makedirs(TEMP_DIR, exist_ok=True)
    audio_path = os.path.join(TEMP_DIR, "audio.mp3")
    subs_path = os.path.join(TEMP_DIR, "subs.ass")
    asyncio.run(generate_audio_with_timestamps(script, audio_path, subs_path))
    duration = get_duration(audio_path)
    print(f"   Audio: {duration:.1f}s with word-synced captions\n")

    # 4. Create video
    print("🎬 Rendering final video...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(OUTPUT_DIR, f"short_{timestamp}.mp4")
    create_video(clips, audio_path, subs_path, video_path, duration)
    print(f"   ✅ Saved: {video_path}\n")

    # 5. Save metadata
    meta = {"topic": topic, "script": script, "keywords": keywords, "duration": duration}
    meta_path = os.path.join(OUTPUT_DIR, f"short_{timestamp}.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Cleanup
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"📱 Ready to upload! Duration: {duration:.1f}s")


if __name__ == "__main__":
    main()
