#!/usr/bin/env python3
"""Numbers an independent review asked for, from the existing bundles and LLM answers only.

    python3 review_stats.py > review.json

P1  recall over ALL observed calls (not only named items), a mutually exclusive decomposition of
    every call the static union misses, pooled and by repository median, and a reflection test:
    is the union's miss rate higher when the CALLER contains a reflective construct?
P4  the LLM sample: base rate of observed calls, and how much of it qualified only because the
    static tools were wrong about it (resolve.hard's third clause).
P7  the serving-model strings recorded with every LLM answer.
"""
import ast
import json
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

H = Path(os.environ.get("TW_HARNESS", Path.home() / "traceweave-harness"))
sys.path.insert(0, str(H))
os.chdir(H)
import bench     # noqa: E402
import resolve   # noqa: E402
import sandbox   # noqa: E402
from context import own_lines  # noqa: E402
from graph import ENTRY, Bundle  # noqa: E402

DUNDER = re.compile(r"^__\w+__$")
REFLECT_NAMES = {"getattr", "setattr", "hasattr", "delattr"}


def reflective_lines(path: Path) -> set[int]:
    """Lines holding a reflective construct: non-literal getattr-family, eval/exec, dynamic import."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name in REFLECT_NAMES and len(n.args) >= 2 and not (
                isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str)):
            out.add(n.lineno)
        elif name in ("eval", "exec", "__import__", "import_module"):
            out.add(n.lineno)
    return out


def tally(its, f):
    tp = sum(1 for i in its if i["label"] and f(i))
    fp = sum(1 for i in its if not i["label"] and f(i))
    fn = sum(1 for i in its if i["label"]) - tp
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "n": len(its), "precision": p, "recall": r}


out = {"repos": {}, "pooled": {}, "decomp": Counter(), "unnamed_found_by_union": 0, "self_call_items": 0,
       "reflect": Counter(), "served_by": Counter(), "sample": Counter()}
pool = Counter()
for name in sorted(p.parent.name for p in (H / "bundles").glob("*/truth.json")):
    b = Bundle(name)
    t = json.loads((b.dir / "truth.json").read_text())
    obs = {(e[0], e[1]) for e in t["edges"]
           if e[0] != ENTRY and e[0] != e[1] and b.nodes[e[1]]["kind"] in ("function", "method")}
    its = bench.items(b)
    by_key = {(i["caller"], i["callee"]): i for i in its}
    out["self_call_items"] += sum(1 for i in its if i["label"] and i["caller"] == i["callee"])
    union = b.static
    tools = {"pycg": b.static_by_tool.get("pycg", set()), "pyright": b.static_by_tool.get("pyright", set()), "union": union}
    for k, es in tools.items():
        pool[f"{k}_found"] += len(obs & es)
    pool["observed"] += len(obs)
    root = sandbox.root(b.repo)
    refl = {}
    dec = Counter()
    for pair in obs:
        caller, callee = pair
        found = pair in union
        it = by_key.get(pair)
        if it is not None:
            cat = f"{it['style']}/{'shared' if it['shared'] > 1 else 'unique'}"
        else:
            cat = "unnamed/" + ("dunder" if DUNDER.match(b.nodes[callee]["qualname"].rsplit(".", 1)[-1]) else "other")
            if found:
                out["unnamed_found_by_union"] += 1
        if not found:
            dec[cat] += 1
        # reflection test: does the caller's own body contain a reflective construct?
        if caller not in refl:
            n = b.nodes[caller]
            refl[caller] = bool(own_lines(b, caller) & reflective_lines(root / n["path"]))
        out["reflect"][f"{'reflective' if refl[caller] else 'plain'}/{'found' if found else 'missed'}"] += 1
    out["decomp"].update(dec)
    nmiss = sum(dec.values())
    out["repos"][name] = {"observed": len(obs), "missed": nmiss,
                          "shares": {c: v / nmiss for c, v in dec.items()} if nmiss else {}}
    # P4: the LLM sample
    if (H / "results" / "resolve" / f"{name}.sample.json").exists():
        sample = set(resolve.sample(b, its))
        llm = resolve.answers(b)
        sitems = [i for i in its if i["caller"] in sample]
        by_caller = defaultdict(list)
        for i in sitems:
            by_caller[i["caller"]].append(i)
        static_only = {c for c, xs in by_caller.items()
                       if not any(i["shared"] > 1 or i["style"] == "reference" for i in xs)}
        s = out["sample"]
        s["callers"] += len(by_caller)
        s["callers_static_wrong_only"] += len(static_only)
        s["items"] += len(sitems)
        s["items_observed"] += sum(i["label"] for i in sitems)
        keep = [i for i in sitems if i["caller"] not in static_only]
        for label, xs in (("all", sitems), ("without_static_wrong_only", keep)):
            for k, v in tally(xs, lambda i: i["pycg"] or i["pyright"]).items():
                if k in ("tp", "fp", "fn", "n"):
                    s[f"{label}/static/{k}"] += v
            for m, got in llm.items():
                done = [i for i in xs if i["caller"] in got]
                for k, v in tally(done, lambda i, got=got: i["callee"] in got.get(i["caller"], ())).items():
                    if k in ("tp", "fp", "fn", "n"):
                        s[f"{label}/{m.split('/')[-1]}/{k}"] += v
                # static on exactly the items this model answered
                for k, v in tally(done, lambda i: i["pycg"] or i["pyright"]).items():
                    if k in ("tp", "fp", "fn", "n"):
                        s[f"{label}/static_on_{m.split('/')[-1]}/{k}"] += v
    # P7: what the API says served each answer
    for f in (H / "results" / "resolve").glob(f"{name}.groq_*.jsonl"):
        for line in f.open():
            r = json.loads(line)
            out["served_by"][f"{r.get('model')} -> {(r.get('model_meta') or {}).get('served_by')}"] += 1

out["pooled"] = {k: pool[f"{k}_found"] / pool["observed"] for k in ("pycg", "pyright", "union")} | {"observed": pool["observed"]}
tot = sum(out["decomp"].values())
out["decomp_pct"] = {c: v / tot for c, v in out["decomp"].items()}
cats = sorted(out["decomp"])
out["decomp_repo_median"] = {c: st.median(r["shares"].get(c, 0.0) for r in out["repos"].values() if r["missed"])
                             for c in cats}
json.dump({k: (dict(v) if isinstance(v, Counter) else v) for k, v in out.items()}, sys.stdout, indent=1, default=dict)
print()
