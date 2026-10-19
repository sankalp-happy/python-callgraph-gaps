#!/usr/bin/env python3
"""Runs INSIDE the traceweave-static image: PyCG's own fixpoint loop, capped and logged.

PyCG's analyze() loops `while (max_iter < 0 or iter_cnt < max_iter) and not has_converged()`,
and pycg_graph.py passes max_iter=-1. This replays that loop with a cap and prints one JSON
line per pass: whether has_converged() held, the state's size (defs, total names) and a
fingerprint of the state, so a state that cycles shows up as a repeated fingerprint.

    docker run -i ... traceweave-static python3 /s/pycg_iterprobe.py --root /repo --max-iter 100 < files
"""
import argparse
import hashlib
import json
import sys
import time


def fingerprint(state: dict) -> str:
    canon = {k: sorted((key, sorted(map(str, v["names"])) if isinstance(v, dict) and "names" in v else str(v))
                       for key, v in state[k].items()) for k in ("defs", "scopes", "classes")}
    return hashlib.sha256(json.dumps(canon, sort_keys=True).encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--max-iter", type=int, default=100)
    ap.add_argument("--wall", type=int, default=1500, help="stop logging after this many seconds")
    args = ap.parse_args()
    files = [l.strip() for l in sys.stdin if l.strip()]
    from pycg.pycg import CallGraphGenerator
    from pycg.processing.postprocessor import PostProcessor
    from pycg.processing.preprocessor import PreProcessor

    t0 = time.time()
    cg = CallGraphGenerator(files, args.root, args.max_iter, "call-graph")
    mgrs = (cg.import_manager, cg.scope_manager, cg.def_manager, cg.class_manager, cg.module_manager)
    cg.do_pass(PreProcessor, True, *mgrs)
    cg.def_manager.complete_definitions()
    seen, prev = {}, set()
    for it in range(args.max_iter):
        converged = cg.has_converged()
        state = cg.extract_state()
        fp = fingerprint(state)
        names = sum(len(v["names"]) for v in state["defs"].values())
        print(json.dumps({"iter": it, "converged": converged, "defs": len(state["defs"]), "names": names,
                          "fingerprint": fp, "seen_at": seen.get(fp), "seconds": round(time.time() - t0, 2),
                          "new_defs": sorted(set(state["defs"]) - prev)[:4] if prev else []}),
              flush=True)
        if converged or time.time() - t0 > args.wall:
            break
        seen.setdefault(fp, it)
        prev = set(state["defs"])
        cg.state = state
        cg.reset_counters()
        cg.do_pass(PostProcessor, False, *mgrs)
        cg.def_manager.complete_definitions()
    return 0


if __name__ == "__main__":
    sys.exit(main())
