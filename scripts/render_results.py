#!/usr/bin/env python3
"""Results overview from the REAL benchmark files. usage: render_results.py <run1.json> <run2.json> <out.png>"""
import json
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

r1 = {r["id"]: r for r in json.load(open(sys.argv[1]))}
r2 = {r["id"]: r for r in json.load(open(sys.argv[2]))}
ids = sorted(r2)
G, R, INK, MUTE = "#2e9e5b", "#d6453d", "#1f2a37", "#6b7280"
FAULT = {"none": "#6c8ebf", "obstacle_spawn": "#d6794c", "grasp_fail": "#b5a33a", "nav_block": "#8a63b5", "place_fail": "#4aa070"}

fig = plt.figure(figsize=(16, 9), facecolor="white")
fig.text(0.04, 0.945, "Gazebo benchmark: 20 randomised scenarios, 5 fault types", fontsize=22, fontweight="bold", color=INK)
fig.text(0.04, 0.91, "Real runs - Gazebo Harmonic + Nav2 + physical grasping - planner: offline reference (no LLM)", fontsize=13, color=MUTE)

# KPI tiles
def tile(x, big, small, col):
    ax = fig.add_axes([x, 0.74, 0.21, 0.13]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.0,rounding_size=0.06", fc="#f4f6f8", ec="none", transform=ax.transAxes))
    ax.text(0.06, 0.5, big, fontsize=34, fontweight="bold", color=col, va="center", transform=ax.transAxes)
    ax.text(0.06, 0.12, small, fontsize=12, color=MUTE, transform=ax.transAxes)
s2 = sum(r["success"] for r in r2.values()); s1 = sum(r["success"] for r in r1.values())
f2 = sum(r["recovered_from_fault"] for r in r2.values() if r["fault"] != "none")
f1 = sum(r["recovered_from_fault"] for r in r1.values() if r["fault"] != "none")
nf = sum(1 for r in r2.values() if r["fault"] != "none")
tile(0.04, f"{s2}/20", f"missions succeeded (run 1: {s1}/20)", G)
tile(0.275, f"{f2}/{nf}", f"injected faults recovered (run 1: {f1}/{nf})", G)
tile(0.51, str(sum(r["safety_violations"] for r in r2.values())), "geofence / safety violations", G)
tile(0.745, f"{sum(r['first_attempt_valid'] for r in r2.values())}/20", "plans valid on first attempt", "#4f6bed")

# outcome matrix
ax = fig.add_axes([0.05, 0.08, 0.30, 0.58])
for i, k in enumerate(ids):
    for j, rr in enumerate((r1, r2)):
        r = rr[k]
        ax.add_patch(plt.Rectangle((j, -i), 0.92, 0.82, fc=G if r["success"] else R, ec="none"))
        ax.text(j + 0.46, -i + 0.41, f"{r['replans']} replan" + ("s" if r["replans"] != 1 else "") if r["replans"] else "", ha="center", va="center", color="white", fontsize=9)
    ax.add_patch(plt.Rectangle((-0.35, -i), 0.18, 0.82, fc=FAULT[r2[k]["fault"]], ec="none"))
    ax.text(-0.45, -i + 0.41, k, ha="right", va="center", fontsize=10, color=INK)
ax.set_xlim(-1.2, 2); ax.set_ylim(-19.2, 1); ax.axis("off")
ax.text(0.46, 1.2, "run 1", ha="center", fontsize=12, fontweight="bold", color=INK)
ax.text(1.46, 1.2, "run 2", ha="center", fontsize=12, fontweight="bold", color=INK)
ax.text(0.46, 2.1, "before / after carry fixes", ha="center", fontsize=10, color=MUTE)
ax.text(-1.2, -20.4, "bar colour = injected fault   green = success   red = failure", fontsize=10, color=MUTE)

# wall time by fault
ax2 = fig.add_axes([0.45, 0.10, 0.25, 0.54])
by = defaultdict(list)
for r in r2.values():
    by[r["fault"]].append(r["wall_s"])
names = sorted(by, key=lambda k: sum(by[k]) / len(by[k]))
ax2.barh(names, [sum(by[k]) / len(by[k]) for k in names], color=[FAULT[k] for k in names])
for i, k in enumerate(names):
    ax2.text(sum(by[k]) / len(by[k]) + 6, i, f"{sum(by[k]) / len(by[k]):.0f}s  (n={len(by[k])})", va="center", fontsize=10, color=INK)
ax2.set_title("mean mission time by fault (run 2)", fontsize=13, color=INK, loc="left")
for sp in ("top", "right"):
    ax2.spines[sp].set_visible(False)
ax2.set_xlim(0, 560); ax2.tick_params(labelsize=10)

# BT size
ax3 = fig.add_axes([0.77, 0.10, 0.20, 0.54])
rp = [r for r in r2.values() if r["replans"]]
ax3.barh([r["id"] for r in rp], [r["initial_nodes"] for r in rp], color="#6c8ebf", label="initial plan")
ax3.barh([r["id"] for r in rp], [r["final_nodes"] - r["initial_nodes"] for r in rp], left=[r["initial_nodes"] for r in rp], color="#d6794c", label="added by replanning")
ax3.set_title("tree size where replanning ran", fontsize=13, color=INK, loc="left")
ax3.legend(fontsize=9, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=2)
for sp in ("top", "right"):
    ax3.spines[sp].set_visible(False)
ax3.tick_params(labelsize=9)
fig.savefig(sys.argv[3], dpi=110)
print(sys.argv[3])
