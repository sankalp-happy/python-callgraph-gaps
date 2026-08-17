#!/usr/bin/env python3
"""Guards for the Phase 1 §1.2 static extraction layer. No docker, no network.

Run:  python3 tests/test_static.py          (also invoked by tests/run_checks.sh)

Three kinds of check, in descending order of how much a regression would cost:

  invariants     Node keys are injective; every call-site owner is a node; every
                 site_id is unique; the edge_type buckets sum to the total.
                 Each of these, when it broke during development, silently
                 DELETED edges or call sites rather than raising -- the site_id
                 collision alone lost 151 of click's 2129 sites -- so they are
                 asserted on real repos, not only on fixtures.
  taxonomy       `tests/fixtures/callsite_taxonomy.py` declares the expected
                 §2.2 classification of every call site in its own source, in
                 `# expect:` comments. The fixture is the specification's
                 statement; this only compares.
  mapping        PyCG's names map onto our node set against the committed
                 goldens, with the four outcomes summing to its node count; and
                 Pyright definition locations map to the right nodes.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "static"))

import callsites  # noqa: E402
import nodes  # noqa: E402
import pycg_baseline  # noqa: E402
from pyright_baseline import NodeLocator  # noqa: E402

FIX = HERE / "fixtures"
PASS, FAIL = 0, 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {msg}")


def check(cond: bool, msg: str, detail: str = "") -> None:
    ok(msg) if cond else bad(f"{msg}{(' -- ' + detail) if detail else ''}")


# --------------------------------------------------------------------------
# 1. Invariants
# --------------------------------------------------------------------------

def check_invariants(label: str, inv, sites) -> None:
    keys = [n.key for n in inv.nodes]
    check(len(keys) == len(set(keys)),
          f"[{label}] node keys are injective ({len(keys)} nodes)",
          f"{len(keys) - len(set(keys))} duplicates")

    node_keys = set(keys)
    orphans = sorted({s.owner for s in sites} - node_keys)
    check(not orphans,
          f"[{label}] every call-site owner is an inventoried node",
          f"{len(orphans)} orphaned owners, e.g. {orphans[:3]}")

    ids = [s.site_id for s in sites]
    check(len(ids) == len(set(ids)),
          f"[{label}] site_ids are injective ({len(ids)} sites)",
          f"{len(ids) - len(set(ids))} collisions")

    counts = callsites.counts(sites)
    total = sum(counts["by_edge_type"].values())
    check(total == len(sites),
          f"[{label}] edge_type buckets sum to the call-site count",
          f"{total} != {len(sites)}")

    unknown = sorted(set(counts["by_edge_type"]) - set(callsites.EDGE_TYPES))
    check(not unknown, f"[{label}] no edge_type outside §2.2's taxonomy", str(unknown))

    check(not any(s.edge_type == "decorator_wrapper" for s in sites),
          f"[{label}] decorator_wrapper is never assigned statically (§2.3)")


# --------------------------------------------------------------------------
# 2. Taxonomy, as the fixture declares it
# --------------------------------------------------------------------------

EXPECT_RE = re.compile(r"#\s*expect:\s*(.+?)\s*$")


def test_taxonomy() -> None:
    inv = nodes.inventory_repo(FIX, FIX / "callsite_taxonomy.py", FIX)
    sites, _ = callsites.analyse_repo(inv)
    mod = inv.modules[0]
    # Read the declarations from real COMMENT tokens, not from raw lines: the
    # fixture's own docstring explains the `# expect:` convention and a line scan
    # happily "declares" line 4 of the prose.
    declared: dict[int, list[str]] = {}
    for tok in tokenize.generate_tokens(io.StringIO(mod.source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        m = EXPECT_RE.search(tok.string)
        if m:
            declared[tok.start[0]] = sorted(t.strip() for t in m.group(1).split(","))

    got: dict[int, list[str]] = {}
    for site in sites:
        got.setdefault(site.lineno, []).append(site.edge_type)
    got = {k: sorted(v) for k, v in got.items()}

    mismatches = [(ln, exp, got.get(ln, [])) for ln, exp in sorted(declared.items())
                  if got.get(ln, []) != exp]
    check(not mismatches,
          f"taxonomy fixture: all {len(declared)} declared lines classify as §2.2 says",
          "; ".join(f"line {ln}: expected {exp}, got {g}" for ln, exp, g in mismatches[:6]))

    undeclared = sorted(set(got) - set(declared))
    check(not undeclared,
          "taxonomy fixture: every call site in it is declared",
          f"lines with calls but no `# expect:`: {undeclared}")

    check_invariants("taxonomy", inv, sites)
    return inv, sites


# --------------------------------------------------------------------------
# 3. Node normalization rules from metric_spec §1
# --------------------------------------------------------------------------

def test_node_rules(inv) -> None:
    by_symbol = {n.qualified_symbol: n for n in inv.nodes}

    # Lambdas: 0-based ordinal within the immediately enclosing scope, and a
    # lambda inside a comprehension is ordinaled against the FUNCTION, because
    # comprehensions are not scopes for our purposes (§1).
    lambdas = sorted(n.qualified_symbol for n in inv.nodes if n.kind == "lambda")
    check(lambdas == ["with_lambdas.<lambda#0>", "with_lambdas.<lambda#1>",
                      "with_lambdas.<lambda#2>"],
          "lambda ordinals are per-enclosing-scope and 0-based", str(lambdas))

    # Comprehensions are never their own node.
    check(not any("comp" in n.qualified_symbol and "<" in n.qualified_symbol
                  for n in inv.nodes if n.kind not in ("lambda", "module")),
          "comprehensions produce no node of their own (§1, PEP 709)")

    # @overload stubs: named apart, not callable, implementation keeps its name.
    stubs = [n for n in inv.nodes if n.overload_stub]
    check(len(stubs) == 2 and all(not n.is_callable for n in stubs),
          "@overload stubs are inventoried but not callable",
          f"{len(stubs)} stubs, callable={[n.is_callable for n in stubs]}")
    check("widened" in by_symbol and not by_symbol["widened"].overload_stub,
          "the @overload IMPLEMENTATION keeps the plain name")

    # Module and class bodies are nodes but not callables (fn_coverage, §4.3).
    check(all(not n.is_callable for n in inv.nodes
              if n.kind in ("module", "class_body")),
          "module and class bodies are out of the fn_coverage denominator")

    # Property getter/setter: identical co_qualname, separated by role.
    fp = nodes.inventory_module(FIX / "false_positives.py", FIX, FIX)
    symbols = {n.qualified_symbol for n in fp.nodes}
    check({"C.v", "C.v.<setter>"} <= symbols,
          "a property setter is separated from its getter", str(sorted(symbols)))


# --------------------------------------------------------------------------
# 4. Source-position machinery
# --------------------------------------------------------------------------

def test_positions(inv, sites) -> None:
    mod = inv.modules[0]
    lines = mod.source.splitlines()

    # tokenize-based attribute lookup survives a comment between dot and name.
    over_lines = [s for s in sites if s.callee_expr.endswith(".method")
                  and "comment between" in lines[s.lineno - 1]
                  or (s.callee_expr == "obj.method" and s.callee_lineno
                      and "method()" in lines[s.callee_lineno - 1]
                      and s.lineno != s.callee_lineno)]
    check(any(s.callee_lineno and s.callee_lineno != s.lineno for s in over_lines),
          "an attribute split across lines by a comment still finds its identifier",
          f"{[(s.lineno, s.callee_lineno) for s in over_lines]}")

    # Every attribute/name call site found an identifier to point at; only
    # subscript / call-result callees may lack one.
    missing = [s for s in sites if s.callee_lineno is None]
    check(all(s.receiver_kind in ("subscript", "call_result", "getattr_call")
              for s in missing),
          "only subscript, call-result and getattr-result callees lack a position",
          str([(s.lineno, s.callee_expr, s.receiver_kind) for s in missing]))

    # UTF-16 vs UTF-8 columns: `ast` counts bytes, LSP counts UTF-16 units.
    from lsp import utf16_column
    line = 'x = "héllo" ; obj.method()'
    byte_col = line.encode("utf-8").index(b"obj")
    char = nodes.char_col(line, byte_col)
    check(line[char:char + 3] == "obj",
          "char_col converts an ast byte column past a non-ASCII character")
    check(utf16_column(line, char) == char,
          "utf16_column agrees with char_col when there are no astral characters")
    astral = "e = '\U0001f600' ; obj.method()"
    a_char = astral.index("obj")
    check(utf16_column(astral, a_char) == a_char + 1,
          "utf16_column counts a surrogate pair as two code units",
          f"{utf16_column(astral, a_char)} vs {a_char + 1}")


# --------------------------------------------------------------------------
# 5. PyCG name mapping
# --------------------------------------------------------------------------

def test_pycg_mapping() -> None:
    # 5a. The committed golden for a nested function.
    golden = json.loads((FIX / "qualname_nested_static_golden.json").read_text())
    inv = nodes.inventory_repo(FIX, FIX / "qualname_nested.py", FIX)
    edges, diag = pycg_baseline.normalize(golden, inv)
    check(diag["name_outcomes_sum_matches"],
          "PyCG name outcomes sum to its node count (nested golden)")
    check(("qualname_nested.py::outer", "qualname_nested.py::outer.inner")
          in edges.in_universe,
          "PyCG's `mod.outer.inner` maps to our `outer.inner`",
          str(sorted(edges.in_universe)))

    # 5b. The committed golden for the plugin-registry fixture: PyCG sees
    # dispatch -> getattr and NOT dispatch -> handle_email. The mapping must
    # preserve that, or the demo's whole point evaporates.
    golden2 = json.loads((FIX / "fixture_static_golden.json").read_text())
    demo = nodes.inventory_repo(REPO / "demo", REPO / "demo" / "fixture.py",
                                REPO / "demo")
    edges2, diag2 = pycg_baseline.normalize(golden2, demo)
    pairs = {f"{a}->{b}" for a, b in edges2.in_universe}
    check("fixture.py::main->fixture.py::PluginRegistry.dispatch" in pairs,
          "PyCG's main -> dispatch survives normalization", str(sorted(pairs)))
    check(not any("handle_email" in p for p in pairs),
          "normalization does not invent the edge PyCG missed", str(sorted(pairs)))

    # 5c. Namespace duplicates: `types.convert_type` merges into
    # `click.types.convert_type` when exactly one package root resolves it.
    fake = {
        "qualname_nested.outer": ["qualname_nested.outer.inner"],
        # the same function seen through a shorter root, as PyCG emits under
        # --src-root src
        "outer": ["outer.inner"],
    }
    inv3 = nodes.inventory_repo(FIX, FIX / "qualname_nested.py", FIX)
    e3, d3 = pycg_baseline.normalize(fake, inv3)
    check(d3["reasons"].get("namespace_merged") == 2,
          "both halves of a shortened duplicate name are merged, with a count",
          json.dumps(d3["reasons"]))
    check(len(e3.in_universe) == 1,
          "the merged duplicate collapses onto one edge, not two",
          str(sorted(e3.in_universe)))

    # 5d. A synthesized attribute path maps to nothing and is COUNTED.
    e4, d4 = pycg_baseline.normalize(
        {"qualname_nested.outer": ["qualname_nested.outer.inner._stream.read"]}, inv3)
    check(d4["reasons"].get("synthesized_path") == 1,
          "a PyCG-invented attribute path is recorded as unmapped, not dropped",
          json.dumps(d4["reasons"]))


# --------------------------------------------------------------------------
# 6. Pyright definition -> node
# --------------------------------------------------------------------------

def test_locator(inv, sites) -> None:
    _, index = callsites.analyse_repo(inv)
    locator = NodeLocator(inv, index)
    mod = inv.modules[0]
    lines = mod.source.splitlines()

    def line_of(text: str) -> int:
        for i, line in enumerate(lines, start=1):
            if text in line:
                return i
        raise AssertionError(f"fixture line not found: {text}")

    key, reason = locator.locate(mod.relative_path, line_of("def plain():"))
    check(key == "callsite_taxonomy.py::plain" and reason == "ok",
          "a definition line maps to its function node", f"{key} {reason}")

    key, reason = locator.locate(mod.relative_path, line_of("class Child(Base):"))
    check(key == "callsite_taxonomy.py::Child.__init__" and reason == "class_to_init",
          "a class definition maps to its __init__ (the runtime callee)",
          f"{key} {reason}")

    key, reason = locator.locate(mod.relative_path, line_of("class Base:"))
    check(key is None and reason == "class_without_init",
          "a class with no in-repo __init__ is out of universe, not a miss",
          f"{key} {reason}")

    key, reason = locator.locate(mod.relative_path, line_of("def widened(x: int)"))
    check(key == "callsite_taxonomy.py::widened" and reason == "overload_redirected",
          "a definition landing on an @overload stub redirects to the implementation",
          f"{key} {reason}")

    key, reason = locator.locate(mod.relative_path, line_of("HANDLERS = {}"))
    check(key is None and reason == "no_node_at_definition_line",
          "a definition on a plain assignment resolves to nothing (no invented edge)",
          f"{key} {reason}")


# --------------------------------------------------------------------------
# 7. The same invariants on a real repository
# --------------------------------------------------------------------------

def test_layout_detection() -> None:
    """A wrong import root produces a graph whose names cannot be mapped and a
    spuriously enormous miss rate -- and it fails SILENTLY, as a repo that
    "has no Python package". ansible and sqlalchemy both ship theirs in `lib/`
    and were both skipped until the reference set was run end to end.
    """
    sys.path.insert(0, str(REPO / "static"))
    from extract import detect_layout
    refrepos = Path.home() / "traceweave-data" / "refrepos"
    if not refrepos.is_dir():
        print("  SKIP  no reference clones at ~/traceweave-data/refrepos")
        return
    expected = {
        "ansible": ("lib", ["lib/ansible"]),
        "sqlalchemy": ("lib", ["lib/sqlalchemy"]),
        "click": ("src", ["src/click"]),
        "django": ("flat", ["django"]),
        "records": ("single-module", ["."]),
    }
    for name, (layout, packages) in expected.items():
        repo = refrepos / name
        if not repo.is_dir():
            continue
        got = detect_layout(repo)
        check(got["layout"] == layout and got["packages"] == packages,
              f"layout: {name} -> {layout} {packages}",
              f"got {got['layout']} {got['packages']}")

    celery = refrepos / "celery"
    if celery.is_dir():
        got = detect_layout(celery)
        check("t" not in got["packages"],
              "layout: celery's `t` test package is not treated as library code",
              str(got["packages"]))


def test_real_repo() -> None:
    click = Path.home() / "traceweave-data" / "refrepos" / "click"
    if not (click / "src" / "click").is_dir():
        print("  SKIP  no click clone at ~/traceweave-data/refrepos/click")
        return
    inv = nodes.inventory_repo(click, click / "src" / "click", click / "src")
    sites, _ = callsites.analyse_repo(inv)
    check_invariants("click", inv, sites)
    check(inv.counts()["parse_failures"] == 0,
          "click parses cleanly with the host ast",
          json.dumps(inv.parse_failures[:2]))
    # The control group, in the demo's sense: if plain `foo()` calls were not the
    # largest bucket, the classifier -- not the repo -- would be wrong.
    by_type = callsites.counts(sites)["by_edge_type"]
    check(by_type["direct"] == max(by_type.values()),
          "in click, `direct` is the largest bucket (classifier sanity floor)",
          json.dumps(by_type))


def main() -> int:
    print("=== static extraction: taxonomy ===")
    inv, sites = test_taxonomy()
    print("=== static extraction: node rules (metric_spec §1) ===")
    test_node_rules(inv)
    print("=== static extraction: source positions ===")
    test_positions(inv, sites)
    print("=== static extraction: PyCG name mapping ===")
    test_pycg_mapping()
    print("=== static extraction: Pyright definition mapping ===")
    test_locator(inv, sites)
    print("=== static extraction: layout detection ===")
    test_layout_detection()
    print("=== static extraction: invariants on a real repo ===")
    test_real_repo()
    print(f"\n  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
