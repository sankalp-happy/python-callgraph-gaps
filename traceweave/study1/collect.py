#!/usr/bin/env python3
"""Pool Study 1 over every traced repo into one JSON file for the paper (paper/make_numbers.py).

Run from anywhere on the host that holds the harness; reads only bundles/ and results/:

    python3 collect.py > rq34.json

Per repo and pooled: edge recall of each static tool against the traced calls, item scores on all
items and on the LLM sample, where the union misses, and the combiner scored two ways (folds
grouped by caller, as the harness does, and leave-one-repo-out).
"""
import ast
import csv
import random
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
pool_all, pool_strat, llm_pool, llm_repo, llm_cat, static_cat, llm_comp = {}, {}, {}, {}, {}, {}, {}


def coverage(b, truth) -> float | None:
    """Executed package lines / statement lines in the package's .py files (AST, so no blanks or comments)."""
    root = H / "work" / b.name
    pkg = root / b.repo["package"]
    total = ran = 0
    ran_by = {p: set(v) for p, v in truth["lines"].items()}
    for f in (pkg.rglob("*.py") if pkg.is_dir() else []):
        try:
            tree = ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        stmts = {n.lineno for n in ast.walk(tree) if isinstance(n, ast.stmt)}
        total += len(stmts)
        ran += len(stmts & ran_by.get(str(f.relative_to(root)), set()))
    return round(ran / total, 4) if total else None


def spearman(x, y):
    rank = lambda v: {i: r for r, i in enumerate(sorted(range(len(v)), key=v.__getitem__))}
    rx, ry = rank(x), rank(y)
    n = len(x)
    return round(1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1)), 3) if n > 2 else None


def bootstrap(per_repo: dict, reps: int = 1000, seed: int = 20261019) -> dict:
    """Repository-cluster bootstrap: resample whole repos, pool their tallies, 95% percentile CI."""
    names, rnd, out = sorted(per_repo), random.Random(seed), {"precision": [], "recall": [], "f1": []}
    for _ in range(reps):
        t = {"tp": 0, "fp": 0, "fn": 0, "n": 0}
        for n in (rnd.choice(names) for _ in names):
            t = add(t, {k: per_repo[n][k] for k in t})
        s = prf(t)
        for k in out:
            out[k].append(s[k])
    return {k: [round(sorted(v)[int(0.025 * reps)], 3), round(sorted(v)[int(0.975 * reps) - 1], 3)] for k, v in out.items()}
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
           "items": len(its), "real": sum(i["label"] for i in its), "unnamed": unnamed, "scores": {},
           "tests_passed": truth["suite"].get("passed"), "line_coverage": coverage(b, truth)}
    run2 = b.dir / "truth.run2.json"                 # repeat trace: is the observed-call set stable?
    if run2.exists():
        t2 = json.loads(run2.read_text())
        obs2 = {(e[0], e[1]) for e in t2["edges"]
                if e[0] != ENTRY and e[0] != e[1] and b.nodes[e[1]]["kind"] in ("function", "method")}
        row["retrace"] = {"jaccard": round(len(observed & obs2) / len(observed | obs2), 4) if observed | obs2 else None,
                          "only_first": len(observed - obs2), "only_second": len(obs2 - observed)}
    for k, f in STATIC.items():
        t = tally(its, f)
        row["scores"][k] = prf(t)
        pool_all[k] = add(pool_all.get(k, {}), t)
        key = (row["stratum"], k)
        pool_strat[key] = add(pool_strat.get(key, {}), t)
    row["scores"]["shared-name union"] = prf(tally([i for i in its if i["shared"] > 1], STATIC["PyCG ∪ Pyright"]))
    for i in its:                                   # every static resolver by kind of item, on all items
        cat = f"{i['style']}/{'shared' if i['shared'] > 1 else 'unique'}"
        for k in ("PyCG", "Pyright", "PyCG ∪ Pyright"):
            c = static_cat.setdefault(cat, {})
            c[k] = add(c.get(k, {}), tally([i], STATIC[k]))
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
        says = {"model": lambda i, got=got: i["callee"] in got.get(i["caller"], ()),
                "static union, same items": STATIC["PyCG ∪ Pyright"]}
        for k, f in says.items():
            llm_pool[m][k] = add(llm_pool[m].get(k, {}), tally(done, f))
        llm_pool[m].setdefault("repos", []).append(name)
        # per repo, and per kind of item (how the name is written x shared or unique)
        llm_repo.setdefault(m, {})[name] = {k: prf(tally(done, f)) for k, f in says.items()}
        for part, keep in (("static missed", lambda i: not (i["pycg"] or i["pyright"])),
                           ("static found", lambda i: i["pycg"] or i["pyright"])):   # complementarity
            c = llm_comp.setdefault(m, {})
            c[part] = add(c.get(part, {}), tally([i for i in done if i["label"] and keep(i)], says["model"]))
        for i in done:
            cat = f"{i['style']}/{'shared' if i['shared'] > 1 else 'unique'}"
            for k, f in says.items():
                c = llm_cat.setdefault(m, {}).setdefault(cat, {})
                c[k] = add(c.get(k, {}), tally([i], f))
    out["repos"][name] = row

