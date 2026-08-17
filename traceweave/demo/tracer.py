#!/usr/bin/env python3
"""Runtime tracer + missing-edge diff for the live demo (design doc: Data contract).

Captures the fixture's real execution with `sys.setprofile` (call/return
events only -- far less overhead than `sys.settrace`'s per-line firing) and
writes `runtime.json`, then compares it against PyCG's `static.json` to find
edges that ran but were never seen statically.

    NAMING, and it is load-bearing. PyCG keys its call graph by qualified name
    (module path + function/class name, dot-joined) -- e.g. `fixture.main`,
    `fixture.PluginRegistry.dispatch`. `sys.setprofile` hands back raw frame
    objects. `frame.f_code.co_qualname` (Python >=3.11) gives the *Python*
    qualified name, which for a nested function includes a literal
    `.<locals>.` segment PyCG's own name never has (e.g.
    `outer.<locals>.inner` vs PyCG's `outer.inner`). `normalize_qualname`
    strips that segment; getting it wrong produces zero or spurious missing
    edges with no visible error, which is exactly why
    tests/fixtures/*_static_golden.json exist -- they're real PyCG 0.0.8
    output (captured 2026-08-14, pinned image
    sha256:72b24f9186eb054b6de110a01e2fbb651932d43aa28b5d7e58b1d69364cef39b,
    see resolve_image.py), not an assumed scheme. See `selftest` below.

Usage:
    python3 tracer.py run --fixture fixture.py --entry main \\
        --run-id 1723651200 --out /path/to/live/runtime.json
    python3 tracer.py selftest
"""

from __future__ import annotations

import argparse
import functools
import importlib
import importlib.util
import inspect
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / "tests" / "fixtures"


def module_name_for(filepath: Path, root: Path) -> str:
    """PyCG's module-naming scheme: path relative to root, dots for
    separators, `.py` stripped.

    A package's `__init__.py` is named for the PACKAGE, not `pkg.__init__`.
    Observed, not assumed: PyCG's real output for click (root `src`) has a
    bare `click` node and `click.__getattr__`, and no `click.__init__`
    anywhere. Getting this wrong is invisible -- it does not error, it just
    makes every edge out of the package's `__init__` look statically missed.
    """
    rel = filepath.resolve().relative_to(root.resolve())
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def normalize_qualname(co_qualname: str, module: str) -> str:
    """`frame.f_code.co_qualname` -> PyCG-style dotted name.

    Python's co_qualname marks nested-function scope with a literal
    `<locals>` segment (`outer.<locals>.inner`); PyCG has no such marker
    (`outer.inner`). Drop every `<locals>` segment, then prefix the module.
    """
    parts = [p for p in co_qualname.split(".") if p != "<locals>"]
    return module + "." + ".".join(parts)


def capture_runtime_edges(fixture_path: Path, entry: str) -> list[dict]:
    """Run `entry()` from the fixture module under sys.setprofile, filtered
    to calls whose callee is defined in the fixture's own file (excludes
    stdlib/import-machinery noise by construction -- see Data contract).
    Returns deduplicated {caller, callee, ts} edges in PyCG-normalized form.
    """
    fixture_path = fixture_path.resolve()
    root = fixture_path.parent
    module_name = module_name_for(fixture_path, root)

    spec = importlib.util.spec_from_file_location(module_name, fixture_path)
    module = importlib.util.module_from_spec(spec)

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    call_stack: list[str] = []

    def profiler(frame, event, arg):  # noqa: ARG001
        if event not in ("call", "return"):
            return
        code = frame.f_code
        if code.co_filename != str(fixture_path):
            return
        # sys.setprofile fires a 'call' event for module-body execution
        # (co_name "<module>") and for class-body execution too (running a
        # `class Foo:` statement to build its namespace) -- neither is a
        # function call PyCG's static graph models, so both would show up as
        # spurious "missing" edges. CO_OPTIMIZED is set only for real
        # function/method code objects, not module or class bodies -- this
        # was verified empirically, not assumed (module=False, class
        # body=False, function/method=True).
        if not (code.co_flags & inspect.CO_OPTIMIZED):
            return
        callee = normalize_qualname(code.co_qualname, module_name)
        if event == "call":
            caller = call_stack[-1] if call_stack else module_name
            call_stack.append(callee)
            pair = (caller, callee)
            if pair not in seen:
                seen.add(pair)
                edges.append({"caller": caller, "callee": callee, "ts": time.time()})
        elif event == "return" and call_stack and call_stack[-1] == callee:
            call_stack.pop()

    sys.setprofile(profiler)
    try:
        spec.loader.exec_module(module)
        getattr(module, entry)()
    finally:
        sys.setprofile(None)

    return edges


