"""The DyPyBench workload, in the shape `tracer.py trace-package` expects.

The pivot plan replaces ins2's hand-captured workloads with each project's own
test suite. That makes the workload one line of pytest, but two details are
load-bearing:

  in-process   `pytest.main()`, not a subprocess. `sys.setprofile` only sees
               frames in this interpreter, so a subprocess would trace nothing.
  -p no:cacheprovider
               pytest writes .pytest_cache into the checkout. Harmless here, but
               it makes the traced tree differ from the tree the static side
               read, and the two sides must be byte-identical.

Everything pytest itself runs is filtered out by `capture_package_edges`, which
only records frames whose file is in the module map. The suite's own test
functions are therefore invisible; only calls into the library are recorded.

TW_PYTEST_ARGS carries the test path from the project list (field 3 or 4 of
github-url.txt). Passed by environment rather than argv because trace-package
owns argv.
"""
from __future__ import annotations

import os
import shlex

import pytest

# Exit code 1 means tests ran and some failed, which is a perfectly good
# workload -- MANIFEST §4 amendment 2 already settled that H2a needs repos that
# run, not repos that pass. Only 2+ (collection error, internal error, usage
# error) means the trace is not measuring the suite.
FATAL_FROM = 2


def entry() -> None:
    args = shlex.split(os.environ.get("TW_PYTEST_ARGS", ""))
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *args])
    if int(rc) >= FATAL_FROM:
        raise SystemExit(f"pytest exited {rc}: the suite did not run, so this "
                         f"trace is not a workload")


def demo() -> None:
    """Self-check: the module is importable and honours TW_PYTEST_ARGS."""
    os.environ["TW_PYTEST_ARGS"] = "--collect-only -q /nonexistent"
    try:
        entry()
    except SystemExit as exc:
        assert "did not run" in str(exc), exc
    else:  # pytest found something under a path that does not exist
        raise AssertionError("expected a fatal pytest exit for a missing path")
    assert shlex.split("a 'b c'") == ["a", "b c"]
    print("pytest_workload: ok")


if __name__ == "__main__":
    demo()
