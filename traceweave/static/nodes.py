#!/usr/bin/env python3
"""The static node set, exactly as `docs/metric_spec_h2a.md` §1 defines it.

Phase 1 §1.2. Both static baselines and (in Phase 2) the tracer must agree on
what a node *is*, or the H2a difference measures our naming and not the tools.
So the node set is produced once, here, and both baselines are mapped onto it
rather than each inventing its own vocabulary.

    node_id = (repo_url, sha, relative_path, qualified_symbol)

`repo_url` and `sha` are constant per extraction and live in the artifact
header; inside a repo a node is keyed `relative_path::qualified_symbol`.
Line numbers are carried but are NEVER part of identity (§1) -- they are a
disambiguation hint for Phase 3 mapping and the only thing that lets the
Pyright baseline turn a definition location back into a node.

Deliberate choices where §1 is silent, all repeated in
`docs/static_extraction_spec.md` §2 so they are reviewable rather than buried:

  class bodies    A class body is a real code object with its own runtime frame
                  (`co_qualname == "C"`), and it is where registration
                  decorators and metaclass work happen -- exactly the H2a
                  construct classes. It is inventoried as `kind=class_body` so
                  those import-time calls have an owner, but `callable=false`
                  so it stays OUT of the `fn_coverage` denominator (§4.3 counts
                  "static callable nodes", and a class body is not callable).
  module nodes    Same treatment: inventoried (§1 mandates the node), but
                  `callable=false`.
  <locals>        §1 says normalize `<locals>` away "but keep it injective".
                  Stripping alone is not injective: `def f(): def g()` and
                  `class f: def g()` both collapse to `f.g`. So the strip is
                  applied, collisions are detected per module, and every member
                  of a colliding group keeps its raw qualname instead. The
                  count of such groups is reported, never silently resolved.

Stdlib only, like every other script in this harness. Runs on the newest
interpreter available (3.12+) -- NOT inside the PyCG image, which is capped at
3.11 by MANIFEST §2.1 and therefore cannot parse the newest syntax.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SPEC_VERSION = "1.0"          # docs/metric_spec_h2a.md this conforms to
INVENTORY_VERSION = "1.0"

MODULE_SYMBOL = "<module>"
LOCALS = "<locals>"

# Kinds that own executable code and can therefore own a call site.
OWNER_KINDS = frozenset({"module", "class_body", "function", "method", "lambda"})
# Kinds that count toward fn_coverage's denominator (§4.3: "static callable
# nodes"). A module body and a class body are executed, not called.
CALLABLE_KINDS = frozenset({"function", "method", "lambda"})

# `@typing.overload` declares a signature; its body is `...` and CPython throws
# the object away when the real def rebinds the name. It is therefore NOT a
# callable code unit: no workload can ever activate it and no static tool should
# emit an edge into it. Left in the inventory (it is real source) but marked
# `overload_stub`, kept out of CALLABLE_KINDS, and named apart so it cannot
# collide with the implementation.
#
# This is not cosmetic. click has 3 overloaded functions with 6 stubs between
# them; without this, `Editor.edit` becomes `Editor.edit#2` and stops matching
# what PyCG and the runtime both call it -- a silent, permanent miss for every
# overloaded function in the corpus. The density scorer hit the same construct
# from the other side (README finding 2: `@t.overload` counted as a registry
# decorator), which is what made it worth checking for here.
OVERLOAD_DECORATORS = frozenset({
    "overload", "t.overload", "typing.overload", "typing_extensions.overload",
})


@dataclass
class Node:
    relative_path: str
    qualified_symbol: str
    kind: str
    lineno: int
    end_lineno: int
    col_offset: int
    raw_qualname: str
    is_async: bool = False
    is_property: bool = False
    decorators: list[str] = field(default_factory=list)
    # Set when this node's <locals> could not be stripped injectively.
    locals_collision: bool = False
    overload_stub: bool = False

    @property
    def key(self) -> str:
        return f"{self.relative_path}::{self.qualified_symbol}"

    @property
    def is_callable(self) -> bool:
        return self.kind in CALLABLE_KINDS and not self.overload_stub

    def to_json(self) -> dict:
        out = {
            "key": self.key,
            "relative_path": self.relative_path,
            "qualified_symbol": self.qualified_symbol,
            "kind": self.kind,
            "callable": self.is_callable,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "col_offset": self.col_offset,
        }
        if self.raw_qualname != self.qualified_symbol:
            out["raw_qualname"] = self.raw_qualname
        if self.is_async:
            out["async"] = True
        if self.is_property:
            out["property"] = True
        if self.decorators:
            out["decorators"] = self.decorators
        if self.locals_collision:
            out["locals_collision"] = True
        if self.overload_stub:
            out["overload_stub"] = True
        return out


def decorator_text(expr: ast.expr) -> str:
    """Dotted text of a decorator expression, or `<expr>` when it is not a
    plain name/attribute/call. Used for §2.3 wrapper transparency and for the
    property/staticmethod checks below -- so it has to be stable, not pretty.
    """
    if isinstance(expr, ast.Call):
        return decorator_text(expr.func)
    if isinstance(expr, ast.Attribute):
        return f"{decorator_text(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Name):
        return expr.id
    return "<expr>"


def strip_locals(raw: str) -> str:
    return ".".join(p for p in raw.split(".") if p != LOCALS)


def char_col(line: str, byte_col: int) -> int:
    """`ast` column -> character column.

    `ast.col_offset` is a UTF-8 BYTE offset; `tokenize` and every editor-facing
    protocol count characters. They agree on ASCII and diverge on any line with
    a non-ASCII character, which is exactly the kind of difference that shows up
    as a handful of unresolvable call sites in one repo and nowhere else.
    """
    if byte_col <= 0:
        return 0
    return len(line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))


class ScopeWalker(ast.NodeVisitor):
    """The scope traversal both the node inventory and `callsites.py` use.

    Shared on purpose, not for brevity: the node set and the call-site set must
    agree on every owner name, or a call site ends up attributed to a node that
    does not exist and the edge silently disappears from S. One walk, two sets
    of hooks. `tests/test_static.py` asserts every call-site owner resolves to
    an inventoried node, which is the guard that keeps them in lockstep.

    Pushes a scope for functions, lambdas and class bodies; pushes NOTHING for
    comprehensions or generator expressions. That is how §1's "normalize into
    the enclosing function" is implemented -- a call inside a comprehension is
    simply owned by the function around it, and a lambda inside one is
    ordinaled against that function's scope.
    """

    def __init__(self) -> None:
        # (raw_qualname, kind) for each enclosing scope.
        self._stack: list[tuple[str, str]] = []
        # Per-scope 0-based lambda counter, keyed by the scope's raw qualname.
        self._lambda_n: dict[str, int] = {}
        # >0 while visiting a decorator expression, so `callsites.py` can flag
        # calls that only happen at import time.
        self._in_decorator = 0

    # -- scope bookkeeping ------------------------------------------------

    def current_scope(self) -> tuple[str, str]:
        """(raw qualname, kind) of the scope being visited."""
        if not self._stack:
            return (MODULE_SYMBOL, "module")
        return self._stack[-1]

    def enclosing_classes(self) -> list[str]:
        return [raw for raw, kind in self._stack if kind == "class_body"]

    def child_prefix(self) -> str:
        """What CPython prepends to a name defined in the current scope.

        A function scope inserts `<locals>`; a class scope does not. This is
        the rule that makes our qualnames equal `co_qualname` at runtime, which
        is the whole point -- Phase 2 joins on it.
        """
        if not self._stack:
            return ""
        raw, kind = self._stack[-1]
        if kind in ("function", "method", "lambda"):
            return f"{raw}.{LOCALS}."
        return f"{raw}."

    # -- hooks (subclasses override what they care about) -----------------

    def on_scope_enter(self, node: ast.AST, raw: str, kind: str) -> None: ...
    def on_scope_leave(self, node: ast.AST, raw: str, kind: str) -> None: ...

    # -- visitors ---------------------------------------------------------

    def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        raw = self.child_prefix() + node.name
        kind = "method" if self.current_scope()[1] == "class_body" else "function"
        self.on_scope_enter(node, raw, kind)
        self._stack.append((raw, kind))
        for child in node.body:
            self.visit(child)
        self._stack.pop()
        self.on_scope_leave(node, raw, kind)
        # Decorator expressions, default arguments and annotations are
        # evaluated in the ENCLOSING scope, not in the function -- visit them
        # after popping, so any call inside them is owned correctly.
        self._in_decorator += 1
        for d in node.decorator_list:
            self.visit(d)
        self._in_decorator -= 1
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self.visit(default)

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        raw = self.child_prefix() + node.name
        self.on_scope_enter(node, raw, "class_body")
        self._stack.append((raw, "class_body"))
        for child in node.body:
            self.visit(child)
        self._stack.pop()
        self.on_scope_leave(node, raw, "class_body")
        self._in_decorator += 1
        for d in node.decorator_list:
            self.visit(d)
        self._in_decorator -= 1
        for b in [*node.bases, *[k.value for k in node.keywords]]:
            self.visit(b)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        scope_raw = self.current_scope()[0]
        n = self._lambda_n.get(scope_raw, 0)
        self._lambda_n[scope_raw] = n + 1
        # §1: `<enclosing.qualname>.<lambda#N>`, N 0-based in source order
        # within the immediately enclosing scope. CPython's own qualname is
        # `enclosing.<locals>.<lambda>` for every lambda in a scope, which is
        # not injective; the ordinal is what makes it one, without using a line
        # number as identity. Phase 2 recovers N from this inventory by
        # (path, firstlineno) -- which is why col_offset is recorded.
        raw = f"{self.child_prefix()}<lambda#{n}>"
        self.on_scope_enter(node, raw, "lambda")
        self._stack.append((raw, "lambda"))
        self.visit(node.body)
        self._stack.pop()
        self.on_scope_leave(node, raw, "lambda")
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self.visit(default)


class _Inventory(ScopeWalker):
    """Node-set hooks over `ScopeWalker`."""

    def __init__(self, relative_path: str, module_end: int):
        super().__init__()
        self.relative_path = relative_path
        self.nodes: list[Node] = []
        # Per-symbol 0-based counter for @overload stubs of the same name.
        self._overload_n: dict[str, int] = {}
        self.module_node = Node(
            relative_path=relative_path,
            qualified_symbol=MODULE_SYMBOL,
            kind="module",
            lineno=1,
            end_lineno=module_end,
            col_offset=0,
            raw_qualname=MODULE_SYMBOL,
        )
        self.nodes.append(self.module_node)

    def on_scope_enter(self, node: ast.AST, raw: str, kind: str) -> None:
        decorators = [decorator_text(d) for d in getattr(node, "decorator_list", [])]
        is_overload = any(d in OVERLOAD_DECORATORS for d in decorators)
        symbol = strip_locals(raw)
        if is_overload:
            n = self._overload_n.get(symbol, 0)
            self._overload_n[symbol] = n + 1
            symbol = f"{symbol}.<overload#{n}>"
        self.nodes.append(Node(
            relative_path=self.relative_path,
            qualified_symbol=symbol,
            kind=kind,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", None) or node.lineno,
            col_offset=node.col_offset,
            raw_qualname=raw,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            # §1: "the getter/setter function is the callee node". Recorded so
            # Phase 3 can tell a property activation from a syntactic call.
            is_property=any(
                d == "property" or d == "cached_property"
                or d.endswith((".setter", ".getter", ".deleter"))
                for d in decorators
            ),
            decorators=decorators,
            overload_stub=is_overload,
        ))


def _group_by_symbol(nodes: list[Node]) -> dict[str, list[Node]]:
    out: dict[str, list[Node]] = {}
    for n in nodes:
        out.setdefault(n.qualified_symbol, []).append(n)
    return out


# Accessor role read off the decorator, used only to break a tie that no other
# rule can break -- see _resolve_collisions.
def _accessor_role(node: Node) -> str | None:
    for d in node.decorators:
        if d.endswith(".setter"):
            return "setter"
        if d.endswith(".deleter"):
            return "deleter"
    return None


def _resolve_collisions(nodes: list[Node]) -> tuple[int, int]:
    """Make `qualified_symbol` injective within a module, in two passes.

    Pass 1 undoes the `<locals>` strip, which §1 permits only "keep[ing] it
    injective": `def f(): def g()` and `class f: def g()` both collapse to
    `f.g`, and the raw qualnames separate them.

    Pass 2 handles a case §1 does not cover and that raw qualnames CANNOT fix:
    a property setter has byte-identical `co_qualname` to its getter
    (`C.v` for both), and a conditionally redefined `def f` under an
    `if`/`else` has two definitions with one name. CPython itself only tells
    them apart by `co_firstlineno`. So the tie is broken by role for accessors
    (`C.v` / `C.v.<setter>` / `C.v.<deleter>`) and by source-order ordinal
    otherwise (`f#0`, `f#1`), and Phase 3 maps a runtime frame onto the right
    one using its line number -- which §1 explicitly sanctions as a
    "disambiguation hint".

    Returns (locals_collision_groups, redefinition_groups). Both are reported:
    a repo where they fire has names our scheme handles by falling back, and
    the reader should know how often that happened rather than trust that it
    never did.
    """
    locals_groups = 0
    for symbol, group in _group_by_symbol(nodes).items():
        if len(group) < 2:
            continue
        if len({n.raw_qualname for n in group}) == len(group):
            locals_groups += 1
            for n in group:
                n.qualified_symbol = n.raw_qualname
                n.locals_collision = True

    redef_groups = 0
    for symbol, group in _group_by_symbol(nodes).items():
        if len(group) < 2:
            continue
        redef_groups += 1
        group.sort(key=lambda n: (n.lineno, n.col_offset))
        roles = [_accessor_role(n) for n in group]
        # Roles only settle it if they are present and distinct.
        if all(r is not None for r in roles[1:]) and len(set(roles)) == len(roles):
            for n, role in zip(group, roles):
                if role:
                    n.qualified_symbol = f"{n.qualified_symbol}.<{role}>"
        else:
            for i, n in enumerate(group):
                n.qualified_symbol = f"{n.qualified_symbol}#{i}"
    return locals_groups, redef_groups


@dataclass
class ModuleInventory:
    relative_path: str
    module_name: str
    nodes: list[Node]
    tree: ast.Module
    source: str = ""
    locals_collisions: int = 0
    redefinitions: int = 0

    def by_key(self) -> dict[str, Node]:
        return {n.key: n for n in self.nodes}

    @property
    def lines(self) -> list[str]:
        return self.source.splitlines()


def module_name_for(path: Path, src_root: Path) -> str:
    """Dotted import name of `path` relative to `src_root`.

    `pkg/__init__.py` -> `pkg`, `pkg/mod.py` -> `pkg.mod`. This is also the
    name PyCG uses, which is what makes `pycg_baseline.py`'s mapping possible.

    A file outside `src_root` (a `tests/` tree analysed alongside a `src/`
    layout) is named relative to its own nearest ancestor instead of being
    dropped. Dropping it would shrink the node set, and a smaller node set
    flatters both static baselines -- exactly the direction of error this
    project cannot afford to make silently.
    """
    resolved, root = path.resolve(), src_root.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        rel = Path(resolved.name)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def inventory_module(path: Path, repo_root: Path, src_root: Path,
                     source: str | None = None) -> ModuleInventory:
    """Parse one module and return its nodes. Raises SyntaxError to the caller
    -- an unparseable file is a recorded outcome (`parse_failures`), never a
    silently empty module, because an empty module set would flatter the static
    baselines by shrinking their denominator.
    """
    text = source if source is not None else path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=str(path))
    rel = str(path.resolve().relative_to(repo_root.resolve()))
    end = max((getattr(n, "end_lineno", 0) or 0) for n in ast.walk(tree)) if tree.body else 1
    inv = _Inventory(rel, end)
    for child in tree.body:
        inv.visit(child)
    locals_groups, redef_groups = _resolve_collisions(inv.nodes)
    return ModuleInventory(
        relative_path=rel,
        module_name=module_name_for(path, src_root),
        nodes=inv.nodes,
        tree=tree,
        source=text,
        locals_collisions=locals_groups,
        redefinitions=redef_groups,
    )


@dataclass
class RepoInventory:
    repo_root: Path
    src_root: Path
    modules: list[ModuleInventory]
    parse_failures: list[dict]

    @property
    def nodes(self) -> list[Node]:
        return [n for m in self.modules for n in m.nodes]

    def by_key(self) -> dict[str, Node]:
        return {n.key: n for n in self.nodes}

    def module_by_name(self) -> dict[str, ModuleInventory]:
        return {m.module_name: m for m in self.modules}

    def path_to_module(self) -> dict[str, str]:
        return {m.relative_path: m.module_name for m in self.modules}

    def counts(self) -> dict:
        by_kind: dict[str, int] = {}
        for n in self.nodes:
            by_kind[n.kind] = by_kind.get(n.kind, 0) + 1
        return {
            "modules": len(self.modules),
            "nodes": len(self.nodes),
            "callable_nodes": sum(1 for n in self.nodes if n.is_callable),
            "by_kind": dict(sorted(by_kind.items())),
            "parse_failures": len(self.parse_failures),
            "locals_collision_groups": sum(m.locals_collisions for m in self.modules),
            "redefinition_groups": sum(m.redefinitions for m in self.modules),
            "overload_stubs": sum(1 for n in self.nodes if n.overload_stub),
        }


def discover_py_files(package_dir: Path, exclude_names: set[str] = frozenset(),
                      exclude_dirs: set[str] = frozenset()) -> list[Path]:
    """Every .py under `package_dir`, sorted, minus exclusions.

    A single .py file is accepted too, so a caller can point at one module
    without inventing a directory for it.

    Sorted because PyCG's entry-point order is one of the things that moves its
    output (see scripts/pycg_determinism.py); a stable order removes one source
    of run-to-run difference we would otherwise have to explain.
    """
    if package_dir.is_file():
        return [package_dir] if package_dir.suffix == ".py" else []
    out = []
    for p in sorted(package_dir.rglob("*.py")):
        if p.name in exclude_names:
            continue
        if exclude_dirs and any(part in exclude_dirs for part in p.parts):
            continue
        out.append(p)
    return out


DEFAULT_EXCLUDE_DIRS = frozenset({
    ".git", "__pycache__", ".tox", ".nox", ".venv", "venv", "build", "dist",
    ".eggs", "node_modules", ".mypy_cache", ".pytest_cache",
})


def inventory_repo(repo_root: Path, package_dirs: Path | list[Path], src_root: Path,
                   exclude_names: set[str] = frozenset(),
                   exclude_dirs: set[str] = DEFAULT_EXCLUDE_DIRS) -> RepoInventory:
    """Inventory one or more package dirs under a single import root.

    A list, because plenty of real repos ship several top-level packages and
    analysing them one at a time would resolve no cross-package call and make
    every tool involved look worse than it is (the same reason `run_static.py`
    has a package mode at all).
    """
    dirs = [package_dirs] if isinstance(package_dirs, Path) else list(package_dirs)
    modules, failures = [], []
    seen: set[Path] = set()
    paths = []
    for package_dir in dirs:
        for path in discover_py_files(package_dir, exclude_names, exclude_dirs):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    for path in sorted(paths):
        try:
            modules.append(inventory_module(path, repo_root, src_root))
        except SyntaxError as exc:
            failures.append({
                "relative_path": str(path.resolve().relative_to(repo_root.resolve())),
                "error": f"{type(exc).__name__}: {exc.msg}",
                "lineno": exc.lineno,
                "parser": f"cpython-{sys.version_info.major}.{sys.version_info.minor}-ast",
            })
        except (UnicodeDecodeError, ValueError) as exc:
            failures.append({
                "relative_path": str(path.resolve().relative_to(repo_root.resolve())),
                "error": f"{type(exc).__name__}: {exc}",
                "lineno": None,
                "parser": f"cpython-{sys.version_info.major}.{sys.version_info.minor}-ast",
            })
    return RepoInventory(repo_root, src_root, modules, failures)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Print the static node inventory for a package.")
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--package", required=True, help="dir inside --repo, e.g. src/click")
    ap.add_argument("--src-root", default=".", help="import root inside --repo, e.g. src")
    ap.add_argument("--exclude", default="", help="comma-separated basenames to skip")
    ap.add_argument("--counts-only", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    inv = inventory_repo(
        repo, repo / args.package, repo / args.src_root,
        {n for n in args.exclude.split(",") if n},
    )
    if args.counts_only:
        print(json.dumps(inv.counts(), indent=2))
    else:
        print(json.dumps({
            "inventory_version": INVENTORY_VERSION,
            "spec_version": SPEC_VERSION,
            "counts": inv.counts(),
            "parse_failures": inv.parse_failures,
            "nodes": [n.to_json() for n in inv.nodes],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
