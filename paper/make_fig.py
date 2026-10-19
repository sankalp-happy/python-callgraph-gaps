#!/usr/bin/env python3
"""Fig. 1 from the same result files as numbers.tex; rerun after make_numbers.py.

    python3 paper/make_fig.py        # writes paper/fig_recall.pdf
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
reps = json.loads((ROOT / "study1-results" / "rq34.json").read_text())["repos"]
dens = {json.loads(l)["name"]: json.loads(l).get("density_score") for l in (ROOT / "candidates" / "02_scored.jsonl").open()}
dens |= {"click": 17.39, "toolz": 7.82}          # same reference-set values as make_numbers.py

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times", "Nimbus Roman", "DejaVu Serif"],
                     "font.size": 7, "pdf.fonttype": 42, "axes.linewidth": 0.5,
                     "xtick.major.width": 0.5, "ytick.major.width": 0.5})
STRATA = [("LOW", "#2a78d6", "o"), ("MED", "#eb6834", "s"), ("HIGH", "#1baf7a", "^")]
fig, (a, b) = plt.subplots(1, 2, figsize=(3.5, 1.6), constrained_layout=True)

a.plot([0, 1], [0, 1], color="#999999", lw=0.6, ls="--", zorder=0)
for s, c, m in STRATA:
    rs = [(dens[n], r["edge_recall"]) for n, r in reps.items() if r["stratum"] == s]
    kw = dict(s=12, color=c, marker=m, edgecolors="white", linewidths=0.4)
    a.scatter([e["pycg"] for _, e in rs], [e["pyright"] for _, e in rs], label=s, **kw)
    b.scatter([d for d, _ in rs], [e["union"] for _, e in rs], **kw)
a.set(xlim=(0, 1.02), ylim=(0, 1.02), xlabel="PyCG recall", ylabel="Pyright recall", title="(a)")
b.set(xlim=(-1, None), ylim=(0, 1.02), xlabel="dynamism score", ylabel="union recall", title="(b)")
a.legend(loc="lower right", frameon=False, handletextpad=0.1, borderpad=0.1, labelspacing=0.2)
for ax in (a, b):
    ax.title.set_size(7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#e5e5e5", lw=0.4)
    ax.set_axisbelow(True)
fig.savefig(ROOT / "paper" / "fig_recall.pdf")