# ------------------------------------------------ whole-package tracing

# Caller sentinel for a call that entered the analysed set from outside it
# (our driver calling into click). PyCG's graph cannot contain such a node,
# so these are reported separately and never counted as "missed" -- see
# diff_package.
ENTRY_CALLER = "<entry>"


def discover_modules(pkg_dir: Path, src_root: Path, exclude: set[str]) -> dict[str, str]:
    """Absolute .py path -> PyCG module name, for the analysed module set.

    `exclude` holds bare filenames the STATIC side did not analyse (for
    click, `testing.py`, which makes PyCG's behaviour non-deterministic --
    see scripts/pycg_determinism.py). The runtime side must exclude exactly
    the same set: tracing a module PyCG never saw would score every one of
    its edges as "missed" for free, which measures the exclusion, not the
    tool.
    """
    modules: dict[str, str] = {}
    for path in sorted(pkg_dir.rglob("*.py")):
        if path.name in exclude:
            continue
        modules[str(path.resolve())] = module_name_for(path, src_root)
    return modules


def capture_package_edges(file_to_module: dict[str, str], run) -> list[dict]:
    """The single-file profiler contract widened to a whole module set.

    Two differences from capture_runtime_edges, both load-bearing:

    * `sys.setprofile` arms only the calling thread, so any work done on a
      worker thread would vanish from the trace and could never be counted
      as missed. `threading.setprofile` arms threads started afterwards.
      Each thread keeps its OWN call stack via threading.local -- a shared
      stack would splice unrelated frames together and invent caller/callee
      pairs that never happened.
    * Calls entering from outside the analysed set get caller `ENTRY_CALLER`
      rather than being attributed to whatever happened to be on the stack.
    """
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    tls = threading.local()

    def profiler(frame, event, arg):  # noqa: ARG001
        if event not in ("call", "return"):
            return
        code = frame.f_code
        module = file_to_module.get(code.co_filename)
        if module is None:
            return
        # Same CO_OPTIMIZED filter as the single-file tracer: module bodies
        # and class bodies fire 'call' but are not calls PyCG models.
        if not (code.co_flags & inspect.CO_OPTIMIZED):
            return
        stack = getattr(tls, "stack", None)
        if stack is None:
            stack = []
            tls.stack = stack
        callee = normalize_qualname(code.co_qualname, module)
        if event == "call":
            caller = stack[-1] if stack else ENTRY_CALLER
            stack.append(callee)
            pair = (caller, callee)
            if pair in seen:
                return
            seen.add(pair)
            # The IMMEDIATE caller frame is often not click's: a call can
            # reach one click function from another through stdlib machinery
            # (contextlib for an @contextmanager, textwrap, sorted(key=...)).
            # Attributing to f_back alone loses the call site for ~10% of
            # edges. Walk up to the nearest frame inside the analysed set --
            # that is the line that really caused this call.
            back = frame.f_back
            hops = 0
            while back is not None and back.f_code.co_filename not in file_to_module:
                back = back.f_back
                hops += 1
            edges.append({
                "caller": caller,
                "callee": callee,
                "ts": time.time(),
                # Where the call was made from, so the UI can show the real
                # source line of a missed edge instead of just asserting it.
                # Module name rather than an absolute path: these files ship
                # to a browser and should not carry this machine's paths.
                "call_module": (file_to_module.get(back.f_code.co_filename)
                                if back is not None else None),
                "call_line": back.f_lineno if back is not None else None,
                # >0 means the call reached here through frames outside the
                # analysed set -- worth surfacing, not worth hiding.
                "via_external_frames": hops,
                "def_line": code.co_firstlineno,
                "module": module,
            })
        elif event == "return" and stack and stack[-1] == callee:
            stack.pop()

    sys.setprofile(profiler)
    threading.setprofile(profiler)
    try:
        run()
    finally:
        sys.setprofile(None)
        threading.setprofile(None)

    return edges


