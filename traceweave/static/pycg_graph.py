#!/usr/bin/env python3
"""Runs INSIDE the PyCG image. One analysis, the FULL adjacency map on stdout.

Sibling of `demo/pycg_probe.py`, which prints only the cost of an analysis --
that one exists for the scaling and determinism sweeps, where the graph itself
is not wanted and holding 1200 nodes per step would be waste. Here the graph is
the point.

A separate process per analysis, for the same reason the probe is: the
interesting runs are the ones PyCG does not come back from, and a run that
exhausts memory has to be able to die without taking the harness with it.

Usage (inside the container):
    python3 /s/pycg_graph.py --root <import-root> --files-from <listfile>
    python3 /s/pycg_graph.py --root <import-root> a.py b.py

Stdout: {"graph": {...}, "cost": {...}}   Stderr: progress only.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--files-from")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()

    files = list(args.files)
    if args.files_from:
        with open(args.files_from, encoding="utf-8") as fh:
            files.extend(line.strip() for line in fh if line.strip())
    if not files:
        print("no input files", file=sys.stderr)
        return 2

    # Imported here, not at module top: the import itself fails on Python 3.12
    # (MANIFEST §2.1) and the failure should be reported as a run outcome with
    # its message, not as a traceback from the wrong place.
    from pycg.pycg import CallGraphGenerator

    started = time.time()
    cg = CallGraphGenerator(files, args.root, -1, "call-graph")
    cg.analyze()
    graph = {k: sorted(v) for k, v in cg.output().items()}
    cost = {
        "seconds": round(time.time() - started, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "nodes": len(graph),
        "edges": sum(len(v) for v in graph.values()),
        # Recorded because it CHANGES THE RESULT: PyCG's fixpoint iterates over
        # sets, so the hash seed decides which graph comes back and whether one
        # comes back at all (scripts/pycg_determinism.py). A static graph
        # without its seed is not a reproducible artifact.
        "hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "n_input_files": len(files),
    }
    json.dump({"graph": graph, "cost": cost}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
