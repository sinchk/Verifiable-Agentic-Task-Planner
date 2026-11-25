#!/usr/bin/env python3
"""Plot benchmark metrics: python scripts/plot_results.py runs/<stamp>/metrics.json [out_dir]"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

src = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent
rows = [r for r in json.loads(src.read_text()) if "error" not in r]
ids = [r["id"] for r in rows]
colors = {"none": "#6c8ebf", "obstacle_spawn": "#d6794c", "grasp_fail": "#b5a33a",
          "nav_block": "#8a63b5", "place_fail": "#4aa070"}

fig, ax = plt.subplots(1, 3, figsize=(16, 4.2))
ax[0].bar(ids, [r["wall_s"] for r in rows], color=[colors.get(r["fault"], "gray") for r in rows])
ax[0].set_title("Mission wall time (s) — colour = injected fault")
ax[0].tick_params(axis="x", rotation=90)
for k, c in colors.items():
    ax[0].bar([], [], color=c, label=k)
ax[0].legend(fontsize=7)

ax[1].bar(ids, [r["initial_nodes"] for r in rows], label="initial plan", color="#6c8ebf")
ax[1].bar(ids, [max(0, r["final_nodes"] - r["initial_nodes"]) for r in rows],
          bottom=[r["initial_nodes"] for r in rows], label="added by replanning", color="#d6794c")
ax[1].set_title("BT node count")
ax[1].tick_params(axis="x", rotation=90)
ax[1].legend(fontsize=7)

rp = [(r["id"], r["replan_latency_s"]) for r in rows if r["replans"]]
ax[2].bar([i for i, _ in rp], [v for _, v in rp], color="#d6794c")
ax[2].set_title(f"Replanning latency (s)  [{len(rp)} replans]")
ax[2].tick_params(axis="x", rotation=90)

ok = sum(r["success"] for r in rows)
fig.suptitle(f"{src.parent.name}: {ok}/{len(rows)} missions succeeded", fontsize=11)
fig.tight_layout()
png = out / "metrics.png"
fig.savefig(png, dpi=130)
print(png)