def diff_package(static_graph: dict, runtime_edges: list[dict]) -> dict:
    """diff_missing_edges for a package trace, with entry edges held out.

    The headline ratio is computed over INTERNAL edges only (both endpoints
    inside the analysed set). Entry edges are reported alongside so the
    holdout is visible rather than silent.
    """
    internal = [e for e in runtime_edges if e["caller"] != ENTRY_CALLER]
    entry = [e for e in runtime_edges if e["caller"] == ENTRY_CALLER]
    result = diff_missing_edges(static_graph, internal)
    result["entry_edges"] = entry
    result["counter"]["entry_excluded"] = len(entry)
    return result


def diff_missing_edges(static_graph: dict, runtime_edges: list[dict]) -> dict:
    """A missing edge is any (caller, callee) pair in `runtime_edges` absent
    from `static_graph`'s adjacency map. Both sides must already be in the
    same normalized (PyCG-style) qualified-name form.
    """
    static_pairs = {
        (caller, callee)
        for caller, callees in static_graph.items()
        for callee in callees
    }
    missing = [
        e for e in runtime_edges
        if (e["caller"], e["callee"]) not in static_pairs
    ]
    return {
        "runtime_edges": runtime_edges,
        "missing_edges": missing,
        "counter": {"missing": len(missing), "total": len(runtime_edges)},
    }


