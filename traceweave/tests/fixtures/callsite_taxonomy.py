"""Test-only fixture: one call site per `edge_type` in metric_spec_h2a.md §2.2.

Each line that contains a call declares what `callsites.py` must classify it as,
in a trailing `# expect:` comment listing EVERY edge_type on that line. The test
(`tests/test_static.py`) reads those comments and compares -- the same posture as
`demo/constructs/`, where each fixture states its own prediction and the script
fails if a prediction is wrong.

The declarations are the specification's, not the implementation's. If a rule
here looks wrong, argue with §2.2 first.
"""
import importlib
import os
import subprocess
from typing import overload

HANDLERS = {}


def plain():
    return 1


class Base:
    def method(self):
        return 2

    def overridden(self):
        return 3


class Child(Base):
    def __init__(self, cb):
        self._cb = cb
        self.helper = Base()                             # expect: direct

    def overridden(self):
        # `super()` is itself a call, so this line holds two sites.
        return super().overridden()                      # expect: super_dispatch, direct

    def calls(self, untyped, typed: Base):
        a = plain()                                      # expect: direct
        b = self.method()                                # expect: method_static
        c = typed.method()                               # expect: method_static
        d = untyped.method()                             # expect: method_dynamic
        e = self._cb()                                   # expect: callback_dispatch
        f = HANDLERS["k"]()                              # expect: callback_dispatch
        g = getattr(self, "method")()                    # expect: reflective, direct
        h = importlib.import_module("json")              # expect: dynamic_import
        i = eval("1 + 1")                                # expect: eval_exec
        j = subprocess.run(["true"])                     # expect: subprocess_ipc
        k = os.system("true")                            # expect: subprocess_ipc
        m = Base()                                       # expect: direct
        n = local_factory()()                            # expect: callback_dispatch, direct
        return a, b, c, d, e, f, g, h, i, j, k, m, n


def local_factory():
    return plain


def registry(fn):
    return fn


@registry                                                # expect: decorator_apply
def decorated():
    return 4


@registry                                                # expect: decorator_apply
@registry                                                # expect: decorator_apply
def twice_decorated():
    return 5


def with_lambdas():
    first = lambda: plain()                              # expect: direct
    second = lambda: 2
    inside = [(lambda: plain()) for _ in range(1)]        # expect: direct, direct
    return first, second, inside


def comprehension_owner():
    # §1: comprehensions normalize into the enclosing function, so this call is
    # owned by comprehension_owner and NOT by a comprehension node.
    return [plain() for _ in range(3)]                    # expect: direct, direct


@overload                                                # expect: decorator_apply
def widened(x: int) -> int: ...
@overload                                                # expect: decorator_apply
def widened(x: str) -> str: ...
def widened(x):
    return x


def dotted_attribute_over_lines(obj):
    # The Call node starts on the `return (obj` line, so the declaration lives
    # there; the callee IDENTIFIER is two lines down, past a comment, which is
    # what the tokenize-based lookup in IdentifierIndex exists for.
    return (obj                                           # expect: method_dynamic
            .  # a comment between the dot and the name
            method())


def non_ascii_column(obj):
    label = "héllo wörld ünicode"                          # noqa: F841
    return obj.method()                                    # expect: method_dynamic
