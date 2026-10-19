#!/usr/bin/env python3
"""Mapping audit: how much of PyCG's low recall is our name mapping rather than PyCG?

PyCG emits dotted names; static/pycg_baseline.py maps them strictly onto the shared node set. This
reruns PyCG once (seed 0, Phase 1's file list, the sweep's fresh clone) on every traced corpus repo,
keeps the RAW graph, and maps it again with three lenient rules on top of the strict one:

  ctor    a class name -> that class's __init__, own or inherited (the observed callee)
  mro     Sub.m with m defined on a base class -> Base.m (the metric's defining-class rule)
  suffix  an unmapped name whose last two components (else last one) match exactly one node

Then: PyCG recall strict vs lenient (pooled and median), constructor-item recall, Pyright-wins,
and every observed call Pyright finds and strict PyCG misses classified as a mapping loss
(lenient PyCG has it) or a genuine PyCG miss, with examples.

    python3 d1_mapping.py > d1.json
"""
import json
import os
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "static"))
sys.path.insert(0, str(HERE))
import pycg_baseline as pb                               # noqa: E402
import sweep                                             # noqa: E402

H = sweep.H
sys.path.insert(0, str(H))
os.chdir(H)
import bench                                             # noqa: E402
from graph import ENTRY, Bundle                          # noqa: E402


def lenient_mapper(b: Bundle, root: Path, strict: pb.NameMapper):
    nodes = b.nodes
    by_qual = defaultdict(list)                          # qualname suffixes -> node keys
    for k, n in nodes.items():
        q = n["qualname"]
        parts = q.split(".")
        by_qual[".".join(parts[-2:])].append(k)
        by_qual[parts[-1]].append(k)
    classes = {}                                         # (path, Class) -> key
    for k, n in nodes.items():
        if n["kind"] == "class_body":
            classes[(n["path"], n["qualname"].rsplit(".", 1)[-1])] = k
    bases = {}                                           # simple class name -> base simple names
    for n in nodes.values():
        if n["kind"] == "module":
            bases.update(bench.class_bases(root / n["path"]))
    methods = defaultdict(dict)                          # class simple name -> {method: key}
    for k, n in nodes.items():
        if n["kind"] == "method":
            cls, m = n["qualname"].rsplit(".", 2)[-2:]
            methods[cls][m] = k

    def resolve_on(cls: str, meth: str):
        seen, todo = set(), [cls]
        while todo:                                      # first class up the bases defining meth
            c = todo.pop(0)
            if c in seen:
                continue
            seen.add(c)
            if meth in methods.get(c, {}):
                return methods[c][meth]
            todo += bases.get(c, [])
        return None

    def mapped(name: str):
        out, rule = set(), None
        outcome, key = strict.map_name(name)
        if key:
            out.add(key)
            if nodes.get(key, {}).get("kind") == "class_body":      # ctor: class -> __init__
                init = resolve_on(nodes[key]["qualname"].rsplit(".", 1)[-1], "__init__")
                if init:
                    out.add(init)
                    rule = "ctor"
            return out, rule
        if outcome == pb.EXTERNAL:
            return out, None
        parts = name.split(".")
        if len(parts) >= 2:                                         # mro: Sub.m defined on a base
            k = resolve_on(parts[-2], parts[-1])
            if k:
                return {k}, "mro"
        for suf in (".".join(parts[-2:]), parts[-1]):               # suffix, unique only
            c = by_qual.get(suf, [])
            if len(c) == 1:
                return {c[0]}, "suffix"
        return out, None
    return mapped