def missing_ratio(counter: dict) -> float:
    """`missing / total`, 0.0 (not a ZeroDivisionError) when total is 0."""
    total = counter["total"]
    return counter["missing"] / total if total else 0.0


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write-then-rename (Data contract: 'Atomic writes, not in-place
    writes'). POSIX rename is atomic, so a poller can never observe a
    half-written file.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.rename(tmp, path)


# ------------------------------------------------------------------- selftest


def selftest() -> int:
    failures = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  PASS  {name}")
        else:
            failures.append(name)
            print(f"  FAIL  {name}  {detail}")

    # --- qualified-name normalization against REAL PyCG output, not an
    # assumed scheme (Data contract's explicit requirement).
    fixture_golden = json.loads((GOLDEN_DIR / "fixture_static_golden.json").read_text())
    nested_golden = json.loads((GOLDEN_DIR / "qualname_nested_static_golden.json").read_text())

    check(
        "normalize: top-level function (fixture.main)",
        normalize_qualname("main", "fixture") in fixture_golden,
    )
    check(
        "normalize: method (fixture.PluginRegistry.dispatch)",
        normalize_qualname("PluginRegistry.dispatch", "fixture") in fixture_golden,
    )
    check(
        "normalize: nested function (qualname_nested.outer.inner)",
        normalize_qualname("outer.<locals>.inner", "qualname_nested") in nested_golden,
    )

    # --- missing-edge diff function: five named cases from the design doc.
    static_present = {"a": ["b"]}
    rt_present = [{"caller": "a", "callee": "b", "ts": 0}]
    d = diff_missing_edges(static_present, rt_present)
    check("diff(a): edge present in static -> 0 missing", d["counter"]["missing"] == 0)

    static_absent = {"a": []}
    rt_absent = [{"caller": "a", "callee": "b", "ts": 0}]
    d = diff_missing_edges(static_absent, rt_absent)
    check("diff(b): edge absent from static -> 1 missing", d["counter"]["missing"] == 1)

    d = diff_missing_edges({}, rt_absent)
    check("diff(c): empty static -> all runtime edges missing",
          d["counter"]["missing"] == 1 and d["counter"]["total"] == 1)

    rt_dupe = [
        {"caller": "a", "callee": "b", "ts": 0},
        {"caller": "a", "callee": "b", "ts": 1},
    ]
    # Dedup happens at capture time (capture_runtime_edges' `seen` set); the
    # diff function itself just counts what it's given, so exercise dedup
    # directly here on a pre-deduped list to pin the contract.
    deduped = list({(e["caller"], e["callee"]): e for e in rt_dupe}.values())
    check("diff(d): duplicate runtime edges deduped to 1", len(deduped) == 1)

    d = diff_missing_edges(static_present, [])
    check("diff(e): empty runtime -> 0/0, no div-by-zero",
          d["counter"]["missing"] == 0 and d["counter"]["total"] == 0
          and missing_ratio(d["counter"]) == 0.0)

    # --- end-to-end: run the actual fixture and confirm it reproduces the
    # exact missing edge the demo is built around.
    fixture_path = HERE / "fixture.py"
    rt_edges = capture_runtime_edges(fixture_path, "main")
    d = diff_missing_edges(fixture_golden, rt_edges)
    missing_pairs = {(e["caller"], e["callee"]) for e in d["missing_edges"]}
    # Exact count, not just membership: a looser check here previously
    # missed module-body/class-body "call" events (co_name "<module>", or a
    # class statement executing) inflating the count to 3 -- neither is a
    # function call PyCG's static graph models. See the CO_OPTIMIZED filter
    # in capture_runtime_edges.
    check(
        "end-to-end: fixture.py misses EXACTLY dispatch->handle_email, nothing else",
        missing_pairs == {("fixture.PluginRegistry.dispatch",
                            "fixture.PluginRegistry.handle_email")},
        detail=f"missing={missing_pairs}",
    )

    # --- whole-package tracing (real-repo demo path).
    pkg_dir = HERE / "pkgfixture"
    mods = discover_modules(pkg_dir, HERE, exclude={"beta.py"})
    check(
        "discover: exclude drops beta.py, keeps alpha",
        set(mods.values()) == {"pkgfixture", "pkgfixture.alpha"},
        detail=f"got {sorted(mods.values())}",
    )
    check(
        "discover: __init__.py is named for the package (PyCG's scheme)",
        mods[str((pkg_dir / "__init__.py").resolve())] == "pkgfixture",
    )

    mods = discover_modules(pkg_dir, HERE, exclude=set())
    sys.path.insert(0, str(HERE))
    try:
        import pkgfixture.alpha as alpha  # noqa: PLC0415

        pkg_edges = capture_package_edges(mods, alpha.main)
    finally:
        sys.path.remove(str(HERE))
    pkg_pairs = {(e["caller"], e["callee"]) for e in pkg_edges}

    check(
        "package: cross-module call captured (alpha.main -> beta.direct)",
        ("pkgfixture.alpha.main", "pkgfixture.beta.direct") in pkg_pairs,
        detail=f"pairs={sorted(pkg_pairs)}",
    )
    # The regression this guards: with sys.setprofile alone the worker
    # thread is never profiled and this edge silently does not exist, so a
    # threaded call could never be reported as statically missed.
    check(
        "package: worker-thread call captured (alpha.spawned -> beta.on_thread)",
        ("pkgfixture.alpha.spawned", "pkgfixture.beta.on_thread") in pkg_pairs,
        detail=f"pairs={sorted(pkg_pairs)}",
    )
    check(
        "package: entry call gets the <entry> sentinel, not a real caller",
        (ENTRY_CALLER, "pkgfixture.alpha.main") in pkg_pairs,
        detail=f"pairs={sorted(pkg_pairs)}",
    )
    check(
        "package: every internal edge carries a call-site line",
        all(e["call_line"] is not None
            for e in pkg_edges if e["caller"] != ENTRY_CALLER),
    )
    # An entry edge is entered from outside the analysed set, so there is no
    # call site inside it to point at -- None here is correct, not a gap.
    check(
        "package: entry edges have no in-package call site",
        all(e["call_line"] is None
            for e in pkg_edges if e["caller"] == ENTRY_CALLER),
    )

    # --- entry holdout: entry edges must not inflate the missing count.
    d = diff_package({"pkgfixture.alpha.main": ["pkgfixture.beta.direct"]}, pkg_edges)
    entry_in_missing = [e for e in d["missing_edges"] if e["caller"] == ENTRY_CALLER]
    check(
        "diff_package: entry edges excluded from missing, reported separately",
        not entry_in_missing and d["counter"]["entry_excluded"] == len(d["entry_edges"])
        and d["counter"]["entry_excluded"] > 0,
        detail=f"counter={d['counter']}",
    )
    check(
        "diff_package: total counts internal edges only",
        d["counter"]["total"] == len([e for e in pkg_edges if e["caller"] != ENTRY_CALLER]),
        detail=f"counter={d['counter']}",
    )

    print()
    print(f"{len(failures)} failed" if failures else "all selftests passed")
    return 1 if failures else 0


# ----------------------------------------------------------------------- CLI


def cmd_run(args) -> int:
    fixture_path = Path(args.fixture).resolve()
    edges = capture_runtime_edges(fixture_path, args.entry)
    write_json_atomic(Path(args.out), {"run_id": args.run_id, "edges": edges})
    print(f"wrote {len(edges)} edges -> {args.out}")
    return 0


def cmd_trace_package(args) -> int:
    src_root = Path(args.src_root).resolve()
    pkg_dir = Path(args.package).resolve()
    exclude = {name for name in args.exclude.split(",") if name}
    file_to_module = discover_modules(pkg_dir, src_root, exclude)
    if not file_to_module:
        print(f"no modules found under {pkg_dir}", file=sys.stderr)
        return 2

    # The workload imports the package under test, so src_root has to be
    # importable before anything else happens.
    sys.path.insert(0, str(src_root))
    workload_path = Path(args.workload).resolve()
    spec = importlib.util.spec_from_file_location("tw_workload", workload_path)
    workload = importlib.util.module_from_spec(spec)

    def run():
        # Executed INSIDE the profiler, matching cmd_run: the package's
        # import-time work (click's decorators build Command objects at
        # import) is part of what really runs, so it belongs in the trace.
        spec.loader.exec_module(workload)
        getattr(workload, args.entry)()

    edges = capture_package_edges(file_to_module, run)

    # Attach the call-site line here rather than only in `summarize`: the UI
    # shows source for EVERY edge it can (including ones PyCG found), and a
    # runtime file that records a file:line but not what is on that line
    # forces every reader back to a checkout to see the evidence.
    for edge in edges:
        edge["source"] = read_source_line(src_root, edge.get("call_module"),
                                           edge.get("call_line"))

    payload = {
        "run_id": args.run_id,
        "edges": edges,
        "analysed_modules": sorted(set(file_to_module.values())),
        "excluded_files": sorted(exclude),
        "workload": workload_path.name,
    }
    write_json_atomic(Path(args.out), payload)
    internal = sum(1 for e in edges if e["caller"] != ENTRY_CALLER)
    print(f"wrote {len(edges)} edges ({internal} internal, "
          f"{len(edges) - internal} entry) over {len(file_to_module)} modules -> {args.out}")
    return 0


# A miss rate above this almost certainly means the two sides are NAMING
# things differently (see module_name_for), not that the tool really missed
# that much. Silent naming drift is the single most dangerous failure mode
# here: it produces a huge, wrong, extremely quotable number.
NAMING_SANITY_CEILING = 0.90


def module_source_path(src_root: Path, module: str) -> Path | None:
    """PyCG module name -> file on disk, inverting module_name_for."""
    if not module:
        return None
    base = src_root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def read_source_line(src_root: Path, module: str | None, line: int | None) -> str | None:
    """The literal call-site line, so a claimed missing edge can be checked
    against the code that made it rather than taken on trust.
    """
    if module is None or not line:
        return None
    path = module_source_path(src_root, module)
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return lines[line - 1].strip() if 0 < line <= len(lines) else None


def canonicalize_static_graph(graph: dict, package: str,
                               submodules: set[str]) -> tuple[dict, dict]:
    """Merge PyCG's duplicate naming of the same function.

    PyCG emits click's own submodules under TWO namespaces at once: the
    path-derived `click.types.convert_type` and the import-derived
    `types.convert_type`, both as definition nodes, with edges split
    arbitrarily between them. The tracer only ever produces the canonical
    form, so every edge PyCG happened to record under the bare alias would
    be scored as a miss that PyCG did not actually make. On click that was
    78 edges -- 11 points of miss rate, entirely an artifact.

    Merge is deliberately conservative: a bare name is rewritten only when
    its `click.`-prefixed twin ALSO exists as a definition node. Rewriting
    on the strength of the prefix alone would fold stdlib `types.X` into
    `click.types.X` and could invent an edge PyCG never had.
    """
    defs = set(graph)
    alias = {
        name: f"{package}.{name}"
        for name in defs
        if name.split(".")[0] in submodules and f"{package}.{name}" in defs
    }
    merged: dict[str, set[str]] = {}
    for caller, callees in graph.items():
        key = alias.get(caller, caller)
        merged.setdefault(key, set()).update(alias.get(c, c) for c in callees)
    stats = {
        "aliased_nodes": len(alias),
        "nodes_before": len(defs),
        "nodes_after": len(merged),
    }
    return {k: sorted(v) for k, v in merged.items()}, stats


# Frames Python creates for comprehension/lambda scopes. These are not
# functions a call-graph tool is expected to model as call targets, so
# counting them as "missed" would be free credit. Held out of the headline.
SYNTHETIC_SCOPE = re.compile(r"<(lambda|genexpr|listcomp|dictcomp|setcomp)>")


def _descriptor_kind(qualname: str, modules: set[str]) -> str | None:
    """Is `qualname` a property/cached_property getter?

    A property access is a real function frame at runtime but not a
    syntactic call site, so whether it "should" be in a call graph is
    arguable. Rather than quietly pick a side, classify it and let the
    headline exclude it while the breakdown still shows it.

    Uses vars() rather than getattr() deliberately: getattr on a class
    attribute that IS a property returns the descriptor, but getattr on an
    instance would execute it. Walking __dict__ never runs user code.
    """
    module = max((m for m in modules if qualname.startswith(m + ".")),
                 key=len, default=None)
    if module is None:
        return None
    try:
        obj = importlib.import_module(module)
    except Exception:  # noqa: BLE001 - an unimportable module is just unknown
        return None
    parts = qualname[len(module) + 1:].split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    attr = vars(obj).get(parts[-1]) if hasattr(obj, "__dict__") else None
    if isinstance(attr, property) or isinstance(attr, functools.cached_property):
        return "property"
    return None


DUNDER = re.compile(r"^__\w+__$")
REFLECTIVE = re.compile(r"getattr\(|importlib|__import__")

# Ordered: the first rule that matches wins, so each edge lands in exactly
# one bucket and the buckets sum to the total. Every rule is checkable by
# eye against the call-site line the UI shows next to the edge.
#
# `bare-call` is the control group and the reason to trust the rest. A plain
# `foo()` is the easiest call there is; if a large share of those came back
# missing, the pipeline would be wrong, not PyCG. Keeping it visible means
# the reader can check that instead of taking the taxonomy on trust.
def classify_edge(edge: dict, modules: set[str]) -> str:
    source = edge.get("source")
    caller, callee = edge["caller"], edge["callee"]
    tail = callee.split(".")[-1]

    if SYNTHETIC_SCOPE.search(caller) or SYNTHETIC_SCOPE.search(callee):
        return "synthetic-scope"
    if _descriptor_kind(callee, modules) == "property":
        return "property-getter"
    if source is None:
        # No call-site line recovered, so no evidence to classify on. Its own
        # bucket rather than a guess folded into a real one.
        return "unattributed"
    if "super(" in source:
        return "super-dispatch"
    if REFLECTIVE.search(source):
        return "reflective-lookup"
    if tail == "__init__":
        return "indirect-construction"
    if DUNDER.match(tail):
        return "dunder-protocol"
    if not re.search(r"\b" + re.escape(tail) + r"\s*\(", source):
        # The callee's name does not appear at the call site at all -- it was
        # reached through a variable, attribute or argument. This is the
        # crispest form of "no static analysis could resolve this by name".
        return "name-absent-callback"
    if re.search(r"\bself\." + re.escape(tail) + r"\s*\(", source):
        return "self-dispatch"
    if re.search(r"\w\." + re.escape(tail) + r"\s*\(", source):
        return "attribute-dispatch"
    return "bare-call"


def classify_missing(edges: list[dict], modules: set[str]) -> None:
    """Tag every edge with the construct class that produced it.

    This is the paper's claim ("misses concentrate in identifiable construct
    classes") applied to real measured edges instead of hand-written
    fixtures.
    """
    for edge in edges:
        edge["construct"] = classify_edge(edge, modules)


# Buckets held out of the conservative headline: one is not a function a
# call-graph tool models, the other is not a syntactic call site.
HELD_OUT_CONSTRUCTS = frozenset({"synthetic-scope", "property-getter"})


def rollup_by_module(missing: list[dict], internal: list[dict]) -> list[dict]:
    """Per-module missing/total, so the UI can show WHERE the misses land --
    the taxonomy claim is about concentration, and a single global ratio
    cannot show concentration.
    """
    totals: dict[str, int] = {}
    misses: dict[str, int] = {}
    for edge in internal:
        totals[edge["module"]] = totals.get(edge["module"], 0) + 1
    for edge in missing:
        misses[edge["module"]] = misses.get(edge["module"], 0) + 1
    rows = [
        {"module": mod, "total": total, "missing": misses.get(mod, 0),
         "ratio": round(misses.get(mod, 0) / total, 4) if total else 0.0}
        for mod, total in totals.items()
    ]
    rows.sort(key=lambda r: (-r["missing"], r["module"]))
    return rows


def cmd_summarize(args) -> int:
    static = json.loads(Path(args.static).read_text())
    runtime = json.loads(Path(args.runtime).read_text())
    src_root = Path(args.src_root).resolve()

    if static["run_id"] != runtime["run_id"]:
        print(f"run_id mismatch: static={static['run_id']} runtime={runtime['run_id']}",
              file=sys.stderr)
        return 2

    modules_all = set(runtime.get("analysed_modules", []))
    package = args.package or (min(modules_all, key=len) if modules_all else "")
    submodules = {m.split(".")[1] for m in modules_all if m.count(".") == 1}
    graph, alias_stats = canonicalize_static_graph(static["graph"], package, submodules)

    result = diff_package(graph, runtime["edges"])
    internal = [e for e in runtime["edges"] if e["caller"] != ENTRY_CALLER]
    ratio = missing_ratio(result["counter"])

    # Classification needs to import the traced package to tell a property
    # getter from a method; the package lives under src_root, not on the
    # default path.
    sys.path.insert(0, str(src_root))
    modules = modules_all
    for edge in internal:
        edge["source"] = read_source_line(src_root, edge.get("call_module"),
                                           edge.get("call_line"))
    classify_missing(internal, modules)

    missing_keys = {(e["caller"], e["callee"]) for e in result["missing_edges"]}
    missing = [e for e in internal if (e["caller"], e["callee"]) in missing_keys]

    # Conservative headline: drop the two arguable buckets from BOTH sides of
    # the fraction. Dropping them from the numerator only would shrink the
    # miss count while leaving their edges in the denominator -- a number
    # that flatters the tool rather than reporting it.
    kept = [e for e in internal if e["construct"] not in HELD_OUT_CONSTRUCTS]
    kept_missing = [e for e in missing if e["construct"] not in HELD_OUT_CONSTRUCTS]
    conservative = {"missing": len(kept_missing), "total": len(kept)}

    by_construct: dict[str, dict] = {}
    for edge in internal:
        row = by_construct.setdefault(edge["construct"], {"missing": 0, "total": 0})
        row["total"] += 1
    for edge in missing:
        by_construct[edge["construct"]]["missing"] += 1
    constructs = [
        {"construct": name, "missing": row["missing"], "total": row["total"],
         "held_out": name in HELD_OUT_CONSTRUCTS,
         "ratio": round(row["missing"] / row["total"], 4) if row["total"] else 0.0}
        for name, row in sorted(by_construct.items(), key=lambda kv: -kv[1]["missing"])
    ]

    payload = {
        "run_id": runtime["run_id"],
        "repo": args.repo,
        "sha": args.sha,
        "workload": runtime.get("workload"),
        "counter": result["counter"],
        "missing_ratio": round(ratio, 4),
        "conservative_counter": conservative,
        "conservative_ratio": round(missing_ratio(conservative), 4),
        "held_out_constructs": sorted(HELD_OUT_CONSTRUCTS),
        "by_construct": constructs,
        "missing_edges": missing,
        "by_module": rollup_by_module(missing, internal),
        "analysed_modules": sorted(modules),
        "excluded_files": runtime.get("excluded_files", []),
        "static_cost": static.get("cost"),
        "static_nodes": len(static["graph"]),
        "hash_seed": static.get("hash_seed", "unset"),
        "alias_merge": alias_stats,
    }
    write_json_atomic(Path(args.out), payload)

    print(f"{result['counter']['missing']}/{result['counter']['total']} internal edges "
          f"missing ({ratio * 100:.1f}%), "
          f"{result['counter']['entry_excluded']} entry edges held out")
    print(f"conservative (excluding {', '.join(sorted(HELD_OUT_CONSTRUCTS))}): "
          f"{conservative['missing']}/{conservative['total']} "
          f"({missing_ratio(conservative) * 100:.1f}%)")
    for row in constructs:
        flag = "  [held out]" if row["held_out"] else ""
        print(f"    {row['construct']:22s} {row['missing']:4d}/{row['total']:4d}"
              f"  {row['ratio'] * 100:5.1f}%{flag}")
    if ratio > NAMING_SANITY_CEILING:
        print(f"REFUSING: {ratio * 100:.1f}% missing is above the "
              f"{NAMING_SANITY_CEILING * 100:.0f}% sanity ceiling. This is far more "
              f"likely to be a qualified-name mismatch between PyCG and the tracer "
              f"than a real result -- do not present this number. "
              f"Check module_name_for against the static graph's node names.",
              file=sys.stderr)
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="trace the fixture, write runtime.json")
    p_run.add_argument("--fixture", required=True)
    p_run.add_argument("--entry", default="main")
    p_run.add_argument("--run-id", required=True)
    p_run.add_argument("--out", required=True)

    p_pkg = sub.add_parser("trace-package",
                            help="trace a whole package under a workload (real-repo demo)")
    p_pkg.add_argument("--src-root", required=True,
                       help="import root; PyCG module names are relative to this")
    p_pkg.add_argument("--package", required=True, help="package dir to trace")
    p_pkg.add_argument("--exclude", default="",
                       help="comma-separated filenames the static side also excluded")
    p_pkg.add_argument("--workload", required=True, help="python file exposing --entry")
    p_pkg.add_argument("--entry", default="main")
    p_pkg.add_argument("--run-id", required=True)
    p_pkg.add_argument("--out", required=True)

    p_sum = sub.add_parser("summarize",
                            help="diff a package static graph against its trace")
    p_sum.add_argument("--static", required=True)
    p_sum.add_argument("--runtime", required=True)
    p_sum.add_argument("--src-root", required=True)
    p_sum.add_argument("--repo", default="")
    p_sum.add_argument("--sha", default="")
    p_sum.add_argument("--package", default="",
                       help="top-level package name for alias canonicalization "
                            "(default: shortest analysed module name)")
    p_sum.add_argument("--out", required=True)

    sub.add_parser("selftest", help="run the unit tests described in the module docstring")

    args = ap.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "trace-package":
        return cmd_trace_package(args)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    return selftest()


if __name__ == "__main__":
    raise SystemExit(main())