out["pooled"] = {k: prf(t) for k, t in pool_all.items()}
out["by_stratum"] = {f"{s}/{k}": prf(t) for (s, k), t in pool_strat.items()}
out["llm"] = {m: {k: (prf(v) if isinstance(v, dict) else v) for k, v in d.items()} for m, d in llm_pool.items()}
out["llm_by_repo"] = llm_repo
out["llm_by_kind"] = {m: {c: {k: prf(t) for k, t in d.items()} for c, d in cats.items()} for m, cats in llm_cat.items()}
out["llm_beats_static_f1"] = {m: sum(r["model"]["f1"] > r["static union, same items"]["f1"] for r in reps.values())
                              for m, reps in llm_repo.items()}
out["static_by_kind"] = {c: {k: prf(t) for k, t in d.items()} for c, d in static_cat.items()}
out["llm_complementarity"] = {m: {k: prf(t) for k, t in d.items()} for m, d in llm_comp.items()}
out["bootstrap"] = {m: {k: bootstrap({n: r[k] for n, r in reps.items()}) for k in ("model", "static union, same items")}
                    for m, reps in llm_repo.items()}
cov = [(r["line_coverage"], r["edge_recall"]["union"], r["tests_passed"]) for r in out["repos"].values()
       if r["line_coverage"] is not None and r["edge_recall"]["union"] is not None]
out["coverage_vs_recall_spearman"] = spearman([c for c, _, _ in cov], [u for _, u, _ in cov])
out["tests_vs_recall_spearman"] = spearman([t or 0 for _, _, t in cov], [u for _, u, _ in cov])
rt = [r["retrace"]["jaccard"] for r in out["repos"].values() if r.get("retrace") and r["retrace"]["jaccard"] is not None]
out["retrace"] = {"repos": len(rt), "jaccard_min": min(rt), "jaccard_median": st.median(rt)} if rt else None
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
        # leave-one-repo-out is the primary result: every resolver on the same items, pooled and per repo
        lo = {"PyCG": lambda i: i["pycg"], "Pyright": lambda i: i["pyright"],
              "PyCG ∪ Pyright": lambda i: i["pycg"] or i["pyright"],
              "majority of the 3 LLMs": lambda i: sum(i["_votes"]) >= 2,
              "static ∪ any LLM": lambda i: i["pycg"] or i["pyright"] or any(i["_votes"]),
              "learned combiner": lambda i: i["_p"] >= 0.5}
        its = [dict(d["item"], _p=p, _votes=d["votes"], _repo=d["repo"]) for d, p in zip(data, probs)]
        out["combiner"]["leave_one_repo_out"] = bench.score(its, lo["learned combiner"])
        out["combiner"]["loro_all"] = {k: bench.score(its, f) for k, f in lo.items()}
        out["combiner"]["loro_by_repo"] = {n: {k: bench.score([i for i in its if i["_repo"] == n], lo[k])["f1"]
                                               for k in ("learned combiner", "PyCG ∪ Pyright")} for n in full}
out["misses"] = dict(out["misses"])
json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
print()