def main() -> int:
    tsv = (HERE / "repos.tsv").read_text().splitlines()
    repos = [l.split("\t")[0] for l in tsv if l and not l.startswith("#") and not l.startswith("repo\t")]
    res, losses, genuine, rules_used = {}, [], [], defaultdict(int)
    for name in repos:
        if not (H / "bundles" / name / "truth.json").exists():
            continue
        summary = json.loads((sweep.DATA / "static" / name / "summary.json").read_text())
        repo = sweep.clone(name, summary)
        inv = sweep.inventory_repo(repo, [repo / p for p in summary["packages"]], repo / summary["src_root"],
                                   set(), set(sweep.DEFAULT_EXCLUDE_DIRS) | sweep.NON_LIBRARY_TOP)
        run = pb.run_pycg(repo, [m.relative_path for m in inv.modules], summary["src_root"], "0",
                          pb.DEFAULT_IMAGE, "8g", 1800)
        if run["status"] != "ok":
            res[name] = {"status": run["status"]}
            continue
        b = Bundle(name)
        strict = pb.NameMapper(inv)
        mapped = lenient_mapper(b, repo, strict)
        strict_e, lenient_e = set(), set()
        for caller, callees in run["graph"].items():
            cs, _ = mapped(caller)
            o, ck = strict.map_name(caller)
            for callee in callees:
                o2, xk = strict.map_name(callee)
                if ck and xk:
                    strict_e.add((ck, xk))
                xs, rule = mapped(callee)
                for c in cs:
                    for x in xs:
                        lenient_e.add((c, x))
                        if rule and (c, x) not in strict_e:
                            rules_used[rule] += 1
        t = json.loads((b.dir / "truth.json").read_text())
        obs = {(e[0], e[1]) for e in t["edges"]
               if e[0] != ENTRY and e[0] != e[1] and b.nodes[e[1]]["kind"] in ("function", "method")}
        pyr = b.static_by_tool.get("pyright", set())
        bundle_pycg = b.static_by_tool.get("pycg", set())
        its = bench.items(b)
        ctor = [i for i in its if i["style"] == "constructor" and i["label"]]
        r = {"observed": len(obs),
             "recall_bundle_pycg": len(obs & bundle_pycg) / len(obs),
             "recall_strict_seed0": len(obs & strict_e) / len(obs),
             "recall_lenient": len(obs & lenient_e) / len(obs),
             "recall_pyright": len(obs & pyr) / len(obs),
             "recall_union_lenient": len(obs & (lenient_e | pyr)) / len(obs),
             "ctor_n": len(ctor),
             "ctor_strict": sum((i["caller"], i["callee"]) in strict_e for i in ctor),
             "ctor_lenient": sum((i["caller"], i["callee"]) in lenient_e for i in ctor),
             "ctor_pyright": sum((i["caller"], i["callee"]) in pyr for i in ctor)}
        for pair in obs & pyr - strict_e:
            (losses if pair in lenient_e else genuine).append((name, *pair))
        res[name] = r
        print(f"{name}: strict {r['recall_strict_seed0']:.2f} lenient {r['recall_lenient']:.2f} "
              f"pyright {r['recall_pyright']:.2f}", file=sys.stderr, flush=True)
    ok = {n: r for n, r in res.items() if "observed" in r}
    tot = sum(r["observed"] for r in ok.values())
    pooled = {k: sum(r[k] * r["observed"] for r in ok.values()) / tot
              for k in ("recall_bundle_pycg", "recall_strict_seed0", "recall_lenient", "recall_pyright", "recall_union_lenient")}
    med = {k: st.median(r[k] for r in ok.values()) for k in pooled}
    rnd = random.Random(20261020)
    out = {"repos": res, "n_repos": len(ok), "pooled": pooled, "median": med,
           "pyright_wins_strict": sum(r["recall_pyright"] > r["recall_strict_seed0"] for r in ok.values()),
           "pyright_wins_lenient": sum(r["recall_pyright"] > r["recall_lenient"] for r in ok.values()),
           "ctor": {k: sum(r[k] for r in ok.values()) for k in ("ctor_n", "ctor_strict", "ctor_lenient", "ctor_pyright")},
           "audit": {"pyright_hits_strict_pycg_misses": len(losses) + len(genuine), "mapping_loss": len(losses),
                     "genuine_miss": len(genuine), "rules_used": dict(rules_used),
                     "examples_loss": rnd.sample(losses, min(5, len(losses))),
                     "examples_genuine": rnd.sample(genuine, min(5, len(genuine))),
                     "random50_loss_share": (lambda s: sum(x in set(losses) for x in s) / len(s) if s else None)(
                         rnd.sample(losses + genuine, min(50, len(losses) + len(genuine))))}}
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
