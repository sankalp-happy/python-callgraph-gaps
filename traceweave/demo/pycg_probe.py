#!/usr/bin/env python3
"""Runs INSIDE the demo Docker image. One PyCG analysis, cost reported as
JSON on stdout. Used by scripts/pycg_scaling.py, which calls it once per
step of a growing file list.

Deliberately a separate process per step: the interesting steps are the ones
where PyCG does not come back, and a step that OOMs has to be able to die
without taking the measurement harness with it.

Usage (inside the container):  python3 /s/pycg_probe.py <root> <file>...
"""

from __future__ import annotations

import json
import resource
import sys
import time

from pycg.pycg import CallGraphGenerator


def main() -> int:
    root, files = sys.argv[1], sys.argv[2:]
    started = time.time()
    cg = CallGraphGenerator(files, root, -1, "call-graph")
    cg.analyze()
    graph = cg.output()
    print(json.dumps({
        "nodes": len(graph),
        "edges": sum(len(v) for v in graph.values()),
        "seconds": round(time.time() - started, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
