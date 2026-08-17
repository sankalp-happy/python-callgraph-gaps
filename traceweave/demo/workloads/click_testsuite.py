"""Workload: click's own test suite, run in-process under the tracer.

Why click's tests rather than a script we write: a workload we author would
only exercise the paths we thought of, and "the calls Sankalp remembered to
make" is not a measurement of anything. The project's own test suite is
written by the library's maintainers to cover its real behaviour, and it is
the workload triage already certified for this repo (corpus/click/py3.12/
result.env: n_collected=1965, status=GREEN).

In-process (`pytest.main`) rather than a subprocess, because `sys.setprofile`
only sees the process it is armed in -- a subprocess would produce an empty
trace and a 100%-missing result that looks spectacular and means nothing.

`click/testing.py` (CliRunner) drives most of these tests but is NOT in the
traced module set: PyCG cannot analyse it (see pycg_scaling.py), so it is
excluded from both sides. Calls it makes into click land as `<entry>` edges
and are held out of the ratio -- see tracer.diff_package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CLICK_REPO = Path(os.environ["CLICK_REPO"]).resolve()


def main() -> None:
    import pytest

    # click's tests resolve conftest.py and pyproject settings from the repo
    # root; run from anywhere else and collection silently changes shape.
    previous_cwd = Path.cwd()
    os.chdir(CLICK_REPO)
    try:
        code = pytest.main([
            "-q",
            "--no-header",
            "-p", "no:cacheprovider",
            str(CLICK_REPO / "tests"),
        ])
    finally:
        os.chdir(previous_cwd)

    # A workload that half-failed would silently under-report runtime edges,
    # so surface it loudly instead of quietly producing a smaller number.
    if int(code) not in (0, 5):
        print(f"WARNING: click test suite exited {code} -- trace may be partial",
              file=sys.stderr)
