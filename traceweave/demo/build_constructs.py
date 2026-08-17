#!/usr/bin/env python3
"""Measure every construct fixture and emit constructs.json for the UI.

One directory per construct under constructs/, each a minimal reproduction
of one way a call can exist at runtime and not in a static call graph. Each
fixture declares, in its own META, the edge it PREDICTS will be missed; this
script records whether that prediction held. A fixture whose prediction
fails is reported as failed rather than quietly dropped -- the point of
stating the expectation in the fixture is that it can be wrong.

Every construct is run through exactly the same pipeline as the real click
measurement: PyCG in the pinned container, then the same tracer, then the
same diff and the same classifier. A fixture that got special treatment
would not be evidence about the real pipeline.

Each fixture is a separate tracer subprocess: they all define a module
called `fixture`, so running them in one interpreter would collide in
sys.modules and silently trace the wrong code.

Usage: ./build_constructs.py [--out ../../explainer/public/live/constructs.json]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONSTRUCTS_DIR = HERE / "constructs"
IMAGE = "traceweave-demo-pycg:latest"

sys.path.insert(0, str(HERE))
from tracer import (  # noqa: E402
    ENTRY_CALLER,
    canonicalize_static_graph,
    classify_missing,
    diff_package,
    read_source_line,
)


def read_meta(fixture: Path) -> dict:
    """Pull META out without importing the fixture -- importing it here
    would execute the very code we are about to trace, in this process.
    """
    tree = ast.parse(fixture.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "META" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{fixture} has no META block")


def run_pycg(construct_dir: Path, out_dir: Path, run_id: str) -> dict:
    rel = construct_dir.relative_to(HERE)
    subprocess.run([
        "docker", "run", "--rm", "--memory=4g",
        "-v", f"{HERE}:/repo:ro", "-v", f"{out_dir}:/out",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", f"RUN_ID={run_id}", "-e", "MODE=package",
        "-e", f"PACKAGE={rel}", "-e", f"SRC_ROOT={rel}",
        "-e", "OUT_NAME=static.json",
        IMAGE,
    ], check=True, capture_output=True, text=True)
    return json.loads((out_dir / "static.json").read_text())


def run_tracer(construct_dir: Path, out_dir: Path, run_id: str) -> dict:
    subprocess.run([
        sys.executable, str(HERE / "tracer.py"), "trace-package",
        "--src-root", str(construct_dir),
        "--package", str(construct_dir),
        "--workload", str(construct_dir / "fixture.py"),
        "--entry", "main",
        "--run-id", run_id,
        "--out", str(out_dir / "runtime.json"),
    ], check=True, capture_output=True, text=True)
    return json.loads((out_dir / "runtime.json").read_text())


def measure(construct_dir: Path, run_id: str) -> dict:
    meta = read_meta(construct_dir / "fixture.py")
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        static = run_pycg(construct_dir, out_dir, run_id)
        runtime = run_tracer(construct_dir, out_dir, run_id)

    modules = set(runtime["analysed_modules"])
    package = min(modules, key=len) if modules else ""
    submodules = {m.split(".")[1] for m in modules if m.count(".") == 1}
    graph, _ = canonicalize_static_graph(static["graph"], package, submodules)

    result = diff_package(graph, runtime["edges"])
    internal = [e for e in runtime["edges"] if e["caller"] != ENTRY_CALLER]
    for edge in internal:
        edge["source"] = read_source_line(construct_dir, edge.get("call_module"),
                                           edge.get("call_line"))
    classify_missing(internal, modules)
    missing_keys = {(e["caller"], e["callee"]) for e in result["missing_edges"]}
    missing = [e for e in internal if (e["caller"], e["callee"]) in missing_keys]

    missing_pairs = {(e["caller"], e["callee"]) for e in missing}
    ran_pairs = {(e["caller"], e["callee"]) for e in internal}

    expected_missing = [tuple(pair) for pair in meta["expect_missing"]]
    # An unexpected extra miss is not a failure -- the fixture predicts what
    # it is built to demonstrate, not that nothing else can also be missed.
    unmet = [pair for pair in expected_missing if pair not in missing_pairs]

    # `expect_found` is the other direction, and it has to be checked just as
    # hard: a fixture claiming "PyCG resolves this one" is a claim about the
    # tool, and an edge that never ran would satisfy "not missing" vacuously.
    expected_found = [tuple(pair) for pair in meta.get("expect_found", [])]
    unmet += [pair for pair in expected_found
              if pair in missing_pairs or pair not in ran_pairs]

    outcome = meta.get("outcome") or (
        "found" if meta["is_control"] else
        "missed" if expected_missing else "resolved-in-small"
    )

    return {
        **meta,
        "outcome": outcome,
        "expect_found": [list(p) for p in expected_found],
        "dir": construct_dir.name,
        "source": (construct_dir / "fixture.py").read_text(),
        "graph": graph,
        "runtime_edges": internal,
        "missing_edges": missing,
        "counter": {"missing": len(missing), "total": len(internal)},
        "expected_missing": [list(p) for p in expected_missing],
        "unmet_expectations": [list(p) for p in unmet],
        "expectation_met": not unmet,
        "static_nodes": len(graph),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE.parent.parent /
                                          "explainer/public/live/constructs.json"))
    args = ap.parse_args()

    run_id = str(int(time.time()))
    dirs = sorted(d for d in CONSTRUCTS_DIR.iterdir() if (d / "fixture.py").is_file())
    if not dirs:
        print(f"no fixtures under {CONSTRUCTS_DIR}", file=sys.stderr)
        return 2

    results = []
    for construct_dir in dirs:
        result = measure(construct_dir, run_id)
        results.append(result)
        status = "ok" if result["expectation_met"] else "PREDICTION FAILED"
        print(f"{result['construct']:24s} "
              f"{result['counter']['missing']:2d}/{result['counter']['total']:2d} missing"
              f"   {status}", flush=True)
        for pair in result["unmet_expectations"]:
            print(f"    expected missing but PyCG found it: {pair[0]} -> {pair[1]}",
                  file=sys.stderr)

    payload = {
        "run_id": run_id,
        "constructs": results,
        "n_failed_predictions": sum(1 for r in results if not r["expectation_met"]),
    }
    out = Path(args.out).resolve()
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.rename(tmp, out)
    print(f"wrote {out}")
    return 1 if payload["n_failed_predictions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
