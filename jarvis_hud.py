#!/usr/bin/env python3
"""J.A.R.V.I.S HUD — Lightweight Iron Man UI. Targets 60fps on low-end hardware."""
import pygame
import math
import time
import os
import threading

W, H = 1366, 768
FPS = 30  # Lock to 30fps to save CPU for voice
BG = (5, 5, 15)
CYAN = (0, 200, 240)
CYAN_DIM = (0, 60, 90)
WHITE = (180, 200, 220)
GREEN = (0, 220, 100)
ORANGE = (255, 140, 0)

sys_data = {"cpu": 0, "ram": 0, "ram_used": 0, "ram_total": 0, "uptime": ""}

def update_sys():
    while True:
        try:
            with open("/proc/stat") as f:
                l = f.readline().split()
            idle1, total1 = int(l[4]), sum(int(x) for x in l[1:])
            time.sleep(1)
            with open("/proc/stat") as f:
                l = f.readline().split()
            idle2, total2 = int(l[4]), sum(int(x) for x in l[1:])
            sys_data["cpu"] = 100 * (1 - (idle2-idle1)/(total2-total1+0.01))
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            total = int(lines[0].split()[1])
            avail = int(lines[2].split()[1])
            sys_data["ram_total"] = total // 1024
            sys_data["ram_used"] = (total - avail) // 1024
            sys_data["ram"] = 100 * (total - avail) / total
            with open("/proc/uptime") as f:
                s = int(float(f.read().split()[0]))
            sys_data["uptime"] = f"{s//3600}h {(s%3600)//60}m"
        except:
            pass
        time.sleep(2)

def get_state():
    try:
        with open("/tmp/jarvis_state") as f:
            return f.read().strip()
    except:
        return "idle"

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
    pygame.display.set_caption("J.A.R.V.I.S")
    clock = pygame.time.Clock()
    font_lg = pygame.font.SysFont("monospace", 28, bold=True)
    font_md = pygame.font.SysFont("monospace", 16)
    font_sm = pygame.font.SysFont("monospace", 13)
    font_title = pygame.font.SysFont("monospace", 38, bold=True)

    threading.Thread(target=update_sys, daemon=True).start()

    frame = 0
    running = True
    while running:
        clock.tick(FPS)
        frame += 1
        t = frame / FPS

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False

        screen.fill(BG)
        cx, cy = W // 2, H // 2

        # --- ORB: simple rotating arcs ---
        for i in range(3):
            r = 70 + i * 20
            speed = (0.8 + i * 0.4) * (1 if i % 2 == 0 else -1)
            offset = t * speed
            for j in range(3):
                start = offset + j * 2.094
                rect = pygame.Rect(cx-r, cy-r, r*2, r*2)
                pygame.draw.arc(screen, CYAN, rect, start, start + 1.2, 2)

        # Core circle
        pulse = int(30 + math.sin(t * 2) * 5)
        pygame.draw.circle(screen, CYAN, (cx, cy), pulse)
        pygame.draw.circle(screen, WHITE, (cx, cy), pulse - 10)

        # Title
        ts = font_title.render("J.A.R.V.I.S", True, CYAN)
        screen.blit(ts, (cx - ts.get_width()//2, 35))

        # Status
        state = get_state()
        sc = GREEN if state == "listening" else ORANGE if state == "speaking" else CYAN
        ss = font_md.render(f"STATUS: {state.upper()}", True, sc)
        screen.blit(ss, (cx - ss.get_width()//2, 80))

        # --- LEFT: System ---
        lx, ly = 40, 150
        screen.blit(font_md.render("SYSTEM", True, CYAN), (lx, ly))
        ly += 28
        cpu_c = GREEN if sys_data["cpu"] < 60 else ORANGE
        screen.blit(font_sm.render(f"CPU: {sys_data['cpu']:.0f}%", True, cpu_c), (lx, ly))
        pygame.draw.rect(screen, CYAN_DIM, (lx+100, ly+2, 150, 10))
        pygame.draw.rect(screen, cpu_c, (lx+100, ly+2, int(150*sys_data["cpu"]/100), 10))
        ly += 24
        ram_c = GREEN if sys_data["ram"] < 70 else ORANGE
        screen.blit(font_sm.render(f"RAM: {sys_data['ram_used']}MB/{sys_data['ram_total']}MB", True, ram_c), (lx, ly))
        pygame.draw.rect(screen, CYAN_DIM, (lx+200, ly+2, 100, 10))
        pygame.draw.rect(screen, ram_c, (lx+200, ly+2, int(100*sys_data["ram"]/100), 10))
        ly += 24
        screen.blit(font_sm.render(f"UPTIME: {sys_data['uptime']}", True, WHITE), (lx, ly))

        # Cores
        ly += 40
        screen.blit(font_md.render("NEURAL CORES", True, CYAN), (lx, ly))
        ly += 24
        for name in ["GEMINI 3.1 PRO", "CLAUDE FABLE 5", "GROQ WHISPER", "CLOUD STT/TTS"]:
            screen.blit(font_sm.render(f"● {name}", True, GREEN), (lx+10, ly))
            ly += 20

        # --- RIGHT: Revenue ---
        rx, ry = W - 340, 150
        screen.blit(font_md.render("ANALYTICS", True, CYAN), (rx, ry))
        ry += 28
        for line in ["YT Subs: --", "YT Views: --", "YT Rev: $0.00", "", "TikTok: --", "", "Cloud: $228 remaining"]:
            if line:
                screen.blit(font_sm.render(line, True, WHITE), (rx, ry))
            ry += 18

        # Project
        ry += 20
        screen.blit(font_md.render("PROJECT", True, CYAN), (rx, ry))
        ry += 26
        for name, pct in [("Voice", 85), ("TV", 90), ("Music", 70), ("Search", 95), ("Shorts", 40), ("HUD", 60)]:
            screen.blit(font_sm.render(f"{name:8s}", True, WHITE), (rx, ry))
            pygame.draw.rect(screen, CYAN_DIM, (rx+80, ry+2, 100, 10))
            pygame.draw.rect(screen, CYAN, (rx+80, ry+2, pct, 10))
            screen.blit(font_sm.render(f"{pct}%", True, CYAN), (rx+190, ry))
            ry += 20

        # Time
        now = time.strftime("%H:%M:%S")
        ts2 = font_lg.render(now, True, CYAN)
        screen.blit(ts2, (cx - ts2.get_width()//2, H - 55))
        ds = font_sm.render(time.strftime("%A, %B %d, %Y"), True, CYAN_DIM)
        screen.blit(ds, (cx - ds.get_width()//2, H - 25))

        # Corner lines
        for x1, y1, x2, y2 in [(10,10,50,10),(10,10,10,50),(W-10,10,W-50,10),(W-10,10,W-10,50),
                                 (10,H-10,50,H-10),(10,H-10,10,H-50),(W-10,H-10,W-50,H-10),(W-10,H-10,W-10,H-50)]:
            pygame.draw.line(screen, CYAN_DIM, (x1,y1), (x2,y2))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
