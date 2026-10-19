#!/usr/bin/env python3
"""Static baseline 1: PyCG 0.0.8, the published Python call-graph tool.

Phase 1 §1.2. The plan's word for why this exists is "non-negotiable":

    "Reporting against PyCG makes the claim about *the state of the art*, not
     about our code."

Two jobs, and the second is the harder one.

### 1. Run it, honestly, given that it is not deterministic

`scripts/pycg_determinism.py` established that identical invocations over
click's 17 modules return 1137, 1160 and 1286 nodes on different runs, and
that some identical invocations exhaust 8 GB instead of returning at all --
because PyCG's fixpoint iterates over sets and `PYTHONHASHSEED` is random per
process by default.

That makes "PyCG's call graph for repo R" ill-defined, so the seed policy has
to be part of the metric rather than an implementation detail:

  * every run pins `PYTHONHASHSEED` explicitly (default policy: 0, 1, 42),
  * the headline S is the **union of the runs that completed**, and
  * the per-seed node/edge counts and any OOM/timeout are recorded beside it.

The union is deliberate. It gives the published baseline the maximum credit
its own tool can produce, so nobody can answer a high miss rate with "you
picked its worst run". The single seed-0 run is recorded too, because that is
the one a reader can reproduce exactly.

### 2. Map its names onto our node set

PyCG names things `<module.dotted.path>.<qualified_symbol>`, which is nearly
our scheme -- but "nearly" is where the fabricated headline numbers live. Three
real behaviours, all measured on click, all reported as counts rather than
quietly patched:

  namespace duplicates  With `--src-root src`, PyCG emits click's own submodules
                        under two namespaces at once: `click.types.convert_type`
                        AND `types.convert_type`, both as definition nodes, with
                        edges split between them. 44 functions were affected in
                        click; unmerged, that alone inflated the miss rate by
                        ~11 points. Merged here, with a count.
  synthesized paths     PyCG invents attribute paths that are not definitions in
                        the source at all (`core.Command._stream.read`). They
                        map to no node and are recorded as `unmapped`, never
                        dropped in silence.
  builtins / external   `<builtin>.getattr`, `re.compile`. Out of universe by
                        §2.1 and counted as the external surface.

Every name PyCG emits lands in exactly one of: mapped, namespace_merged,
external, or unmapped-with-a-reason. The four sum to its node count, so the
mapping can be audited by arithmetic rather than by trust.

Usage:
    # normalize a graph that already exists (no docker; how the tests run)
    python3 pycg_baseline.py --repo ~/traceweave-data/refrepos/click \\
        --package src/click --src-root src \\
        --graph-json ../../explainer/public/live/real_static.json

    # the real thing: run PyCG under the seed policy, then normalize
    python3 pycg_baseline.py --repo ~/traceweave-data/refrepos/click \\
        --package src/click --src-root src --seeds 0,1,42 --out /tmp/pycg.json

Stdlib only. Exit codes: 0 ok, 2 bad args, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from edgeset import StaticEdgeSet
from nodes import MODULE_SYMBOL, RepoInventory, inventory_repo

BASELINE = "pycg"
BASELINE_VERSION = "1.0"
TOOL_PIN = "pycg==0.0.8"          # MANIFEST.md §2
DEFAULT_IMAGE = "traceweave-static:latest"
DEFAULT_SEEDS = ("0", "1", "42")
BUILTIN_PREFIX = "<builtin>"

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Running PyCG
# --------------------------------------------------------------------------

def kill_container(name: str) -> None:
    """Stop a container the timeout path abandoned.

    subprocess's `timeout=` kills the `docker run` CLIENT, not the container:
    the daemon keeps it running at 100% CPU indefinitely, and `--rm` only fires
    when it exits, which it never does. Every timeout used to leak one core.
    Best-effort and silent -- it may already have exited on its own.
    """
    try:
        subprocess.run(["docker", "kill", name], capture_output=True,
                       text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def run_pycg(repo: Path, rel_files: list[str], src_root_rel: str, seed: str,
             image: str = DEFAULT_IMAGE, memory: str = "8g",
             timeout: int = 1800) -> dict:
    """One PyCG analysis in the pinned image. Never raises for a tool failure:
    an OOM or a timeout is an outcome to record, and `pycg_parse_rate.py`
    measured 1.6% of library files unparseable at all, so failure is normal
    here rather than exceptional.
    """
    listing = "\n".join(f"/repo/{f}" for f in rel_files)
    # --name so the timeout path below can actually stop the container.
    name = f"tw-pycg-{os.getpid()}-{seed}-{time.time_ns():x}"
    argv = [
        "docker", "run", "--rm", f"--name={name}", f"--memory={memory}",
        "-e", f"PYTHONHASHSEED={seed}",
        "--entrypoint", "python3",
        "-v", f"{repo}:/repo:ro", "-v", f"{HERE}:/s:ro",
        "-i", image, "/s/pycg_graph.py",
        "--root", f"/repo/{src_root_rel}" if src_root_rel != "." else "/repo",
        "--files-from", "/dev/stdin",
    ]
    started = time.time()
    try:
        proc = subprocess.run(argv, input=listing, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_container(name)
        return {"status": "timeout", "seed": seed, "wall_seconds": timeout}
    except FileNotFoundError:
        return {"status": "no_docker", "seed": seed, "wall_seconds": 0}
    wall = round(time.time() - started, 2)
    if proc.returncode == 137:
        return {"status": "killed", "detail": "OOM (exit 137)", "seed": seed,
                "wall_seconds": wall}
    if proc.returncode != 0:
        return {"status": "error", "seed": seed, "wall_seconds": wall,
                "detail": (proc.stderr or "").strip()[-800:]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "seed": seed, "wall_seconds": wall,
                "detail": "stdout was not JSON"}
    return {"status": "ok", "seed": seed, "wall_seconds": wall,
            "graph": payload["graph"], "cost": payload["cost"]}


def union_graphs(runs: list[dict]) -> tuple[dict, dict]:
    """Union of every successful run's adjacency map, plus the spread.

    Union, not intersection or first-run: see the module docstring. The spread
    is reported whether or not it is zero -- "PyCG returned the same graph on
    all three seeds for this repo" is a result too.
    """
    ok = [r for r in runs if r["status"] == "ok"]
    graph: dict[str, set[str]] = {}
    for run in ok:
        for caller, callees in run["graph"].items():
            graph.setdefault(caller, set()).update(callees)
    spread = {
        "seeds_attempted": [r["seed"] for r in runs],
        "seeds_completed": [r["seed"] for r in ok],
        "per_seed": [
            {"seed": r["seed"], "status": r["status"],
             "nodes": r.get("cost", {}).get("nodes"),
             "edges": r.get("cost", {}).get("edges"),
             "seconds": r.get("cost", {}).get("seconds"),
             "peak_rss_mb": r.get("cost", {}).get("peak_rss_mb"),
             "detail": r.get("detail")}
            for r in runs
        ],
        "union_nodes": len(graph),
        "union_edges": sum(len(v) for v in graph.values()),
        "deterministic_across_seeds": len({
            (r["cost"]["nodes"], r["cost"]["edges"]) for r in ok
        }) <= 1 if ok else None,
    }
    return {k: sorted(v) for k, v in graph.items()}, spread


# --------------------------------------------------------------------------
# Mapping PyCG names onto our node set
# --------------------------------------------------------------------------

MAPPED = "mapped"
MERGED = "namespace_merged"
EXTERNAL = "external"
UNMAPPED = "unmapped"


@dataclass
class NameMapper:
    """PyCG dotted name -> our node key, with every outcome accounted for."""

    inv: RepoInventory
    module_names: set[str] = field(default_factory=set)
    package_roots: set[str] = field(default_factory=set)
    path_for_module: dict[str, str] = field(default_factory=dict)
    nodes: set[str] = field(default_factory=set)
    # symbol -> the `#N` group it was split into by nodes.py collision handling
    redefinition_groups: dict[str, list[str]] = field(default_factory=dict)
    reasons: dict[str, int] = field(default_factory=dict)
    merged_names: list[str] = field(default_factory=list)
    unmapped_names: list[str] = field(default_factory=list)
    # Memoized so `reasons` counts each distinct NAME once. Without this the
    # counts inflate by however many edges mention the name, which would make
    # the diagnostics unreadable and the sum check meaningless.
    _cache: dict[str, tuple[str, str | None]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.module_names = set(self.inv.module_by_name())
        self.path_for_module = {m.module_name: m.relative_path for m in self.inv.modules}
        self.package_roots = {name.split(".")[0] for name in self.module_names}
        self.nodes = set(self.inv.by_key())
        for key in self.nodes:
            path, _, symbol = key.partition("::")
            if "#" in symbol.rsplit(".", 1)[-1]:
                base = symbol.rsplit("#", 1)[0]
                self.redefinition_groups.setdefault(f"{path}::{base}", []).append(key)
        for group in self.redefinition_groups.values():
            group.sort()

    def _note(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def _direct(self, name: str) -> str | None:
        """Longest module prefix wins: `a.b.c.f` prefers module `a.b.c` over
        `a.b`, because `a.b.c` may define `f` while `a.b` defines a class `c`.
        """
        best: str | None = None
        for module in self.module_names:
            if name == module or name.startswith(module + "."):
                if best is None or len(module) > len(best):
                    best = module
        if best is None:
            return None
        path = self.path_for_module[best]
        symbol = name[len(best) + 1:] or MODULE_SYMBOL
        key = f"{path}::{symbol}"
        if key in self.nodes:
            return key
        # nodes.py split a conditionally-redefined `def f` into `f#0`/`f#1`;
        # PyCG emits the bare name. Map to the first, and record it -- Phase 3
        # can be generous across the group, but the count must be visible.
        group = self.redefinition_groups.get(key)
        if group:
            self._note("redefinition_collapsed")
            return group[0]
        return None

    def map_name(self, name: str) -> tuple[str, str | None]:
        """Returns (outcome, node_key). Outcome is one of the four constants."""
        if name in self._cache:
            return self._cache[name]
        result = self._map_name_uncached(name)
        self._cache[name] = result
        return result

    def _map_name_uncached(self, name: str) -> tuple[str, str | None]:
        if name.startswith(BUILTIN_PREFIX):
            self._note("builtin")
            return EXTERNAL, None

        key = self._direct(name)
        if key:
            return MAPPED, key

        # The namespace-duplicate merge: `types.convert_type` is click's own
        # `click.types.convert_type` seen through a shorter root. Only accepted
        # when exactly one package root resolves it, so an ambiguous shortening
        # is never guessed at.
        candidates = {root: self._direct(f"{root}.{name}") for root in self.package_roots}
        resolved = [k for k in candidates.values() if k]
        if len(set(resolved)) == 1:
            self.merged_names.append(name)
            self._note("namespace_merged")
            return MERGED, resolved[0]

        head = name.split(".")[0]
        if head in self.module_names or head in self.package_roots:
            # In our namespace but not a node we inventoried: a synthesized
            # attribute path (`core.Command._stream.read`).
            self.unmapped_names.append(name)
            self._note("synthesized_path")
            return UNMAPPED, None
        self._note("external_module")
        return EXTERNAL, None


def add_edge(edges: StaticEdgeSet, caller: str | None, callee: str | None,
             callee_outcome: str) -> None:
    if caller and callee:
        edges.add_in_universe(caller, callee)
    elif caller and callee_outcome == EXTERNAL:
        edges.add_external(caller)
    else:
        edges.add_unmapped("caller_unmapped" if not caller else "callee_unmapped")


def normalize(graph: dict[str, list[str]], inv: RepoInventory) -> tuple[StaticEdgeSet, dict]:
    mapper = NameMapper(inv)
    edges = StaticEdgeSet(BASELINE)
    node_outcomes: dict[str, int] = {MAPPED: 0, MERGED: 0, EXTERNAL: 0, UNMAPPED: 0}
    mapped_nodes: set[str] = set()

    for name in graph:
        outcome, key = mapper.map_name(name)
        node_outcomes[outcome] += 1
        if key:
            mapped_nodes.add(key)

    for caller, callees in graph.items():
        _, caller_key = mapper.map_name(caller)
        for callee in callees:
            callee_outcome, callee_key = mapper.map_name(callee)
            add_edge(edges, caller_key, callee_key, callee_outcome)

    diagnostics = {
        "pycg_nodes": len(graph),
        "pycg_edges": sum(len(v) for v in graph.values()),
        "name_outcomes": node_outcomes,
        # Arithmetic the reader can check: the four outcomes sum to the node count.
        "name_outcomes_sum_matches": sum(node_outcomes.values()) == len(graph),
        "reasons": dict(sorted(mapper.reasons.items())),
        "namespace_merged_examples": sorted(set(mapper.merged_names))[:20],
        "namespace_merged_distinct": len(set(mapper.merged_names)),
        "unmapped_examples": sorted(set(mapper.unmapped_names))[:20],
        "unmapped_distinct": len(set(mapper.unmapped_names)),
        "inventory_nodes_covered": len(mapped_nodes),
        "inventory_nodes_total": len(inv.by_key()),
    }
    return edges, diagnostics


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="PyCG static baseline for one repo.")
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--package", required=True, help="dir inside --repo, e.g. src/click")
    ap.add_argument("--src-root", default=".", help="import root inside --repo")
    ap.add_argument("--exclude", default="", help="comma-separated basenames to skip")
    ap.add_argument("--graph-json", type=Path,
                    help="normalize an existing graph instead of running PyCG. "
                         "Accepts {'graph':...} or a bare adjacency map.")
    ap.add_argument("--seeds", default=",".join(DEFAULT_SEEDS),
                    help="PYTHONHASHSEED policy (comma-separated)")
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--memory", default="8g")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--counts-only", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    exclude = {n for n in args.exclude.split(",") if n}
    inv = inventory_repo(repo, repo / args.package, repo / args.src_root, exclude)
    rel_files = [m.relative_path for m in inv.modules]

    if args.graph_json:
        raw = json.loads(args.graph_json.read_text())
        graph = raw.get("graph", raw)
        spread = {"source": str(args.graph_json), "seeds_attempted": [],
                  "hash_seed": raw.get("hash_seed", raw.get("cost", {}).get("hash_seed"))}
    else:
        runs = [run_pycg(repo, rel_files, args.src_root, seed, args.image,
                         args.memory, args.timeout)
                for seed in args.seeds.split(",") if seed]
        if all(r["status"] == "no_docker" for r in runs):
            print("docker not available; use --graph-json to normalize an "
                  "existing graph", file=sys.stderr)
            return 3
        graph, spread = union_graphs(runs)
        if not graph:
            print("every PyCG run failed:", json.dumps(spread["per_seed"]), file=sys.stderr)

    edges, diagnostics = normalize(graph, inv)
    payload = {
        "baseline": BASELINE,
        "baseline_version": BASELINE_VERSION,
        "tool_pin": TOOL_PIN,
        "spec_version": "1.0",
        "repo": str(repo),
        "package": args.package,
        "src_root": args.src_root,
        "inventory": inv.counts(),
        "run": spread,
        "diagnostics": diagnostics,
        "edges": edges.to_json(include_edges=not args.counts_only),
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(args.out.suffix + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, args.out)
        print(f"wrote {args.out} ({len(edges.in_universe)} in-universe edges)",
              file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
