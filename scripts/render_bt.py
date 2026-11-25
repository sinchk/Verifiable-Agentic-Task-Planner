#!/usr/bin/env python3
"""Render behavior trees (BT.CPP XML) to a before/after figure with Graphviz.
usage: render_bt.py <initial.xml> <final.xml> <out.png> [title]"""
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CTRL = {"Sequence": "#4f6bed", "Fallback": "#c9533d", "ReactiveSequence": "#4f6bed",
        "RetryUntilSuccessful": "#8a63b5", "Timeout": "#8a63b5", "Inverter": "#8a63b5", "ForceSuccess": "#8a63b5"}
COND = {"CheckZoneClear", "CheckHolding", "CheckObjectAt"}


def load(path):
    root = ET.parse(path).getroot().find("BehaviorTree")
    return list(root)[0]


def sig(n):
    return (n.tag, tuple(sorted((k, v) for k, v in n.attrib.items() if k != "name")))


def to_dot(tree, known=None):
    lines = ["digraph BT { rankdir=TB; nodesep=0.18; ranksep=0.32; bgcolor=white;",
             'node [fontname="DejaVu Sans", fontsize=11, style="filled,rounded", shape=box, penwidth=0];',
             'edge [color="#7a8394", arrowsize=0.6];']
    cnt = [0]

    def walk(n):
        cnt[0] += 1
        me = f"n{cnt[0]}"
        args = ", ".join(f"{k}={v}" for k, v in n.attrib.items() if k != "name")
        label = n.tag if n.tag in CTRL and not args else f"{n.tag}\\n{args}"
        if n.tag in CTRL:
            fill, font, shape = CTRL[n.tag], "white", "box"
        elif n.tag in COND:
            fill, font, shape = "#ffd36b", "black", "diamond"
        else:
            fill, font, shape = "#7ed08a", "black", "box"
        new = known is not None and n.tag not in CTRL and sig(n) not in known
        if new:
            fill, font = "#ff8a65", "black"
        extra = ', penwidth=2.5, color="#b71c1c"' if new else ""
        lines.append(f'{me} [label="{label}", fillcolor="{fill}", fontcolor="{font}", shape={shape}{extra}];')
        for c in n:
            lines.append(f"{me} -> {walk(c)};")
        return me

    walk(tree)
    lines.append("}")
    return "\n".join(lines)


def render(tree, known, out):
    with tempfile.NamedTemporaryFile("w", suffix=".dot", delete=False) as f:
        f.write(to_dot(tree, known))
    subprocess.run(["dot", "-Tpng", "-Gdpi=110", f.name, "-o", str(out)], check=True)
    return Image.open(out).convert("RGB")


def main():
    a, b, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    title = sys.argv[4] if len(sys.argv) > 4 else "Behavior tree before and after recovery"
    t0, t1 = load(a), load(b)
    n0, n1 = sum(1 for _ in t0.iter()), sum(1 for _ in t1.iter())
    known = Counter(sig(n) for n in t0.iter())
    tmp = Path(tempfile.mkdtemp())
    i0, i1 = render(t0, None, tmp / "a.png"), render(t1, set(known), tmp / "b.png")
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26) if Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf").exists() else ImageFont.load_default()
    fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19) if Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf").exists() else ImageFont.load_default()
    W = max(i0.width, i1.width) + 60
    H = i0.height + i1.height + 290
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 18), title, font=f, fill="black")
    d.text((30, 58), "green = skill  |  yellow = condition  |  blue/red/purple = control & decorators  |  orange outline = new in the patched tree",
           font=fs, fill=(90, 90, 90))
    d.text((30, 108), f"1. Initial plan - validated before execution ({n0} nodes)", font=fs, fill=(20, 20, 20))
    img.paste(i0, (30 + (W - 60 - i0.width) // 2, 140))
    y1 = 140 + i0.height + 30
    d.text((30, y1), f"2. After the fault - validated patch for the REMAINING mission ({n1} nodes)", font=fs, fill=(20, 20, 20))
    img.paste(i1, (30 + (W - 60 - i1.width) // 2, y1 + 34))
    img.save(out)
    print(out, img.size)


main()
