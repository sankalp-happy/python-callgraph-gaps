#!/usr/bin/env python3
"""Pool Study 1 over every traced repo into one JSON file for the paper (paper/make_numbers.py).

Run from anywhere on the host that holds the harness; reads only bundles/ and results/:

    python3 collect.py > rq34.json

Per repo and pooled: edge recall of each static tool against the traced calls, item scores on all
items and on the LLM sample, where the union misses, and the combiner scored two ways (folds
grouped by caller, as the harness does, and leave-one-repo-out).
"""
import csv
import json
import os
import statistics as st
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
H = Path(os.environ.get("TW_HARNESS", Path.home() / "traceweave-harness"))
sys.path.insert(0, str(H))
os.chdir(H)

import bench    # noqa: E402  (harness modules)
import ml       # noqa: E402
import resolve  # noqa: E402
from graph import ENTRY, Bundle  # noqa: E402

STRATA = {"click": "HIGH", "toolz": "MED"}   # density scorer reference set (docs/density_scorer_spec.md)
STRATA |= {r["repo"]: r["stratum"] for r in csv.DictReader(
    (l for l in (HERE / "repos.tsv").open() if not l.startswith("#")), delimiter="\t")}
STATIC = {k: f for k, f in bench.BASELINES.items() if k != "name match"} | {"name match": bench.BASELINES["name match"]}


def tally(its, f):
    tp = sum(1 for i in its if i["label"] and f(i))
    fp = sum(1 for i in its if not i["label"] and f(i))
    return {"tp": tp, "fp": fp, "fn": sum(i["label"] for i in its) - tp, "n": len(its)}


def prf(t):
    p = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else 0.0
    r = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else 0.0
    return {**t, "precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def add(a, b):
    return {k: a.get(k, 0) + b[k] for k in b}


repos = sorted(p.parent.name for p in (H / "bundles").glob("*/truth.json"))
out = {"repos": {}, "pooled": {}, "llm": {}, "misses": Counter(), "unnamed": 0, "real_items": 0}
pool_all, pool_strat, llm_pool = {}, {}, {}
for name in repos:
    b = Bundle(name)
    truth = json.loads((b.dir / "truth.json").read_text())
    # same pairs as the harness's truth_summary (studies.py): no recursion, callee a function or method
    observed = {(e[0], e[1]) for e in truth["edges"]
                if e[0] != ENTRY and e[0] != e[1] and b.nodes[e[1]]["kind"] in ("function", "method")}
    edge = {tool: round(len(observed & es) / len(observed), 3) if observed else None
            for tool, es in b.static_by_tool.items()}
    edge["union"] = round(len(observed & b.static) / len(observed), 3) if observed else None
    its = bench.items(b)
    unnamed = len(bench.unnamed(b, its))
    row = {"stratum": STRATA.get(name, "?"), "observed_edges": len(observed), "edge_recall": edge,
           "items": len(its), "real": sum(i["label"] for i in its), "unnamed": unnamed, "scores": {}}
    for k, f in STATIC.items():
        t = tally(its, f)
        row["scores"][k] = prf(t)
        pool_all[k] = add(pool_all.get(k, {}), t)
        key = (row["stratum"], k)
        pool_strat[key] = add(pool_strat.get(key, {}), t)
    row["scores"]["shared-name union"] = prf(tally([i for i in its if i["shared"] > 1], STATIC["PyCG ∪ Pyright"]))
    for i in its:                                   # what kind of line the union misses
        if i["label"] and not (i["pycg"] or i["pyright"]):
            out["misses"][f"{i['style']}/{'shared' if i['shared'] > 1 else 'unique'}"] += 1
    out["real_items"] += row["real"]
    out["unnamed"] += unnamed
    # LLMs and the static tools on the same sampled items
    llm = resolve.answers(b)
    sample = set(resolve.sample(b, its)) if (H / "results" / "resolve" / f"{name}.sample.json").exists() else set()
    for model, got in llm.items():
        done = [i for i in its if i["caller"] in sample and i["caller"] in got]
        if not done:
            continue
        m = model.split("/")[-1]
        llm_pool.setdefault(m, {})
        for k, f in [("model", lambda i, got=got: i["callee"] in got.get(i["caller"], ())),
                     ("static union, same items", STATIC["PyCG ∪ Pyright"])]:
            llm_pool[m][k] = add(llm_pool[m].get(k, {}), tally(done, f))
        llm_pool[m].setdefault("repos", []).append(name)
    out["repos"][name] = row

out["pooled"] = {k: prf(t) for k, t in pool_all.items()}
out["by_stratum"] = {f"{s}/{k}": prf(t) for (s, k), t in pool_strat.items()}
out["llm"] = {m: {k: (prf(v) if isinstance(v, dict) else v) for k, v in d.items()} for m, d in llm_pool.items()}
rec = [r["edge_recall"]["union"] for r in out["repos"].values() if r["edge_recall"]["union"] is not None]
out["edge_recall_union_median"] = round(st.median(rec), 3) if rec else None

# the combiner: only repos every LLM answered
full = [n for n in repos if all(n in d.get("repos", []) for d in llm_pool.values()) and len(llm_pool) == len(ml.LLMS)]
if full and os.environ.get("TW_COMBINER", "1") == "1":     # pure-Python fits: minutes per fold
    r = ml.report(full)
    out["combiner"] = {"repos": full, "items": r["items"], "grouped_by_caller": r["scores"], "weights": r["weights"]}
    data = ml.rows(full)
    if len(full) >= 3:                               # leave one repo out
        for d in data:
            d["group"] = d["repo"]
        probs = ml.cross_val(data, k=len(full))
        its = [dict(d["item"], _p=p) for d, p in zip(data, probs)]
        out["combiner"]["leave_one_repo_out"] = bench.score(its, lambda i: i["_p"] >= 0.5)
out["misses"] = dict(out["misses"])
json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
print()
