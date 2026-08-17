#!/usr/bin/env python3
"""Is PyCG's call graph for a real package reproducible run-to-run?

Found while measuring the scaling curve: three identical invocations over
click's 17 modules returned 1137, 1160 and 1286 nodes, and other identical
invocations were OOM-killed at an 8GB cap instead of returning anything.
That is a different failure from "misses dynamic edges" -- it means the
graph is not a function of the input alone, so any measurement taken from a
single run (including this project's own) is one sample, not the value.

The hypothesis this tests: PyCG's fixpoint iterates over sets, so
PYTHONHASHSEED (random per process by default) changes the iteration order,
which changes both which fixpoint is reached and whether it is reached at
all. If so, each FIXED seed should be internally consistent while different
seeds disagree.

Usage:
    python3 pycg_determinism.py --repo ~/traceweave-data/refrepos/click \\
        --package src/click --src-root src --seeds 0,1,42 --repeats 2 \\
        --out ../../explainer/public/live/determinism.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

IMAGE = "traceweave-demo-pycg:latest"
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def one_run(repo: Path, src_root: str, rel_files: list[str], seed: str | None,
            memory: str, timeout: int) -> dict:
    env = ["-e", f"PYTHONHASHSEED={seed}"] if seed is not None else []
    argv = [
        "docker", "run", "--rm", f"--memory={memory}", *env,
        "--entrypoint", "python3",
        "-v", f"{repo}:/repo:ro", "-v", f"{DEMO_DIR}:/s:ro",
        IMAGE, "/s/pycg_probe.py", f"/repo/{src_root}",
        *[f"/repo/{f}" for f in rel_files],
    ]
    started = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "wall_seconds": timeout}
    wall = round(time.time() - started, 2)
    if proc.returncode == 137:
        return {"status": "killed", "detail": "OOM (exit 137)", "wall_seconds": wall}
    if proc.returncode != 0:
        return {"status": "error", "detail": f"exit {proc.returncode}", "wall_seconds": wall}
    out = json.loads(proc.stdout)
    out.update({"status": "ok", "wall_seconds": wall})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--src-root", required=True)
    ap.add_argument("--seeds", default="0,1,42",
                    help="comma-separated PYTHONHASHSEED values; 'none' = leave unset")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--memory", default="8g")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    files = sorted((repo / args.package).rglob("*.py"))
    rel = [str(p.relative_to(repo)) for p in files]
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    seeds: list[str | None] = [None if s == "none" else s
                                for s in args.seeds.split(",") if s]
    trials = []
    for seed in seeds:
        for i in range(args.repeats):
            result = one_run(repo, args.src_root, rel, seed, args.memory, args.timeout)
            result.update({"seed": "unset" if seed is None else seed, "repeat": i})
            trials.append(result)
            shown = (f"{result['nodes']} nodes / {result['edges']} edges "
                     f"in {result['seconds']}s"
                     if result["status"] == "ok"
                     else f"{result['status'].upper()} {result.get('detail', '')}")
            print(f"seed={result['seed']:>5} run {i}: {shown}", flush=True)

    ok = [t for t in trials if t["status"] == "ok"]
    distinct_graphs = sorted({(t["nodes"], t["edges"]) for t in ok})

    # A killed trial has no node count, so the outcome key has to tolerate its
    # absence: "this seed always OOMs" is a consistent result, and the whole
    # point of the run is that some seeds never return a graph at all.
    def outcome(trial: dict) -> tuple:
        return (trial["status"], trial.get("nodes"), trial.get("edges"))

    per_seed_consistent = all(
        len({outcome(t) for t in trials if t["seed"] == s}) == 1
        for s in {t["seed"] for t in trials}
    )
    payload = {
        "repo": repo.name,
        "sha": sha,
        "package": args.package,
        "n_files": len(rel),
        "memory_cap": args.memory,
        "trials": trials,
        "completed": len(ok),
        "attempted": len(trials),
        "distinct_results": [{"nodes": n, "edges": e} for n, e in distinct_graphs],
        "reproducible_per_seed": per_seed_consistent,
    }
    out = Path(args.out).expanduser().resolve()
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.rename(tmp, out)
    print(f"\n{len(ok)}/{len(trials)} runs completed; "
          f"{len(distinct_graphs)} distinct graph(s): {distinct_graphs}")
    print(f"consistent within a fixed seed: {per_seed_consistent}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
