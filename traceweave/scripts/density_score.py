#!/usr/bin/env python3
"""Score a Python repository for dynamic-feature density and assign a stratum.

This implements amendment 3 of SOP v1.1: the candidate list must be stratified
LOW/MED/HIGH *before* triage, so that stopping early still leaves balanced strata.

Design notes that matter for the paper:

* AST-based, never grep. ``getattr`` inside a docstring or a comment is not a
  dynamic call site, and a grep-based scorer would bin repos on their prose.

* ``getattr(obj, "literal")`` is *statically resolvable* and is therefore weighted
  far lower than ``getattr(obj, name)``. Conflating them is the most common way to
  overstate dynamic density.

* Source and test code are scored **separately**, and the stratum is assigned from
  source only. Test suites use ``getattr``/``monkeypatch``/``mock`` heavily for
  reasons that have nothing to do with the repo's own architecture; scoring them
  together makes every pytest-using project look HIGH.

* stdlib only, so this runs inside a bare ``python:3.12-slim`` with no pip install.
  Run it containerised (see ``score_repo.sh``) rather than on the host: the host is
  3.10 and cannot parse 3.11+ syntax, which would silently undercount.

Usage:
    python3 density_score.py /path/to/repo --repo-url https://github.com/o/n
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

SPEC_VERSION = "1.0"

# Directories that are not the project's own code.
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", "env",
    "node_modules", "site-packages", "dist-packages", "__pycache__",
    "vendor", "vendored", "third_party", "thirdparty", "_vendor",
    "build", "dist", ".eggs", ".mypy_cache", ".pytest_cache",
}

# A file is "test code" if any path part or the filename matches.
TEST_DIR_NAMES = {"test", "tests", "testing", "test_suite", "spec", "specs"}


def is_test_file(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts[:-1]}
    if parts & TEST_DIR_NAMES:
        return True
    name = rel.name.lower()
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


# --- feature weights -------------------------------------------------------
# Provisional. Calibrated ONCE during Phase 0 validation against the reference
# repo set, then frozen alongside docs/metric_spec_h2a.md. See §5 there.
WEIGHTS: dict[str, float] = {
    "getattr_dynamic": 2.0,     # getattr(o, name)      -> real blind spot
    "getattr_literal": 0.3,     # getattr(o, "field")   -> statically resolvable
    "setattr_dynamic": 2.0,
    "setattr_literal": 0.3,
    "dynamic_import": 3.0,      # importlib.import_module / __import__
    "eval_exec": 3.0,           # eval / exec / compile
    "dynamic_class": 2.0,       # 3-arg type(), metaclass=
    "attr_protocol": 2.5,       # __getattr__/__getattribute__/__setattr__ defs
    "registry_decorator": 1.0,  # @app.route(...), @registry.register
    "subscript_call": 1.5,      # handlers[key]()
    "namespace_access": 1.0,    # globals()/locals()/vars()
    "subclass_walk": 2.0,       # __subclasses__()
    "dispatch": 1.5,            # singledispatch, abc register
    "sys_modules": 1.0,         # sys.modules *mutation* only
    "entry_points": 3.0,        # plugin discovery via entry points
}

# Attribute-style decorators that are NOT registries. Without this denylist,
# `@t.overload` and `@x.setter` dominate the signal in any typed codebase -- click
# scored 16.4 registry-decorators/KLOC on nothing but typing and properties.
NON_REGISTRY_DECORATORS = {
    "setter", "getter", "deleter",                       # property protocol
    "overload", "final", "runtime_checkable",            # typing
    "no_type_check", "type_check_only", "deprecated",
    "abstractmethod", "abstractproperty",                # abc
    "wraps", "cached_property", "lru_cache", "cache",    # functools
    "total_ordering", "singledispatchmethod",
    "contextmanager", "asynccontextmanager",             # contextlib
    "dataclass", "staticmethod", "classmethod", "property",
}

# Builtins whose dynamic meaning only holds when called unqualified. `re.compile`
# is not `compile`; `obj.getattr` is not `getattr`. Matching on the trailing
# dotted component conflated these and was the largest single false positive.
BUILTIN_FEATURES = {
    "getattr": "getattr", "hasattr": "getattr", "delattr": "getattr",
    "setattr": "setattr",
    "eval": "eval_exec", "exec": "eval_exec", "compile": "eval_exec",
    "globals": "namespace_access", "locals": "namespace_access", "vars": "namespace_access",
    "__import__": "dynamic_import",
}

# Framework presence is a flat bonus, not per-KLOC: importing pluggy at all says
# something architectural about the repo regardless of its size.
#
# Deliberately EXCLUDED from this list: pytest and click. Both are near-ubiquitous
# (pytest in any tested repo, click in any CLI) and would push almost every
# candidate up a bin without discriminating architecture. pytest's actual plugin
# machinery is `pluggy`, which is listed, so the real signal is still captured.
FRAMEWORK_BONUS = 1.5
#
# Also excluded: importlib.metadata / importlib_metadata / pkg_resources. Importing
# them is near-universal (package version lookup) and says nothing architectural.
# Genuine plugin discovery is caught precisely by the `entry_points` call feature.
FRAMEWORK_MODULES = {
    "flask", "django", "celery", "pluggy", "stevedore", "injector",
    "dependency_injector", "zope", "pyramid", "twisted",
    "scrapy", "airflow", "luigi",
}

# Repos smaller than this are not research subjects and are excluded from the
# corpus with a recorded reason (never silently dropped).
MIN_SLOC = 500

# The per-KLOC denominator is FLOORED at this value. Without a floor, a 29-SLOC
# file with 20 weighted hits scores ~690 -- per-KLOC normalisation amplifies
# rather than normalises below 1 KLOC, which would badly misbin small repos.
# The floor biases small repos conservatively toward LOW; that is intended.
MIN_DENOM_SLOC = 1000

# Bin thresholds (score in weighted-hits per KLOC of source).
#
# CALIBRATED AND FROZEN 2026-07-27 against the 14-repo reference set; see
# docs/density_scorer_spec.md for the observed distribution. Chosen at the two
# natural gaps in that distribution (2.10 -> 7.48 and 9.03 -> 10.47).
#
# NOTE: the continuous `density_score` is the primary covariate for analysis --
# miss-rate is regressed on the score, not on the 3 bins. The bins exist to
# balance corpus *sampling* and to give readable table strata. Do not treat a bin
# boundary as a claim about a repo.
THRESHOLD_LOW_MED = 4.0
THRESHOLD_MED_HIGH = 10.0


@dataclass
class Counts:
    features: dict[str, int] = field(default_factory=dict)
    frameworks: set[str] = field(default_factory=set)
    sloc: int = 0
    files: int = 0
    parse_failures: int = 0
    parse_failure_files: list[str] = field(default_factory=list)

    def bump(self, key: str, n: int = 1) -> None:
        self.features[key] = self.features.get(key, 0) + n

    def weighted(self) -> float:
        return sum(WEIGHTS.get(k, 0.0) * v for k, v in self.features.items())


class FeatureVisitor(ast.NodeVisitor):
    """Counts dynamic-feature call sites in one module."""

    def __init__(self, counts: Counts) -> None:
        self.c = counts

    # -- helpers
    @staticmethod
    def _callee_name(node: ast.expr) -> str | None:
        """Dotted name of a call target, e.g. 'importlib.import_module'."""
        parts: list[str] = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        if isinstance(cur, ast.Attribute):  # unreachable, defensive
            return None
        return ".".join(reversed(parts)) if parts else None

    @staticmethod
    def _is_literal_str(node: ast.expr | None) -> bool:
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    # -- visitors
    def visit_Call(self, node: ast.Call) -> None:
        name = self._callee_name(node.func)
        short = name.rsplit(".", 1)[-1] if name else None

        # Builtin-derived features require an UNQUALIFIED call (or explicit
        # `builtins.x`). This is what keeps `re.compile` out of `eval_exec`.
        bare = node.func.id if isinstance(node.func, ast.Name) else None
        if bare is None and name and name.startswith("builtins."):
            bare = name.split(".", 1)[1]

        if bare in BUILTIN_FEATURES:
            kind = BUILTIN_FEATURES[bare]
            if kind in {"getattr", "setattr"}:
                second = node.args[1] if len(node.args) > 1 else None
                suffix = "_literal" if self._is_literal_str(second) else "_dynamic"
                self.c.bump(kind + suffix)
            else:
                self.c.bump(kind)
        elif bare == "type" and len(node.args) == 3:
            self.c.bump("dynamic_class")
        elif name in {"importlib.import_module", "importlib.util.spec_from_file_location"}:
            self.c.bump("dynamic_import")
        elif short in {"iter_entry_points", "load_entry_point", "entry_points"}:
            self.c.bump("entry_points")
        elif short == "__subclasses__":
            self.c.bump("subclass_walk")
        elif short in {"singledispatch", "register"} or (short and short.endswith("_register")):
            self.c.bump("dispatch")

        # sys.modules.pop(...) etc -- mutation via method rather than assignment.
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"pop", "setdefault", "update", "clear", "popitem"}
            and self._is_sys_modules(node.func.value)
        ):
            self.c.bump("sys_modules")

        # handlers[key]() / self._table[k]() -> registry dispatch
        if isinstance(node.func, ast.Subscript):
            self.c.bump("subscript_call")

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for kw in node.keywords:
            if kw.arg == "metaclass":
                self.c.bump("dynamic_class")
        self._count_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in {"__getattr__", "__getattribute__", "__setattr__", "__delattr__"}:
            self.c.bump("attr_protocol")
        self._count_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def _count_decorators(self, decorators: list[ast.expr]) -> None:
        """An attribute-style decorator (@app.route, @reg.register) implies a registry.

        A bare @staticmethod / @property does not, so plain Name decorators are
        not counted -- and neither are the many attribute-style decorators that are
        protocol or typing machinery rather than registration (NON_REGISTRY_DECORATORS).
        """
        for d in decorators:
            target = d.func if isinstance(d, ast.Call) else d
            if isinstance(target, ast.Attribute) and target.attr not in NON_REGISTRY_DECORATORS:
                self.c.bump("registry_decorator")

    def _is_sys_modules(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        # Only sys.modules *mutation* is a dynamic-feature signal; a bare read
        # (e.g. a membership test) is ordinary and was over-counted before.
        for tgt in node.targets:
            if isinstance(tgt, ast.Subscript) and self._is_sys_modules(tgt.value):
                self.c.bump("sys_modules")
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for tgt in node.targets:
            if isinstance(tgt, ast.Subscript) and self._is_sys_modules(tgt.value):
                self.c.bump("sys_modules")
        self.generic_visit(node)

    def _record_framework(self, module: str | None) -> None:
        """Record only an EXACT match, never the top-level package of a dotted match.

        Previously a dotted hit on `importlib.metadata` recorded the framework as
        `importlib`, so nearly every repo (version lookup is universal) collected a
        spurious framework bonus.
        """
        if not module:
            return
        if module in FRAMEWORK_MODULES:
            self.c.frameworks.add(module)
            return
        top = module.split(".")[0]
        if top in FRAMEWORK_MODULES:
            self.c.frameworks.add(top)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record_framework(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._record_framework(node.module)
        self.generic_visit(node)


def count_sloc(text: str) -> int:
    """Non-blank, non-comment-only physical lines."""
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            n += 1
    return n


def scan(root: Path) -> tuple[Counts, Counts]:
    src, tst = Counts(), Counts()
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        bucket = tst if is_test_file(rel) else src
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            bucket.parse_failures += 1
            bucket.parse_failure_files.append(str(rel))
            continue
        bucket.files += 1
        bucket.sloc += count_sloc(text)
        try:
            tree = ast.parse(text, filename=str(rel))
        except (SyntaxError, ValueError, RecursionError):
            bucket.parse_failures += 1
            if len(bucket.parse_failure_files) < 50:
                bucket.parse_failure_files.append(str(rel))
            continue
        FeatureVisitor(bucket).visit(tree)
    return src, tst


def score(c: Counts) -> float:
    kloc = max(c.sloc, MIN_DENOM_SLOC) / 1000.0
    return round(c.weighted() / kloc + FRAMEWORK_BONUS * len(c.frameworks), 3)


def stratum(s: float, sloc: int) -> str:
    if sloc < MIN_SLOC:
        return "TOO_SMALL"
    if s < THRESHOLD_LOW_MED:
        return "LOW"
    if s < THRESHOLD_MED_HIGH:
        return "MED"
    return "HIGH"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo_path", type=Path)
    ap.add_argument("--repo-url", default="")
    ap.add_argument("--sha", default="")
    args = ap.parse_args()

    root = args.repo_path.resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 2

    src, tst = scan(root)
    src_score = score(src)

    out = {
        "spec_version": SPEC_VERSION,
        "repo_url": args.repo_url,
        "sha": args.sha,
        "repo_path": str(root),
        "python_used_to_parse": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        # Stratum is assigned from SOURCE only; see module docstring.
        "density_score": src_score,
        "stratum": stratum(src_score, src.sloc),
        "source": {**asdict(src), "frameworks": sorted(src.frameworks), "score": src_score},
        "tests": {**asdict(tst), "frameworks": sorted(tst.frameworks), "score": score(tst)},
        "thresholds": {"low_med": THRESHOLD_LOW_MED, "med_high": THRESHOLD_MED_HIGH},
    }
    print(json.dumps(out, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
