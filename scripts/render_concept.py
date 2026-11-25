#!/usr/bin/env python3
"""Concept figure of the LLM-driven loop. ILLUSTRATIVE ONLY - contains no measured data. usage: render_concept.py <out.png>"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

fig, ax = plt.subplots(figsize=(16, 9), facecolor="white")
ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")
INK, MUTE = "#1f2a37", "#6b7280"


def box(x, y, w, h, title, body, fc, tc="white", mono=False, fs=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=fc, ec="none"))
    ax.text(x + 0.2, y + h - 0.32, title, fontsize=13, fontweight="bold", color=tc, va="top")
    ax.text(x + 0.2, y + h - 0.85, body, fontsize=fs, color=tc, va="top", family="monospace" if mono else None, linespacing=1.45)


def arrow(a, b, label="", rad=0.0, col=MUTE):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=18, lw=2, color=col, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.22, label, fontsize=10, color=col, ha="center")


ax.text(0.4, 8.55, "Concept: how an LLM plugs into the verified planning loop", fontsize=22, fontweight="bold", color=INK)
ax.text(0.4, 8.13, "Same pipeline as the implemented system; the model is only a proposer. Example text below is schematic.", fontsize=12.5, color=MUTE)

box(0.4, 5.6, 3.6, 2.0, "1  Instruction + scene", '"Check if the loading bay is\nclear; if blocked, clear the\nsmall box, then deliver the\ncrate to Zone B."', "#4f6bed")
box(4.6, 5.6, 3.6, 2.0, "2  RAG memory", "SC-01 geofence keep-out\nSC-03 one object at a time\nRP-01 unexpected obstacle\nRP-02 grasp failed ...", "#8a63b5")
box(8.8, 5.6, 3.4, 2.0, "3  LLM (proposer)", "schema-constrained JSON:\nnodes: Sequence, Fallback,\nNavigateTo, PickObject ...\ngoals: object_at(crate, zone_b)", "#c9533d")
box(12.7, 5.6, 2.9, 2.0, "4  Validator", "no model inside\nstructure | ports |\nsymbolic execution | goals", "#2e9e5b")
arrow((4.0, 6.6), (4.6, 6.6)); arrow((8.2, 6.6), (8.8, 6.6)); arrow((12.2, 6.6), (12.7, 6.6))

box(8.8, 2.9, 6.8, 2.1, "5  Validator verdict (example message format)",
    "[ERROR GEOFENCE_PATH @n9] straight path zone_a->zone_b\n        crosses keep-out 'restricted_aisle'; route via loading_bay\n-> repair prompt sent back to the LLM  ->  re-validate", "#fbe9e7", tc="#7f1d1d", mono=True, fs=9)
arrow((14.1, 5.6), (14.1, 5.0), "rejected", col="#b71c1c")
arrow((8.8, 3.9), (10.5, 5.6), "", rad=-0.35, col="#b71c1c")

box(0.4, 2.9, 4.6, 2.1, "6  BehaviorTree.CPP XML", "only a VALIDATED plan is emitted\nSequence > Fallback(CheckZoneClear,\n  clear-the-box steps) > deliver ...", "#e8f5e9", tc="#14532d", mono=True)
arrow((13.5, 5.6), (5.0, 4.2), "validated", rad=0.12, col="#2e9e5b")

box(0.4, 0.4, 7.4, 1.9, "7  Lifecycle executor + skill servers", "BT.CPP ticks the tree -> Nav2 / arm / perception skills\nFAILURE (e.g. unexpected obstacle) -> re-perceive scene\n-> same loop returns a validated patch for the REMAINING mission", "#263248")
arrow((2.7, 2.9), (2.7, 2.3))
arrow((7.8, 1.3), (10.4, 2.9), "replan request", rad=0.25, col="#c9533d")
ax.add_patch(FancyBboxPatch((8.9, 0.35), 6.7, 1.0, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#fff3cd", ec="#b58900", lw=2))
ax.text(12.25, 0.85, "ILLUSTRATIVE CONCEPT - not measured output.\nThe Claude backend is implemented but has not been run yet.", ha="center", va="center", fontsize=11, fontweight="bold", color="#7a5b00")
fig.savefig(sys.argv[1], dpi=110, bbox_inches="tight")
print(sys.argv[1])
