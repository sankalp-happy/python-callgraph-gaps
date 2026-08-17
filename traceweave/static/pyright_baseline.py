#!/usr/bin/env python3
"""Static baseline 2: our own extractor, with Pyright resolving the hard calls.

Phase 1 §1.2. The plan's shape for this is "tree-sitter parse + Pyright type
information for attribute-call resolution"; what is built is the same design
with `ast` in place of tree-sitter, for one reason that matters more than
error-tolerance: node identity has to equal CPython's `co_qualname` at runtime
(`docs/metric_spec_h2a.md` §1), `ast` mirrors that structure exactly, and
tree-sitter would leave us reconstructing it. A file `ast` cannot parse is
recorded as a parse failure -- a reported metric either way (§4.4).

### How a call site becomes an edge

Every call site from `callsites.py` is put to Pyright as
`textDocument/definition` at the callee's identifier. Pyright answers with the
definition it resolves to; that location maps back to a node, and the pair
becomes an edge. Where Pyright answers nothing, our own AST binding resolution
answers if it can. Hence "assisted": the extractor is ours, Pyright is what
makes attribute calls tractable.

Both resolvers are recorded per edge, which yields a number worth reporting on
its own -- **how much does a type checker actually add over plain name
binding?** If the answer is "little", that is a finding about the value of type
information for call-graph completeness, not a disappointment.

### Deliberate strictness, and which way it errs

A definition location is accepted only on an EXACT line match against an
inventoried node. Pyright resolves plenty of things that are not callables --
`handlers = {}` resolves to its assignment line -- and a containment-based
match would attribute that to whatever function encloses the assignment,
manufacturing an edge that no tool claimed and no run will ever confirm.
Strictness costs baseline 2 some real edges; inventing them would cost the
paper its credibility.

Two known limits, both stated in the artifact rather than in a footnote:

  no dependencies    Pyright analyses the repo's own source with no installed
                     third-party packages (`deps_available: false`), so a
                     receiver whose type comes from a dependency is
                     unresolvable. This WEAKENS baseline 2 -- our own extractor
                     -- and never PyCG, so it cannot flatter the H2a headline.
                     `--site-packages` strengthens it when a triaged
                     environment is available.
  readiness          A `definition` request answered before Pyright has
                     analysed the file returns empty, which is
                     indistinguishable from "unresolvable" and would silently
                     become a static miss. So each file is opened, its first
                     `publishDiagnostics` is awaited as the readiness signal,
                     and a file that never becomes ready is recorded as
                     `unready` instead of being counted as all-unresolved.

Usage:
    python3 pyright_baseline.py --repo ~/traceweave-data/refrepos/click \\
        --package src/click --src-root src --out /tmp/pyright.json

    # a language server on this host instead of the pinned image
    python3 pyright_baseline.py ... --command "pyright-langserver --stdio"

Stdlib only. Exit codes: 0 ok, 2 bad args, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from callsites import CallSite, RepoIndex, analyse_repo
from edgeset import StaticEdgeSet
from lsp import locations_from_result, utf16_column
from nodes import MODULE_SYMBOL, Node, RepoInventory, inventory_repo

BASELINE = "pyright"
BASELINE_VERSION = "1.0"
TOOL_PIN = "pyright@1.1.411"      # MANIFEST.md §2, published 2026-06-25
DEFAULT_IMAGE = "traceweave-static:latest"
CONTAINER_REPO = "/repo"
CONTAINER_WORK = "/work"

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Definition location -> node
# --------------------------------------------------------------------------

@dataclass
class NodeLocator:
    """Exact-line lookup from a definition location to an inventoried node."""

    inv: RepoInventory
    index: RepoIndex
    by_line: dict[tuple[str, int], list[Node]] = field(default_factory=dict)
    impl_for_overload: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for node in self.inv.nodes:
            if node.qualified_symbol == MODULE_SYMBOL:
                continue
            self.by_line.setdefault((node.relative_path, node.lineno), []).append(node)
        # An @overload stub is not callable (nodes.py); a definition that lands
        # on one is redirected to the implementation that shares its name.
        for node in self.inv.nodes:
            if node.overload_stub:
                base = node.qualified_symbol.rsplit(".<overload#", 1)[0]
                impl = f"{node.relative_path}::{base}"
                if impl in self.index.nodes_by_key:
                    self.impl_for_overload[node.key] = impl

    def locate(self, relative_path: str, line1: int) -> tuple[str | None, str]:
        """Returns (node_key, reason). `reason` is recorded either way."""
        candidates = self.by_line.get((relative_path, line1), [])
        if not candidates:
            return None, "no_node_at_definition_line"
        # A class and a method never share a line; a lambda and its assignment
        # target can, in which case the lambda is the callable one.
        node = sorted(candidates, key=lambda n: (n.kind != "lambda", n.col_offset))[0]
        if node.overload_stub:
            impl = self.impl_for_overload.get(node.key)
            return (impl, "overload_redirected") if impl else (None, "overload_no_impl")
        if node.kind == "class_body":
            init = self.index.lookup_member(node.key, "__init__")
            if init is None:
                # The runtime callee is object.__init__, a C builtin: out of
                # universe by §2.1 rather than a miss.
                return None, "class_without_init"
            return init.key, "class_to_init"
        if node.is_callable:
            return node.key, "ok"
        return None, "definition_not_callable"


# --------------------------------------------------------------------------
# Driving the server
# --------------------------------------------------------------------------

@dataclass
class ProbeRun:
    """One `docker run` of `pyright_probe.py`, plus how it went."""

    status: str
    results: dict[str, list]
    files: list[dict]
    reasons: dict[str, int]
    server_restarts: int = 0
    wall_seconds: float = 0.0
    stderr_tail: str = ""


def probe_argv(repo: Path, work: Path, image: str, site_packages: str | None
               ) -> tuple[list[str], Path, bool]:
    """(argv, root as the probe sees it, in_docker).

    `--image none` runs the probe as a local subprocess instead, for a host that
    has `pyright-langserver` on PATH. Only used for development: MIGRATION.md §4
    keeps static extraction on the execution host with the corpus, so the
    artifact is one machine's output end to end.
    """
    if image == "none":
        return ([sys.executable, str(HERE / "pyright_probe.py")], repo, False)
    argv = [
        "docker", "run", "--rm",
        "-e", f"WORK_DIR={CONTAINER_WORK}",
        "-v", f"{repo}:{CONTAINER_REPO}:ro",
        "-v", f"{work}:{CONTAINER_WORK}",
    ]
    if site_packages:
        argv += ["-v", f"{site_packages}:/site-packages:ro"]
    argv += ["-v", f"{HERE}:/s:ro", "--entrypoint", "python3", image,
             "/s/pyright_probe.py"]
    return argv, Path(CONTAINER_REPO), True


def build_requests(inv: RepoInventory, sites: list[CallSite], root: Path,
                   chunk: int, ready_timeout: float, request_timeout: float
                   ) -> tuple[dict, dict[str, CallSite]]:
    """One position per call site that has a callee identifier to point at.

    Columns are converted to UTF-16 here, on the host, where the source text
    lives: LSP counts UTF-16 code units and `ast` counts UTF-8 bytes, and on any
    line with a non-ASCII character the two disagree (see `lsp.utf16_column`).
    """
    source_by_path = {m.relative_path: m.source for m in inv.modules}
    by_site: dict[str, CallSite] = {}
    files = []
    for rel in sorted({s.relative_path for s in sites}):
        lines = source_by_path.get(rel, "").splitlines()
        positions = []
        for site in sites:
            if site.relative_path != rel or site.callee_lineno is None:
                continue
            line_text = (lines[site.callee_lineno - 1]
                         if 0 < site.callee_lineno <= len(lines) else "")
            positions.append({
                "id": site.site_id,
                "line": site.callee_lineno - 1,
                "char": utf16_column(line_text, site.callee_char or 0),
            })
            by_site[site.site_id] = site
        if positions:
            files.append({"relative_path": rel, "positions": positions})
    spec = {
        "root": str(root),
        "chunk": chunk,
        "ready_timeout": ready_timeout,
        "request_timeout": request_timeout,
        "files": files,
    }
    return spec, by_site


def run_probe(repo: Path, work: Path, spec: dict, image: str,
              site_packages: str | None, timeout: float,
              stream_progress: bool = True) -> ProbeRun:
    work.mkdir(parents=True, exist_ok=True)
    (work / "requests.json").write_text(json.dumps(spec))
    argv, _, _ = probe_argv(repo, work, image, site_packages)
    env = dict(os.environ)
    if image == "none":
        env["WORK_DIR"] = str(work)
    try:
        proc = subprocess.run(
            argv, timeout=timeout, env=env,
            stdout=subprocess.DEVNULL,
            stderr=None if stream_progress else subprocess.PIPE, text=True)
        rc, err = proc.returncode, (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc, err = -1, f"probe timed out after {timeout}s: {exc}"
    except FileNotFoundError as exc:
        return ProbeRun(f"probe_unavailable: {exc}", {}, [], {})

    out_path = work / "definitions.json"
    if not out_path.exists():
        return ProbeRun(f"probe_produced_nothing (rc={rc})", {}, [], {},
                        stderr_tail=err[-2000:])
    payload = json.loads(out_path.read_text())
    return ProbeRun(
        status=payload.get("status", "ok") if rc == 0 else f"{payload.get('status')} (rc={rc})",
        results=payload.get("results", {}),
        files=payload.get("files", []),
        reasons=payload.get("reasons", {}),
        server_restarts=payload.get("server_restarts", 0),
        wall_seconds=payload.get("wall_seconds", 0.0),
        stderr_tail=err[-2000:],
    )


def resolve_edges(sites: list[CallSite], by_site: dict[str, CallSite],
                  run: ProbeRun, locator: NodeLocator, probe_root: Path,
                  repo: Path) -> tuple[StaticEdgeSet, dict]:
    """Definition locations -> edges, with every call site accounted for once."""
    edges = StaticEdgeSet(BASELINE)
    reasons: dict[str, int] = dict(run.reasons)
    unresolved_by_type: dict[str, int] = {}
    resolved_by_type: dict[str, int] = {}

    def note(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    for site in sites:
        answer = run.results.get(site.site_id) if site.site_id in by_site else None
        asked = site.site_id in by_site
        if not asked:
            note("no_callee_identifier")
        elif answer is None:
            # Absent from results is NOT the same as an empty answer: the server
            # never got to this position. Counting it as unresolvable would
            # convert a harness failure into a finding.
            note("no_answer_from_server")

        in_repo_targets: list[str] = []
        external = 0
        for loc in (answer or []):
            rel_target = _relativize(loc["path"], probe_root, repo)
            if rel_target is None:
                note("definition_outside_repo")
                external += 1
                edges.add_external(site.owner)
                continue
            key, reason = locator.locate(rel_target, loc["line"] + 1)
            note(f"locate_{reason}")
            if key:
                in_repo_targets.append(key)
        if answer is not None and len(answer) > 1:
            note("multi_definition")
        if answer == []:
            note("pyright_resolved_nothing")

        if in_repo_targets:
            for key in dict.fromkeys(in_repo_targets):
                edges.add_in_universe(site.owner, key)
                edges.note_provenance("pyright")
            resolved_by_type[site.edge_type] = resolved_by_type.get(site.edge_type, 0) + 1
        elif external:
            # Pyright DID resolve this, into typeshed or a dependency. Out of
            # universe by §2.1, but emphatically not an UnresolvedDispatch:
            # §4.4's census is "statically unresolvable call sites", and `len()`
            # is not one of them. Counting these would swamp the honest-unknowns
            # figure with every builtin call in the corpus.
            resolved_by_type[site.edge_type] = resolved_by_type.get(site.edge_type, 0) + 1
        elif site.resolved_target:
            edges.add_in_universe(site.owner, site.resolved_target)
            edges.note_provenance("ast_fallback")
            note("fallback_to_ast")
            resolved_by_type[site.edge_type] = resolved_by_type.get(site.edge_type, 0) + 1
        else:
            edges.add_unmapped("unresolved_call_site")
            unresolved_by_type[site.edge_type] = unresolved_by_type.get(site.edge_type, 0) + 1

    diagnostics = {
        "probe_status": run.status,
        "server_restarts": run.server_restarts,
        "probe_wall_seconds": run.wall_seconds,
        "files": len(run.files),
        "files_unready": sum(1 for f in run.files if not f.get("ready", True)),
        "call_sites": len(sites),
        "sites_asked": len(by_site),
        "sites_answered": len(run.results),
        "reasons": dict(sorted(reasons.items())),
        "resolved_by_edge_type": dict(sorted(resolved_by_type.items())),
        # §4.4: the UnresolvedDispatch census starts here -- the call sites NO
        # resolver could settle, before any workload has had a chance at them.
        "unresolved_by_edge_type": dict(sorted(unresolved_by_type.items())),
        "slowest_files": sorted(run.files, key=lambda f: -f.get("seconds", 0))[:5],
    }
    if run.stderr_tail:
        diagnostics["probe_stderr_tail"] = run.stderr_tail
    return edges, diagnostics


def extract(repo: Path, inv: RepoInventory, sites: list[CallSite],
            index: RepoIndex, work: Path, image: str = DEFAULT_IMAGE,
            site_packages: str | None = None, chunk: int = 64,
            request_timeout: float = 60.0, ready_timeout: float = 180.0,
            probe_timeout: float = 7200.0, stream_progress: bool = True
            ) -> tuple[StaticEdgeSet, dict]:
    _, probe_root, in_docker = probe_argv(repo, work, image, site_packages)
    spec, by_site = build_requests(inv, sites, probe_root, chunk,
                                   ready_timeout, request_timeout)
    run = run_probe(repo, work, spec, image, site_packages, probe_timeout,
                    stream_progress)
    locator = NodeLocator(inv, index)
    edges, diagnostics = resolve_edges(sites, by_site, run, locator,
                                       probe_root, repo)
    diagnostics.update({
        "in_docker": in_docker,
        "deps_available": bool(site_packages),
        "chunk": chunk,
    })
    return edges, diagnostics


def _relativize(abs_path: str, probe_root: Path, repo: Path) -> str | None:
    for root in (probe_root, repo):
        try:
            return str(Path(abs_path).relative_to(Path(root)))
        except ValueError:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Pyright-assisted static baseline.")
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--package", required=True)
    ap.add_argument("--src-root", default=".")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--image", default=DEFAULT_IMAGE,
                    help="pinned image, or 'none' to run the probe locally "
                         "against a host pyright-langserver")
    ap.add_argument("--site-packages",
                    help="host path to a triaged environment's site-packages, "
                         "mounted read-only to strengthen inference")
    ap.add_argument("--work", type=Path,
                    help="working dir for requests.json / definitions.json "
                         "(default: a temp dir, removed afterwards)")
    ap.add_argument("--chunk", type=int, default=64,
                    help="definition requests in flight per batch")
    ap.add_argument("--request-timeout", type=float, default=60.0)
    ap.add_argument("--ready-timeout", type=float, default=180.0)
    ap.add_argument("--probe-timeout", type=float, default=7200.0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--counts-only", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    exclude = {n for n in args.exclude.split(",") if n}
    inv = inventory_repo(repo, repo / args.package, repo / args.src_root, exclude)
    sites, index = analyse_repo(inv)

    tempdir = None
    if args.work:
        work = args.work.expanduser().resolve()
    else:
        # Under $HOME, never /tmp: MANIFEST §1.1 -- Docker Desktop cannot
        # bind-mount /tmp on either host, and this dir is a bind mount.
        tempdir = tempfile.mkdtemp(prefix="tw-pyright-",
                                   dir=str(Path.home()))
        work = Path(tempdir)
    try:
        edges, diagnostics = extract(
            repo, inv, sites, index, work, image=args.image,
            site_packages=args.site_packages, chunk=args.chunk,
            request_timeout=args.request_timeout,
            ready_timeout=args.ready_timeout, probe_timeout=args.probe_timeout,
            stream_progress=not args.quiet,
        )
    finally:
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)
    if str(diagnostics.get("probe_status", "")).startswith(
            ("probe_unavailable", "probe_produced_nothing", "server_unavailable")):
        print(f"pyright probe failed: {diagnostics['probe_status']}", file=sys.stderr)
        if diagnostics.get("probe_stderr_tail"):
            print(diagnostics["probe_stderr_tail"], file=sys.stderr)
        return 3

    payload = {
        "baseline": BASELINE,
        "baseline_version": BASELINE_VERSION,
        "tool_pin": TOOL_PIN,
        "spec_version": "1.0",
        "repo": str(repo),
        "package": args.package,
        "src_root": args.src_root,
        "inventory": inv.counts(),
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
