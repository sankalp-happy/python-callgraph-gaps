#!/usr/bin/env python3
"""Call-site inventory and `edge_type` classification, per `docs/metric_spec_h2a.md` §2.2.

Phase 1 §1.2. The rule §2.2 sets is the one that makes H2a non-circular:

    "Edge type is assigned by deterministic syntactic classification of the
     call site (from the caller's AST), *not* by whether the static tool
     happened to find it."

So this module never sees PyCG's output and never asks Pyright anything. It
reads the caller's AST and the repo's own binding structure, and nothing else.
Every call site lands in exactly one bucket, so the buckets sum to the total
and "static misses X% of edges of type T" is well defined.

Three things it produces, all consumed downstream:

  1. `edge_type` per call site        -> the per-type breakdown §4.1 requires
  2. AST-resolved target, where the  -> the fallback resolver for baseline 2
     source alone settles it            (`pyright_baseline.py`), and a free
                                        third data point: how much Pyright
                                        actually adds over plain name binding
  3. unresolved call sites           -> the `UnresolvedDispatch` census (§4.4)

### The one judgement call, stated plainly

§2.2 separates `method_static` ("obj's type is statically inferable") from
`method_dynamic` ("not statically inferable"). Inferability is not a syntactic
property, so *something* has to decide it -- and it cannot be Pyright, because
Pyright is baseline 2 and the classification would then be circular.

So inferability is decided by a fixed, conservative, local rule (`R-INFER`
below): `self`/`cls`, a name assigned from a constructor call, a name with a
class annotation, or an in-repo module. Nothing else counts.

**Direction of the bias, because it matters:** the rule is deliberately weak,
so genuinely easy receivers get labelled `method_dynamic`. That moves easy
edges INTO the bucket we predict static tools miss, which makes that bucket's
measured miss rate LOWER -- it dilutes H2a rather than inflating it. A rule
biased the other way would have been unpublishable.

Stdlib only.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

from nodes import (
    LOCALS,
    MODULE_SYMBOL,
    ScopeWalker,
    Node,
    RepoInventory,
    char_col,
    decorator_text,
    inventory_repo,
    strip_locals,
)

CALLSITE_VERSION = "1.0"
SPEC_VERSION = "1.0"

# §2.2, in the spec's order. `decorator_wrapper` is deliberately absent: it is
# a RUNTIME observation (§2.3 -- a wrapper is recognised by having received the
# wrapped function as an argument at decorator_apply time), so assigning it
# here from syntax alone would be a guess dressed as a classification.
EDGE_TYPES = (
    "direct",
    "method_static",
    "method_dynamic",
    "super_dispatch",
    "reflective",
    "dynamic_import",
    "eval_exec",
    "callback_dispatch",
    "decorator_apply",
    "subprocess_ipc",
)

EVAL_EXEC_NAMES = frozenset({"eval", "exec", "compile"})
REFLECTIVE_NAMES = frozenset({"getattr", "__getattribute__"})
REFLECTIVE_DOTTED = frozenset({"operator.attrgetter", "operator.methodcaller"})
DYNAMIC_IMPORT_NAMES = frozenset({"__import__"})
DYNAMIC_IMPORT_DOTTED = frozenset({
    "importlib.import_module", "importlib.__import__", "imp.load_module",
    "imp.load_source", "pkgutil.resolve_name", "pkg_resources.load_entry_point",
})
# §2.2 `subprocess_ipc`: "subprocess, multiprocessing, socket boundary".
IPC_ROOT_MODULES = frozenset({"subprocess", "multiprocessing", "socket", "asyncio.subprocess"})
IPC_OS_FUNCS = frozenset({
    "system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv",
    "spawnve", "spawnvp", "spawnvpe", "execl", "execle", "execlp", "execlpe",
    "execv", "execve", "execvp", "execvpe", "fork", "forkpty", "posix_spawn",
})


# --------------------------------------------------------------------------
# Bindings: what a name means in a scope. Only as much as classification needs.
# --------------------------------------------------------------------------

DEF = "def"                # a def/lambda in this repo            -> node key
CLASS = "class"            # a class in this repo                 -> node key
MODULE = "module"          # a module name                        -> dotted, in_repo
SYMBOL = "symbol"          # a name imported from a module        -> (dotted, attr)
INSTANCE = "instance"      # known to hold an instance of a class -> class node key
PARAM = "param"            # a parameter with no usable annotation
GETATTR = "getattr"        # holds the result of getattr(...)
IMPORTCALL = "importcall"   # holds the result of import_module(...)
VALUE = "value"            # bound, but to something we do not model
CONTAINER = "container"    # read out of a subscript/attribute -- registry-shaped


@dataclass(frozen=True)
class Binding:
    kind: str
    detail: str = ""
    in_repo: bool = False


@dataclass
class CallSite:
    owner: str                  # node key of the enclosing scope
    relative_path: str
    lineno: int
    col_offset: int
    end_lineno: int
    edge_type: str
    callee_expr: str            # source-shaped text of the callee, for eyeballing
    target_scope: str           # in_repo | external | unknown
    resolved_target: str | None = None   # node key, when the AST alone settles it
    receiver_kind: str | None = None
    construct: bool = False     # `C()` -- the runtime callee is C.__init__
    in_decorator: bool = False
    synthetic: bool = False     # decorator_apply sites, which have no Call node
    # Position of the callee IDENTIFIER, in characters, for `pyright_baseline`
    # to point a definition request at. None when the callee has no identifier
    # to point at (`handlers[k]()`, `f()()`) -- Pyright cannot answer those
    # either, and they are precisely the callback_dispatch class.
    callee_lineno: int | None = None
    callee_char: int | None = None
    # Per-file sequence number, assigned after the deterministic sort in
    # `analyse_repo`. It is what makes `site_id` injective, and it has to be:
    # a chained call `a.b().c()` gives the outer and inner Call nodes the SAME
    # (lineno, col_offset), because both expressions start at `a`. Keying on
    # position alone silently collapsed 151 of click's 2129 call sites into 1978
    # -- every one of them dropped from the request batch and from the
    # unresolved census, in the direction that makes the extractor look tidier
    # than it is.
    seq: int = 0

    @property
    def site_id(self) -> str:
        suffix = ":dec" if self.synthetic else ""
        return f"{self.relative_path}:{self.lineno}:{self.col_offset}{suffix}#{self.seq}"

    def to_json(self) -> dict:
        out = {
            "site_id": self.site_id,
            "owner": self.owner,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "edge_type": self.edge_type,
            "callee_expr": self.callee_expr,
            "target_scope": self.target_scope,
        }
        if self.resolved_target:
            out["resolved_target"] = self.resolved_target
        if self.receiver_kind:
            out["receiver_kind"] = self.receiver_kind
        if self.callee_lineno is not None:
            out["callee_lineno"] = self.callee_lineno
            out["callee_char"] = self.callee_char
        for flag in ("construct", "in_decorator", "synthetic"):
            if getattr(self, flag):
                out[flag] = True
        return out


def expr_text(expr: ast.expr) -> str:
    """Compact, stable text for a callee expression.

    `ast.unparse` would be prettier but it is not stable across interpreter
    versions, and this string appears in artifacts that get diffed.
    """
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{expr_text(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Call):
        return f"{expr_text(expr.func)}(...)"
    if isinstance(expr, ast.Subscript):
        return f"{expr_text(expr.value)}[...]"
    if isinstance(expr, ast.Constant):
        return repr(expr.value)[:24]
    if isinstance(expr, ast.Await):
        return expr_text(expr.value)
    return f"<{type(expr).__name__}>"


class IdentifierIndex:
    """Where every NAME token sits, so an attribute's identifier can be located.

    `ast` gives no position for the `attr` of an `Attribute` node -- only for
    the value it hangs off. Scanning forward through the raw text for the name
    breaks on the shapes real code actually uses:

        obj \\
            .method()                  # continuation
        obj.  # a comment here
            method()                   # comment between dot and name
        (obj
         .method())                    # parenthesised continuation
        "obj.method" in s              # the name inside a string literal

    `tokenize` gets all of them right for free, so the tokens are indexed once
    per module and the attribute's identifier is looked up rather than guessed.
    Falls back to an empty index if the file does not tokenize, which is
    recorded rather than silently treated as "no attribute call sites".
    """

    def __init__(self, source: str):
        self.ok = True
        # (row, col) of every NAME token that is immediately preceded by a dot,
        # keyed by name, sorted by position.
        self.after_dot: dict[str, list[tuple[int, int]]] = {}
        try:
            import io
            import tokenize as tk
            prev_was_dot = False
            for tok in tk.generate_tokens(io.StringIO(source).readline):
                if tok.type == tk.NAME and prev_was_dot:
                    self.after_dot.setdefault(tok.string, []).append(tok.start)
                if tok.type == tk.OP:
                    prev_was_dot = tok.string == "."
                elif tok.type not in (tk.NL, tk.NEWLINE, tk.COMMENT, tk.INDENT, tk.DEDENT):
                    prev_was_dot = False
        except (SyntaxError, IndentationError, ValueError, UnicodeDecodeError):
            self.ok = False
            self.after_dot = {}

    def attr_position(self, attr: str, after_row: int, after_col: int) -> tuple[int, int] | None:
        """First `.attr` identifier at or after (row, col), 1-based row."""
        for row, col in self.after_dot.get(attr, ()):
            if (row, col) >= (after_row, after_col):
                return (row, col)
        return None


def iter_scope_stmts(body: list[ast.stmt]):
    """Every statement in one scope, descending through compound statements but
    NOT into nested def/class/lambda bodies -- those are their own scopes and
    get their own binding frame.
    """
    stack = list(body)
    while stack:
        stmt = stack.pop(0)
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field_name in ("body", "orelse", "finalbody"):
            stack = list(getattr(stmt, field_name, []) or []) + stack
        for handler in getattr(stmt, "handlers", []) or []:
            stack = list(handler.body) + stack


# --------------------------------------------------------------------------
# Repo index: enough cross-module structure to resolve a name to a node
# --------------------------------------------------------------------------

class RepoIndex:
    """Module table, top-level symbol table, and class base list for one repo.

    Built once from a `RepoInventory` so that binding resolution can cross
    module boundaries -- `from .core import main; main()` is a `direct` edge and
    must resolve to `core.py::main`, not be written off as unknown.
    """

    def __init__(self, inv: RepoInventory):
        self.inv = inv
        self.nodes_by_key: dict[str, Node] = inv.by_key()
        self.module_by_name = inv.module_by_name()
        # (path, lineno, col) -> the node the inventory actually created there.
        # Owners MUST be resolved through this and never rebuilt from a qualname:
        # `nodes.py` renames a colliding symbol (`f#0`/`f#1` for a def redefined
        # under an `if`, `C.v.<setter>` for a property setter), so a
        # string-rebuilt owner key points at a node that does not exist and every
        # call inside that function silently disappears from S. Caught on click,
        # where 4 owners were orphaned this way.
        self.node_at: dict[tuple[str, int, int], Node] = {}
        for node in inv.nodes:
            self.node_at.setdefault(
                (node.relative_path, node.lineno, node.col_offset), node)
        # module dotted name -> {top-level symbol -> Node}
        self.top_level: dict[str, dict[str, Node]] = {}
        # class node key -> base expressions as text, in declaration order
        self.class_bases: dict[str, list[str]] = {}
        # class node key -> defining module dotted name
        self.class_module: dict[str, str] = {}
        for mod in inv.modules:
            table: dict[str, Node] = {}
            for node in mod.nodes:
                if node.qualified_symbol == MODULE_SYMBOL:
                    continue
                if "." not in node.qualified_symbol:
                    table[node.qualified_symbol] = node
                if node.kind == "class_body":
                    self.class_module[node.key] = mod.module_name
            self.top_level[mod.module_name] = table
        # Every class's bases, for every module, BEFORE any classification runs
        # -- a method lookup in module A must be able to follow a base class
        # declared in module B whichever module is analysed first.
        for mod in inv.modules:
            indexer = _ClassIndexer(mod.relative_path, self)
            for stmt in mod.tree.body:
                indexer.visit(stmt)

    def is_repo_module(self, dotted: str) -> bool:
        return dotted in self.module_by_name

    def module_node_key(self, dotted: str) -> str | None:
        mod = self.module_by_name.get(dotted)
        return f"{mod.relative_path}::{MODULE_SYMBOL}" if mod else None

    def lookup_member(self, class_key: str, attr: str, _depth: int = 0) -> Node | None:
        """`attr` on `class_key`, following in-repo bases.

        §1: "Resolve to the defining class in the MRO, not the runtime
        instance's class." Depth-first over declared bases is not a full C3
        linearisation, and where the two disagree the difference is recorded by
        Phase 3 against the runtime observation rather than guessed at here.
        """
        cls = self.nodes_by_key.get(class_key)
        if cls is None or _depth > 8:
            return None
        member = self.nodes_by_key.get(f"{cls.relative_path}::{cls.qualified_symbol}.{attr}")
        if member is not None:
            return member
        for base_key in self.resolved_bases(class_key):
            found = self.lookup_member(base_key, attr, _depth + 1)
            if found is not None:
                return found
        return None

    def resolved_bases(self, class_key: str) -> list[str]:
        out = []
        module = self.class_module.get(class_key)
        for base_text in self.class_bases.get(class_key, []):
            resolved = self.resolve_dotted_in_module(module, base_text)
            node = self.nodes_by_key.get(resolved) if resolved else None
            if node is not None and node.kind == "class_body":
                out.append(resolved)
        return out

    def resolve_dotted_in_module(self, module: str | None, dotted: str) -> str | None:
        """Best-effort: a bare name in the module's own top level, or
        `mod.Name` where `mod` is an in-repo module.
        """
        if not module:
            return None
        head, _, tail = dotted.partition(".")
        if not tail:
            node = self.top_level.get(module, {}).get(head)
            return node.key if node else None
        for candidate in (f"{module.rsplit('.', 1)[0]}.{head}", head):
            if self.is_repo_module(candidate):
                node = self.top_level.get(candidate, {}).get(tail)
                if node:
                    return node.key
        return None


def resolve_import_module(current_module: str, is_package: bool,
                          module: str | None, level: int) -> str:
    """`from . import x` / `from ..pkg import y` -> an absolute dotted name."""
    if not level:
        return module or ""
    parts = current_module.split(".")
    if not is_package:
        parts = parts[:-1]
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    base = ".".join(parts)
    return f"{base}.{module}" if module else base


# --------------------------------------------------------------------------
# The walker
# --------------------------------------------------------------------------

class _ClassIndexer(ScopeWalker):
    """Records every class's key, bases and defining module. Runs over all
    modules before classification so base-class lookup never depends on the
    order modules happen to be analysed in.
    """

    def __init__(self, relative_path: str, index: RepoIndex):
        super().__init__()
        self.relative_path = relative_path
        self.index = index

    def on_scope_enter(self, node: ast.AST, raw: str, kind: str) -> None:
        if kind != "class_body":
            return
        key = f"{self.relative_path}::{strip_locals(raw)}"
        self.index.class_bases[key] = [expr_text(b) for b in node.bases]
        self.index.class_module.setdefault(
            key, self.index.inv.path_to_module().get(self.relative_path, ""))


class _CallSiteWalker(ScopeWalker):
    def __init__(self, index: RepoIndex, module_name: str, relative_path: str,
                 is_package: bool, source: str = ""):
        super().__init__()
        self.index = index
        self.module_name = module_name
        self.relative_path = relative_path
        self.is_package = is_package
        self.lines = source.splitlines()
        self.idents = IdentifierIndex(source)
        self.sites: list[CallSite] = []
        self._frames: list[dict[str, Binding]] = []
        # Owner node keys, resolved through the inventory rather than rebuilt
        # from qualnames. Bottom of the stack is the module node.
        self._owners: list[str] = [f"{relative_path}::{MODULE_SYMBOL}"]
        self.unresolved_owners = 0

    def _owner_key_for(self, node: ast.AST, raw: str) -> str:
        found = self.index.node_at.get(
            (self.relative_path, node.lineno, node.col_offset))
        if found is not None:
            return found.key
        # Should not happen: both walkers see the same tree. Counted rather than
        # papered over, because the fallback can point at a node that is not
        # there and the resulting call sites would go missing.
        self.unresolved_owners += 1
        return f"{self.relative_path}::{strip_locals(raw)}"

    def current_owner(self) -> str:
        return self._owners[-1]

    def _line(self, lineno: int) -> str:
        return self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""

    def callee_position(self, func: ast.expr) -> tuple[int, int] | None:
        """Where the callee's identifier is, in (1-based row, char col)."""
        if isinstance(func, ast.Name):
            return (func.lineno, char_col(self._line(func.lineno), func.col_offset))
        if isinstance(func, ast.Attribute):
            value = func.value
            end_row = getattr(value, "end_lineno", None) or value.lineno
            end_col = getattr(value, "end_col_offset", None) or 0
            return self.idents.attr_position(
                func.attr, end_row, char_col(self._line(end_row), end_col))
        return None

    # -- frames -----------------------------------------------------------

    def push_frame(self, stmts: list[ast.stmt], scope_prefix: str,
                   args: ast.arguments | None = None,
                   in_class: bool = False, class_raw: str | None = None) -> None:
        """`scope_prefix` is what CPython prepends to a name defined in the
        scope being entered -- it CANNOT come from `child_prefix()` here,
        because `on_scope_enter` fires before the scope is pushed.
        """
        frame: dict[str, Binding] = {}
        if args is not None:
            all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            if args.vararg:
                all_args.append(args.vararg)
            if args.kwarg:
                all_args.append(args.kwarg)
            for i, arg in enumerate(all_args):
                frame[arg.arg] = self._binding_for_annotation(arg.annotation) or Binding(PARAM)
            # R-INFER: `self` / `cls` in a method resolve to the enclosing class.
            if in_class and class_raw and all_args:
                first = all_args[0].arg
                if first in ("self", "cls"):
                    key = f"{self.relative_path}::{strip_locals(class_raw)}"
                    if key in self.index.nodes_by_key:
                        frame[first] = Binding(INSTANCE, key, in_repo=True)
        self._frames.append(frame)
        self._collect(stmts, frame, scope_prefix)

    def pop_frame(self) -> None:
        self._frames.pop()

    def _binding_for_annotation(self, ann: ast.expr | None) -> Binding | None:
        """R-INFER: a class annotation makes a receiver inferable."""
        if ann is None:
            return None
        text = expr_text(ann) if not isinstance(ann, ast.Constant) else str(ann.value)
        key = self.index.resolve_dotted_in_module(self.module_name, text)
        if key and self.index.nodes_by_key[key].kind == "class_body":
            return Binding(INSTANCE, key, in_repo=True)
        return None

    def _collect(self, stmts: list[ast.stmt], frame: dict[str, Binding],
                 prefix: str) -> None:
        """Bindings introduced in this scope. Deliberately flow-insensitive:
        the last binding of a name wins, so a name rebound in a branch is
        modelled by one of its values. Recorded as a known limitation rather
        than solved -- flow-sensitive binding is a static analysis, and the
        static analyses are the things under measurement here.
        """
        for stmt in iter_scope_stmts(stmts):
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = f"{self.relative_path}::{strip_locals(prefix + stmt.name)}"
                frame[stmt.name] = Binding(DEF, key, in_repo=True)
            elif isinstance(stmt, ast.ClassDef):
                key = f"{self.relative_path}::{strip_locals(prefix + stmt.name)}"
                frame[stmt.name] = Binding(CLASS, key, in_repo=True)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    dotted = alias.name
                    bound = alias.asname or dotted.split(".")[0]
                    target = dotted if alias.asname else dotted.split(".")[0]
                    frame[bound] = Binding(MODULE, target,
                                           in_repo=self.index.is_repo_module(target))
            elif isinstance(stmt, ast.ImportFrom):
                dotted = resolve_import_module(self.module_name, self.is_package,
                                               stmt.module, stmt.level)
                for alias in stmt.names:
                    bound = alias.asname or alias.name
                    if alias.name == "*":
                        continue
                    submodule = f"{dotted}.{alias.name}" if dotted else alias.name
                    if self.index.is_repo_module(submodule):
                        frame[bound] = Binding(MODULE, submodule, in_repo=True)
                        continue
                    node = self.index.top_level.get(dotted, {}).get(alias.name)
                    if node is not None:
                        frame[bound] = Binding(
                            CLASS if node.kind == "class_body" else DEF,
                            node.key, in_repo=True)
                    else:
                        frame[bound] = Binding(SYMBOL, f"{dotted}.{alias.name}",
                                               in_repo=self.index.is_repo_module(dotted))
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                binding = (self._value_binding(stmt.value) if stmt.value is not None else None)
                frame[stmt.target.id] = (
                    binding if binding and binding.kind == INSTANCE
                    else self._binding_for_annotation(stmt.annotation)
                    or binding or Binding(VALUE))
            elif isinstance(stmt, (ast.Assign, ast.AugAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                binding = self._value_binding(getattr(stmt, "value", None))
                for target in targets:
                    if isinstance(target, ast.Name):
                        frame[target.id] = binding
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                if isinstance(stmt.target, ast.Name):
                    frame[stmt.target.id] = Binding(VALUE)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if isinstance(item.optional_vars, ast.Name):
                        frame[item.optional_vars.id] = self._value_binding(item.context_expr)

    def _value_binding(self, value: ast.expr | None) -> Binding:
        """What a name holds after `name = <value>`. Only the shapes that
        change a classification are modelled; everything else is VALUE.
        """
        if value is None:
            return Binding(VALUE)
        if isinstance(value, ast.Call):
            func = value.func
            dotted = expr_text(func)
            if isinstance(func, ast.Name) and func.id in REFLECTIVE_NAMES:
                return Binding(GETATTR)
            if dotted in REFLECTIVE_DOTTED:
                return Binding(GETATTR)
            if (isinstance(func, ast.Name) and func.id in DYNAMIC_IMPORT_NAMES) \
                    or dotted in DYNAMIC_IMPORT_DOTTED:
                return Binding(IMPORTCALL)
            resolved = self._resolve(func)
            # R-INFER: a name assigned from a constructor call is inferable.
            if resolved and resolved.kind == CLASS:
                return Binding(INSTANCE, resolved.detail, in_repo=True)
            return Binding(VALUE)
        if isinstance(value, ast.Name):
            return self._lookup(value.id) or Binding(VALUE)
        if isinstance(value, (ast.Subscript,)):
            return Binding(CONTAINER)
        if isinstance(value, ast.Attribute):
            resolved = self._resolve(value)
            return resolved or Binding(CONTAINER)
        return Binding(VALUE)

    # -- name resolution --------------------------------------------------

    def _lookup(self, name: str) -> Binding | None:
        for frame in reversed(self._frames):
            if name in frame:
                return frame[name]
        return None

    def _resolve(self, expr: ast.expr) -> Binding | None:
        """Resolve a callee expression to a binding, crossing modules and
        classes where the source allows it.
        """
        if isinstance(expr, ast.Name):
            return self._lookup(expr.id)
        if isinstance(expr, ast.Attribute):
            base = self._resolve(expr.value)
            if base is None:
                return None
            if base.kind == MODULE and base.in_repo:
                node = self.index.top_level.get(base.detail, {}).get(expr.attr)
                if node is not None:
                    return Binding(CLASS if node.kind == "class_body" else DEF,
                                   node.key, in_repo=True)
                submodule = f"{base.detail}.{expr.attr}"
                if self.index.is_repo_module(submodule):
                    return Binding(MODULE, submodule, in_repo=True)
                return None
            if base.kind == MODULE:
                return Binding(SYMBOL, f"{base.detail}.{expr.attr}", in_repo=False)
            if base.kind in (INSTANCE, CLASS):
                member = self.index.lookup_member(base.detail, expr.attr)
                if member is not None:
                    return Binding(DEF, member.key, in_repo=True)
                return None
            return None
        if isinstance(expr, ast.Call):
            resolved = self._resolve(expr.func)
            if resolved and resolved.kind == CLASS:
                return Binding(INSTANCE, resolved.detail, in_repo=True)
            return None
        return None

    # -- classification ---------------------------------------------------

    def classify(self, call: ast.Call) -> CallSite:
        func = call.func
        dotted = expr_text(func)
        owner = self.current_owner()

        pos = self.callee_position(func)

        def site(edge_type: str, *, target: str | None = None,
                 scope: str = "unknown", receiver: str | None = None,
                 construct: bool = False) -> CallSite:
            return CallSite(
                owner=owner,
                relative_path=self.relative_path,
                lineno=call.lineno,
                col_offset=call.col_offset,
                end_lineno=getattr(call, "end_lineno", None) or call.lineno,
                edge_type=edge_type,
                callee_expr=dotted,
                target_scope="in_repo" if target else scope,
                resolved_target=target,
                receiver_kind=receiver,
                construct=construct,
                in_decorator=bool(self._in_decorator),
                callee_lineno=pos[0] if pos else None,
                callee_char=pos[1] if pos else None,
            )

        # R1 super().m() -- §2.2 super_dispatch. Checked first because the
        # receiver is a Call and would otherwise fall through to R7.
        if isinstance(func, ast.Attribute):
            recv = func.value
            if isinstance(recv, ast.Call) and isinstance(recv.func, ast.Name) \
                    and recv.func.id == "super" and self._lookup("super") is None:
                enclosing = self.enclosing_classes()
                target = None
                if enclosing:
                    class_key = f"{self.relative_path}::{strip_locals(enclosing[-1])}"
                    for base_key in self.index.resolved_bases(class_key):
                        member = self.index.lookup_member(base_key, func.attr)
                        if member is not None:
                            target = member.key
                            break
                return site("super_dispatch", target=target, receiver="super")

        # R2 eval / exec / compile -- §2.2 always lands in a PhantomNode.
        if isinstance(func, ast.Name) and func.id in EVAL_EXEC_NAMES \
                and self._lookup(func.id) is None:
            return site("eval_exec", scope="unknown")

        # R3 dynamic import, either called directly or through a name that
        # holds the imported module.
        if (isinstance(func, ast.Name) and func.id in DYNAMIC_IMPORT_NAMES
                and self._lookup(func.id) is None) or dotted in DYNAMIC_IMPORT_DOTTED:
            return site("dynamic_import", scope="unknown")
        if isinstance(func, ast.Attribute):
            base = self._resolve_or_none(func.value)
            if base is not None and base.kind == IMPORTCALL:
                return site("dynamic_import", scope="unknown", receiver="import_result")
        if isinstance(func, ast.Name):
            bound = self._lookup(func.id)
            if bound is not None and bound.kind == IMPORTCALL:
                return site("dynamic_import", scope="unknown", receiver="import_result")

        # R4 reflective: getattr(o, n)(), a name holding a getattr result, or
        # an attribute reached through one. §2.2's core H2a target.
        if isinstance(func, ast.Call):
            inner = func.func
            inner_dotted = expr_text(inner)
            if (isinstance(inner, ast.Name) and inner.id in REFLECTIVE_NAMES
                    and self._lookup(inner.id) is None) or inner_dotted in REFLECTIVE_DOTTED:
                return site("reflective", scope="unknown", receiver="getattr_call")
        for probe in (func, getattr(func, "value", None)):
            if probe is None:
                continue
            bound = self._resolve_or_none(probe)
            if bound is not None and bound.kind == GETATTR:
                return site("reflective", scope="unknown", receiver="getattr_result")

        # R5 subprocess / multiprocessing / socket boundary. Out of universe by
        # §2.1, but counted so the external surface has a number.
        if isinstance(func, ast.Attribute):
            root = dotted.split(".")[0]
            bound_root = self._lookup(root)
            if bound_root is not None and bound_root.kind == MODULE:
                if bound_root.detail in IPC_ROOT_MODULES:
                    return site("subprocess_ipc", scope="external")
                if bound_root.detail == "os" and func.attr in IPC_OS_FUNCS:
                    return site("subprocess_ipc", scope="external")
        if isinstance(func, ast.Name):
            bound = self._lookup(func.id)
            if bound is not None and bound.kind == SYMBOL:
                mod = bound.detail.rsplit(".", 1)[0]
                if mod in IPC_ROOT_MODULES or (
                        mod == "os" and bound.detail.rsplit(".", 1)[1] in IPC_OS_FUNCS):
                    return site("subprocess_ipc", scope="external")

        # R6 registry / container / call-result dispatch -- the plugin and DI
        # mechanism §2.2 calls callback_dispatch.
        if isinstance(func, ast.Subscript):
            return site("callback_dispatch", scope="unknown", receiver="subscript")
        if isinstance(func, ast.Call):
            return site("callback_dispatch", scope="unknown", receiver="call_result")

        # R7 a bare name. Resolves to a def/class -> direct; a parameter or a
        # container read -> callback_dispatch; otherwise unknown.
        if isinstance(func, ast.Name):
            bound = self._lookup(func.id)
            if bound is None:
                # Not bound anywhere we can see: a builtin, a star-import, or a
                # global defined elsewhere. Treated as direct-but-external
                # rather than as a dynamic construct, because syntactically it
                # is the easiest call there is and calling it "dynamic" would
                # inflate the dynamic buckets.
                return site("direct", scope="external")
            if bound.kind == DEF:
                return site("direct", target=bound.detail)
            if bound.kind == CLASS:
                init = self.index.lookup_member(bound.detail, "__init__")
                return site("direct", target=init.key if init else None,
                            scope="in_repo", construct=True)
            if bound.kind == SYMBOL:
                return site("direct", scope="in_repo" if bound.in_repo else "external")
            if bound.kind == MODULE:
                return site("direct", scope="in_repo" if bound.in_repo else "external")
            if bound.kind in (PARAM, CONTAINER):
                return site("callback_dispatch", scope="unknown",
                            receiver="parameter" if bound.kind == PARAM else "container")
            if bound.kind == INSTANCE:
                call_member = self.index.lookup_member(bound.detail, "__call__")
                return site("callback_dispatch",
                            target=call_member.key if call_member else None,
                            scope="unknown", receiver="instance")
            return site("callback_dispatch", scope="unknown", receiver="value")

        # R8 attribute call. A module attribute is a plain def lookup and stays
        # `direct`; everything else is a method call, split by R-INFER.
        if isinstance(func, ast.Attribute):
            base = self._resolve_or_none(func.value)
            if base is not None and base.kind == MODULE:
                resolved = self._resolve_or_none(func)
                if resolved is not None and resolved.kind == DEF:
                    return site("direct", target=resolved.detail, receiver="module")
                if resolved is not None and resolved.kind == CLASS:
                    init = self.index.lookup_member(resolved.detail, "__init__")
                    return site("direct", target=init.key if init else None,
                                scope="in_repo", receiver="module", construct=True)
                return site("direct", scope="in_repo" if base.in_repo else "external",
                            receiver="module")
            if base is not None and base.kind in (INSTANCE, CLASS):
                member = self.index.lookup_member(base.detail, func.attr)
                if member is not None:
                    return site("method_static", target=member.key,
                                receiver="self" if expr_text(func.value) in ("self", "cls")
                                else "typed")
                # R-INFER said the receiver is inferable, but the attribute is
                # not on the class or any in-repo base. `self._cb()` shaped:
                # an instance attribute holding a callable.
                return site("callback_dispatch", scope="unknown", receiver="instance_attr")
            if base is not None and base.kind == SYMBOL:
                return site("method_static" if base.in_repo else "method_dynamic",
                            scope="in_repo" if base.in_repo else "external",
                            receiver="imported_symbol")
            # R-INFER did not fire: the receiver's type is not statically
            # inferable under the rule, so §2.2's method_dynamic.
            return site("method_dynamic", scope="unknown",
                        receiver="uninferable")

        return site("callback_dispatch", scope="unknown", receiver="other")

    def _resolve_or_none(self, expr: ast.expr | None) -> Binding | None:
        if expr is None:
            return None
        try:
            return self._resolve(expr)
        except RecursionError:
            return None

    # -- traversal --------------------------------------------------------

    def on_scope_enter(self, node: ast.AST, raw: str, kind: str) -> None:
        # §2.3: `@dec def f` is a real call at import time, made by the scope
        # the def lives in, and it has no ast.Call of its own when the
        # decorator is a bare name -- so it is synthesized. Done BEFORE the new
        # frame is pushed, because a decorator expression is evaluated in the
        # enclosing scope and must resolve against the enclosing bindings.
        for dec in getattr(node, "decorator_list", []):
            self.sites.append(self._decorator_site(self.current_owner(), dec))

        if kind == "class_body":
            self.push_frame(node.body, f"{raw}.")
        elif kind == "lambda":
            self.push_frame([], f"{raw}.{LOCALS}.", node.args)
        else:
            in_class = self.current_scope()[1] == "class_body"
            self.push_frame(node.body, f"{raw}.{LOCALS}.", node.args,
                            in_class=in_class,
                            class_raw=self.current_scope()[0] if in_class else None)
        self._owners.append(self._owner_key_for(node, raw))

    def on_scope_leave(self, node: ast.AST, raw: str, kind: str) -> None:
        self.pop_frame()
        self._owners.pop()

    def _decorator_site(self, owner: str, dec: ast.expr) -> CallSite:
        text = decorator_text(dec)
        expr = dec.func if isinstance(dec, ast.Call) else dec
        resolved = self._resolve_or_none(expr)
        target = resolved.detail if resolved and resolved.kind == DEF else None
        pos = self.callee_position(expr)
        return CallSite(
            owner=owner,
            relative_path=self.relative_path,
            lineno=dec.lineno,
            col_offset=dec.col_offset,
            end_lineno=getattr(dec, "end_lineno", None) or dec.lineno,
            edge_type="decorator_apply",
            callee_expr=text,
            target_scope="in_repo" if target else (
                "in_repo" if resolved and resolved.in_repo else "unknown"),
            resolved_target=target,
            synthetic=True,
            callee_lineno=pos[0] if pos else None,
            callee_char=pos[1] if pos else None,
        )

    def visit_Call(self, node: ast.Call) -> None:
        self.sites.append(self.classify(node))
        # Nested calls are call sites too: `f(g())` is two edges.
        self.visit(node.func)
        for arg in [*node.args, *[k.value for k in node.keywords]]:
            self.visit(arg)


def analyse_module(index: RepoIndex, mod) -> list[CallSite]:
    walker = _CallSiteWalker(
        index, mod.module_name, mod.relative_path,
        is_package=mod.relative_path.endswith("__init__.py"),
        source=mod.source,
    )
    walker.push_frame(mod.tree.body, "")
    for stmt in mod.tree.body:
        walker.visit(stmt)
    walker.pop_frame()
    return walker.sites


def analyse_repo(inv: RepoInventory) -> tuple[list[CallSite], RepoIndex]:
    index = RepoIndex(inv)
    sites: list[CallSite] = []
    for mod in inv.modules:
        sites.extend(analyse_module(index, mod))
    sites.sort(key=lambda s: (s.relative_path, s.lineno, s.col_offset, s.synthetic))
    per_file: dict[str, int] = {}
    for site in sites:
        site.seq = per_file.get(site.relative_path, 0)
        per_file[site.relative_path] = site.seq + 1
    return sites, index


def counts(sites: list[CallSite]) -> dict:
    by_type: dict[str, int] = {t: 0 for t in EDGE_TYPES}
    by_scope: dict[str, int] = {}
    resolved = 0
    for s in sites:
        by_type[s.edge_type] = by_type.get(s.edge_type, 0) + 1
        by_scope[s.target_scope] = by_scope.get(s.target_scope, 0) + 1
        if s.resolved_target:
            resolved += 1
    return {
        "call_sites": len(sites),
        "ast_resolved": resolved,
        "by_edge_type": by_type,
        "by_target_scope": dict(sorted(by_scope.items())),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Classify every call site in a package.")
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--package", required=True)
    ap.add_argument("--src-root", default=".")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--counts-only", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    inv = inventory_repo(repo, repo / args.package, repo / args.src_root,
                         {n for n in args.exclude.split(",") if n})
    sites, _ = analyse_repo(inv)
    payload = {
        "callsite_version": CALLSITE_VERSION,
        "spec_version": SPEC_VERSION,
        "counts": counts(sites),
    }
    if not args.counts_only:
        payload["call_sites"] = [s.to_json() for s in sites]
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
