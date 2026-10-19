#!/usr/bin/env python3
"""Leave-one-repository-out combiner predictions, one JSON line per item, for paired comparisons.

collect.py scores LORO but keeps only pooled and per-repo F1; a paired bootstrap over repositories
needs every item's out-of-fold probability. Same data and model as collect.py (ml.rows, ml.cross_val
with one fold per repository).

    python3 loro.py all   > loro_all.jsonl      # every repo every LLM answered
    python3 loro.py noref > loro_noref.jsonl    # without click and toolz (the combiner was tuned on them)
"""
import json
import os
import sys
from pathlib import Path

H = Path(os.environ.get("TW_HARNESS", Path.home() / "traceweave-harness"))
sys.path.insert(0, str(H))
os.chdir(H)
import ml       # noqa: E402
import resolve  # noqa: E402
from graph import Bundle  # noqa: E402

repos = sorted(p.parent.name for p in (H / "bundles").glob("*/truth.json"))
full = [n for n in repos if all(m in resolve.answers(Bundle(n)) for m in ml.LLMS)]
if sys.argv[1] == "noref":
    full = [n for n in full if n not in ("click", "toolz")]
data = ml.rows(full)
for d in data:
    d["group"] = d["repo"]
probs = ml.cross_val(data, k=len(full))
for d, p in zip(data, probs):
    i = d["item"]
    print(json.dumps({"repo": d["repo"], "caller": i["caller"], "callee": i["callee"], "label": bool(i["label"]),
                      "pycg": bool(i["pycg"]), "pyright": bool(i["pyright"]), "votes": d["votes"], "p": round(p, 5)}))
