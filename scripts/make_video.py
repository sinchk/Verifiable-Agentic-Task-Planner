#!/usr/bin/env python3
"""Assemble recorded frames into an MP4.  usage: make_video.py <frames_dir> <out.mp4> [speedup=4] [fps=20]
Adds a short title card and a closing card. H.264 if the local OpenCV supports it, else MPEG-4."""
import sys
from pathlib import Path

import cv2
import numpy as np

src, out = Path(sys.argv[1]), Path(sys.argv[2])
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
fps = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
frames = sorted(src.glob("frame_*.jpg"))
assert frames, "no frames"
first = cv2.imread(str(frames[0]))
h, w = first.shape[:2]

writer = None
for codec in ("avc1", "H264", "mp4v"):
    wr = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*codec), fps, (w, h))
    if wr.isOpened():
        writer, used = wr, codec
        break
assert writer, "no usable codec"


def card(lines, secs):
    img = np.full((h, w, 3), (30, 24, 18), np.uint8)
    y = h // 2 - 40 * len(lines) // 2
    for i, (txt, scale, col) in enumerate(lines):
        (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, scale, 2)
        cv2.putText(img, txt, ((w - tw) // 2, y + i * 58), cv2.FONT_HERSHEY_DUPLEX, scale, col, 2, cv2.LINE_AA)
    for _ in range(int(secs * fps)):
        writer.write(img)


card([("Verifiable Agentic Task Planner", 1.5, (255, 255, 255)),
      ("LLM-to-BehaviorTree synthesis, validated before execution", 0.9, (255, 200, 130)),
      ("Real Gazebo Harmonic run - planner: offline reference (no LLM)", 0.75, (190, 190, 190))], 3.0)
step = max(1, int(round(speed * fps / 4.0)))   # recorded at 4 fps; speedup applied by frame skipping
for i, f in enumerate(frames):
    if i % max(1, int(round(4.0 / (fps / speed)))) == 0:
        writer.write(cv2.imread(str(f)))
card([("Obstacle appeared mid-mission", 1.1, (255, 255, 255)),
      ("detected -> re-perceived -> validated patch -> recovered", 0.9, (130, 230, 140)),
      ("github.com/sinchk/Verifiable-Agentic-Task-Planner", 0.8, (190, 190, 190))], 3.5)
writer.release()
print(f"{out} codec={used} frames_in={len(frames)} size={out.stat().st_size/1e6:.1f} MB")
