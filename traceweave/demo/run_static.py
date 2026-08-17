#!/usr/bin/env python3
"""Runs INSIDE the demo Docker image (see Dockerfile). Analyzes bind-mounted
source with PyCG and atomically writes its call graph into the bind-mounted
/out (Data contract: write .tmp, then os.rename()).

Two modes:

  file     (default) one fixture file, repo root = /repo. This is the
           original toy-demo path and its output is byte-compatible with
           what it produced before package mode existed.
  package  every .py under PACKAGE (recursively), analysed together with
           repo root = SRC_ROOT, minus EXCLUDE. Used for the real-repo demo,
           where PyCG must see the whole module set at once -- analysing
           files one at a time would resolve no cross-module calls and make
           the tool look far worse than it is.

Mounts expected (see run_demo.sh / run_real.sh):
  /repo   read-only bind mount containing the source to analyse
  /out    writable bind mount -> explainer/public/live/ on the host

Env:
  RUN_ID    epoch-seconds run id, embedded in the output (Data contract)
  MODE      file | package                        (default: file)
  FIXTURE   file mode: filename inside /repo      (default: fixture.py)
  PACKAGE   package mode: dir inside /repo, e.g. src/click
  SRC_ROOT  package mode: import root inside /repo, e.g. src
  EXCLUDE   package mode: comma-separated basenames to skip
  OUT_NAME  output filename inside /out           (default: static.json)
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

from pycg.pycg import CallGraphGenerator

REPO = Path("/repo")
OUT_DIR = Path("/out")


def write_atomic(name: str, payload: dict) -> None:
    tmp = OUT_DIR / (name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.rename(tmp, OUT_DIR / name)


def analyse(entry_points: list[str], root: str) -> tuple[dict, dict]:
    """PyCG over `entry_points` with `root` as the import root. Returns the
    adjacency map plus the cost of producing it -- cost is data here, not
    logging: PyCG's memory curve is one of the things the demo shows.
    """
    started = time.time()
    cg = CallGraphGenerator(entry_points, root, -1, "call-graph")
    cg.analyze()
    graph = {k: sorted(v) for k, v in cg.output().items()}
    cost = {
        "seconds": round(time.time() - started, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "nodes": len(graph),
        "edges": sum(len(v) for v in graph.values()),
    }
    return graph, cost


def run_file_mode(run_id: str, out_name: str) -> int:
    fixture_path = REPO / os.environ.get("FIXTURE", "fixture.py")
    graph, cost = analyse([str(fixture_path)], str(REPO))
    write_atomic(out_name, {"run_id": run_id, "graph": graph})
    print(f"wrote {out_name} (run_id={run_id}, {cost['nodes']} nodes)", file=sys.stderr)
    return 0


def run_package_mode(run_id: str, out_name: str) -> int:
    package = REPO / os.environ["PACKAGE"]
    src_root = REPO / os.environ["SRC_ROOT"]
    exclude = {name for name in os.environ.get("EXCLUDE", "").split(",") if name}

    files = [p for p in sorted(package.rglob("*.py")) if p.name not in exclude]
    if not files:
        print(f"no .py files under {package}", file=sys.stderr)
        return 2
    skipped = sorted({p.name for p in package.rglob("*.py") if p.name in exclude})

    graph, cost = analyse([str(p) for p in files], str(src_root))
    write_atomic(out_name, {
        "run_id": run_id,
        "graph": graph,
        "analysed_files": [str(p.relative_to(REPO)) for p in files],
        "excluded_files": skipped,
        "cost": cost,
        # Recorded because it CHANGES THE RESULT: PyCG's fixpoint iterates over
        # sets, so the hash seed decides which graph comes back (and whether
        # one comes back at all). A static graph without its seed is not
        # reproducible. See scripts/pycg_determinism.py.
        "hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
    })
    print(f"wrote {out_name} (run_id={run_id}, {len(files)} files, "
          f"{cost['nodes']} nodes, {cost['edges']} edges, {cost['seconds']}s, "
          f"{cost['peak_rss_mb']}MB peak)", file=sys.stderr)
    return 0


def main() -> int:
    run_id = os.environ["RUN_ID"]
    mode = os.environ.get("MODE", "file")
    out_name = os.environ.get("OUT_NAME", "static.json")
    if mode == "package":
        return run_package_mode(run_id, out_name)
    if mode == "file":
        return run_file_mode(run_id, out_name)
    print(f"unknown MODE={mode!r} (expected 'file' or 'package')", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
