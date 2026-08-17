#!/usr/bin/env python3
"""Measure how PyCG's cost grows as a real package's modules are added.

Motivation: the live demo's headline is a miss RATE, which says nothing
about whether the tool can be run at all. On click it cannot be run on the
whole package -- `click/testing.py` does not complete at 8GB / 120s, while
the other 16 modules together finish in under two seconds. That is a
different kind of limit from "misses some edges" and deserves its own
measured curve rather than an anecdote.

Each step is a fresh container running demo/pycg_probe.py over a cumulative
file list, so a step that OOMs kills only its own container. Steps are
cumulative because PyCG's cost is inter-procedural: measuring files
individually would miss exactly the cross-module blowup this is looking for.

The suspected-blowup module is measured LAST so that every other datapoint
exists even if the run has to be cut short.

Usage:
    python3 pycg_scaling.py --repo ~/traceweave-data/refrepos/click \\
        --package src/click --src-root src --last testing.py \\
        --out ../../explainer/public/live/scaling.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

IMAGE = "traceweave-demo-pycg:latest"
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def run_step(repo: Path, root_in_repo: str, rel_files: list[str],
             memory: str, timeout: int) -> dict:
    """One PyCG run in a throwaway container. Returns a result dict whose
    `status` is ok / timeout / killed / error -- a step that fails is a
    datapoint, not an exception.
    """
    argv = [
        "docker", "run", "--rm", f"--memory={memory}",
        "--entrypoint", "python3",
        "-v", f"{repo}:/repo:ro",
        "-v", f"{DEMO_DIR}:/s:ro",
        IMAGE, "/s/pycg_probe.py", f"/repo/{root_in_repo}",
        *[f"/repo/{f}" for f in rel_files],
    ]
    started = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "wall_seconds": timeout}
    wall = round(time.time() - started, 2)

    if proc.returncode == 137:
        # 128+9: the kernel's OOM killer, i.e. PyCG asked for more than the
        # container's memory cap rather than merely being slow.
        return {"status": "killed", "wall_seconds": wall, "detail": "OOM (exit 137)"}
    if proc.returncode != 0:
        return {"status": "error", "wall_seconds": wall,
                "detail": proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else
                          f"exit {proc.returncode}"}
    result = json.loads(proc.stdout)
    result.update({"status": "ok", "wall_seconds": wall})
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--package", required=True, help="package dir relative to repo")
    ap.add_argument("--src-root", required=True, help="import root relative to repo")
    ap.add_argument("--last", default="",
                    help="comma-separated basenames to measure last (suspected blowups)")
    ap.add_argument("--memory", default="8g")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    pkg = repo / args.package
    last = {name for name in args.last.split(",") if name}

    files = sorted(p for p in pkg.rglob("*.py") if p.name not in last)
    files += sorted(p for p in pkg.rglob("*.py") if p.name in last)
    rel = [str(p.relative_to(repo)) for p in files]

    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    steps = []
    for i in range(1, len(rel) + 1):
        added = Path(rel[i - 1]).name
        result = run_step(repo, args.src_root, rel[:i], args.memory, args.timeout)
        result.update({"n_files": i, "added": added,
                       "measured_last": added in last})
        steps.append(result)
        summary = (f"{result['nodes']} nodes, {result['edges']} edges, "
                   f"{result['seconds']}s, {result['peak_rss_mb']}MB"
                   if result["status"] == "ok"
                   else f"{result['status'].upper()} {result.get('detail', '')}")
        print(f"[{i:2d}/{len(rel)}] +{added:24s} {summary}", flush=True)

    payload = {
        "repo": repo.name,
        "sha": sha,
        "package": args.package,
        "memory_cap": args.memory,
        "timeout_seconds": args.timeout,
        "measured_last": sorted(last),
        "steps": steps,
    }
    out = Path(args.out).expanduser().resolve()
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.rename(tmp, out)
    print(f"wrote {out}")

    failed = [s for s in steps if s["status"] != "ok"]
    if failed:
        print(f"{len(failed)} step(s) did not complete: "
              f"{', '.join(s['added'] for s in failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
