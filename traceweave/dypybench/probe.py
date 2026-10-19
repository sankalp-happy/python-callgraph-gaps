#!/usr/bin/env python3
"""Week-1 gate: which of DyPyBench's 50 projects install under Python 3.11+.

`plan_pivot_nov2026.md` §"The week-1 gate". `demo/tracer.py` reads
`frame.f_code.co_qualname`, added in Python 3.11. DyPyBench's own image builds
`FROM ubuntu:latest` and installs the distro `python3`, which is 3.10. So either
the corpus runs on 3.11 or the tracer needs a qualname backfill. This script
answers that, per project, with a number instead of a guess.

The decision rule is pre-committed by the plan, so record it before running:

  >= 25 projects install on 3.11   run that subset, `co_qualname` unchanged.
  < 25                             backfill qualname on 3.10 from `co_name` plus
                                   the self/cls binding in `frame.f_locals`.

3.10 IS THE CONTROL ARM, AND IT IS NOT OPTIONAL. A fresh install in 2026 does
not reproduce DyPyBench's 2023 environments: several of these projects have
UNPINNED dev requirements, so `pip install -r` resolves three years forward.
Verified on dbader/schedule, whose requirements-dev.txt asks for a bare `pytest`
and a 2023-era `pytest-flake8`; today that resolves to pytest 9 and the plugin
fails hook validation, on every Python version alike. Probing only 3.11 would
score that as "does not work on 3.11" and the gate would be wrong.

So every project is probed on 3.10 as well, and `report` reads the difference,
not the absolute:

  fails on 3.11, passes on 3.10   the Python version is the cause. Counts.
  fails on both                   dependency drift or a system dependency.
                                  Says nothing about 3.11. Excluded from the gate.

The plan's own instruction not to rebuild DyPyBench's venvs wholesale is the
same point from the other side. This probe measures feasibility on a fresh
install; the corpus itself should still come from their published image.

Three things this does NOT do, each deliberate:

  no rebuild    The plan forbids rebuilding DyPyBench's venvs wholesale: their
                resolved dependency sets are part of the corpus's identity, the
                same argument MANIFEST §1 makes for ours. This clones into a
                scratch dir and never touches an installed /Project tree. It
                measures feasibility; it does not become the corpus.
  no extras     Only what `scripts/install-all-projects.sh` installs, plus the
                per-project test extras it hardcodes (without them ~10 projects
                fail COLLECT for a reason that has nothing to do with 3.11).
  no upgrade    setuptools is left where the base image put it. setuptools 66
                (Jan 2023) made PEP 440 parsing strict and some of these
                pre-2023-01-18 commits have metadata that no longer parses.
                That is a real install failure and it is recorded as one;
                `--setuptools '<66'` re-runs to separate the two causes.

Verdicts, narrowest to widest:

  INSTALL_FAIL   `pip install .` (or `-r <req>`) returned non-zero.
  COLLECT_FAIL   installed, but `pytest --collect-only` found nothing runnable.
  COLLECT_EMPTY  collected zero tests. Installs, cannot supply a workload.
  OK             installs and collects >0 tests. Usable on this Python version.

Usage:
    # one image per version under test, control arm included
    for v in 3.10 3.11 3.12; do
        docker build --build-arg PYVER=$v -t tw-dypybench:$v .
    done

    # the gate: 50 projects x 3 versions, resumable, ~150 container runs
    python3 probe.py run --jobs 4

    python3 probe.py run --pyvers 3.11 --limit 5     # smoke test first
    python3 probe.py run --dry-run                   # plan only, no docker
    python3 probe.py report --verbose                # the gate answer

    # W1's second half: one project traced end to end
    python3 probe.py trace --project 10 --pyver 3.11

Stdlib only, like every other script in this harness.

Exit codes: 0 ok, 2 bad args / missing input, 3 environment not usable.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRACEWEAVE = HERE.parent
PROJECT_LIST = HERE / "github-url.txt"

# DyPyBench pins every project to its last commit before this date, and says
# plainly that changing it breaks the projects. It is part of the corpus
# identity, not a tunable.
CHECKOUT_UNTIL = "2023-01-18"

INSTALL_TIMEOUT = 1800
COLLECT_TIMEOUT = 600
TRACE_TIMEOUT = 7200

RESULT_SENTINEL = "TW_RESULT "

# Copied verbatim from scripts/install-all-projects.sh, where they are commented
# "required for running tests". Without them these projects fail COLLECT for a
# missing test-only dependency, which would be recorded as a Python-version
# verdict. Keyed by URL exactly as the upstream script keys them.
EXTRA_TEST_DEPS = {
    "https://github.com/lorien/grab.git": ["cssselect", "pyquery", "pymongo", "fastrq"],
    "https://github.com/psf/black.git": ["aiohttp"],
    "https://github.com/errbotio/errbot.git": ["mock"],
    "https://github.com/PyFilesystem/pyfilesystem2.git": ["parameterized", "pyftpdlib", "psutil"],
    "https://github.com/wtforms/wtforms.git": ["babel", "email_validator"],
    "https://github.com/geopy/geopy.git": ["docutils"],
    "https://github.com/gawel/pyquery.git": ["webtest"],
    "https://github.com/elastic/elasticsearch-dsl-py.git": ["pytz"],
    "https://github.com/marshmallow-code/marshmallow.git": ["pytz", "simplejson"],
    "https://github.com/pytest-dev/pytest.git": ["hypothesis", "xmlschema"],
}

# Also from install-all-projects.sh: a pinned `invoke==0.13.0` in
# dev-requirements.txt conflicts and upstream patches it in place.
SED_FIXES = {
    "https://github.com/spotify/dh-virtualenv.git":
        (r"0,/invoke==0.13.0/s//invoke/", "dev-requirements.txt"),
}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# --------------------------------------------------------------------------
# The project list
# --------------------------------------------------------------------------

def parse_projects(path: Path) -> list[dict]:
    """`github-url.txt` -> one dict per project, numbered as DyPyBench numbers.

    Upstream format is positional and the position of the test path depends on
    the flags: `URL FLAGS [REQ_FILE] TEST_PATH`, where REQ_FILE is present only
    when FLAGS contains `r`. install-all-projects.sh reads `${parts[2]}` as the
    requirements file under exactly that condition.

    The index is 1-based and matters: DyPyBench installs to `project$idx` and
    `dypybench.py --test N` addresses projects by it. Renumbering would silently
    break every cross-reference to their artifact.
    """
    projects = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            raise SystemExit(f"{path}:{idx}: expected 'URL FLAGS [REQ] TEST', got {line!r}")
        url, flags = parts[0], parts[1]
        if "r" in flags:
            if len(parts) < 4:
                raise SystemExit(f"{path}:{idx}: flags {flags!r} promise a "
                                 f"requirements file and a test path, got {line!r}")
            req, test_path = parts[2], parts[3]
        else:
            req, test_path = None, parts[2]
        projects.append({
            "idx": idx,
            "url": url,
            "name": url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"),
            "flags": flags,
            "req": req,
            "test_path": test_path,
        })
    return projects


# --------------------------------------------------------------------------
# In-container worker
# --------------------------------------------------------------------------

def sh(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> tuple[int, str]:
    """Run, capture combined output, never raise on a non-zero exit."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace")
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as exc:
        tail = exc.output or ""
        if isinstance(tail, bytes):
            tail = tail.decode("utf-8", "replace")
        return 124, f"{tail}\nTIMEOUT after {timeout}s: {' '.join(cmd)}"


def tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.splitlines()[-lines:])


def collected_count(output: str) -> int | None:
    """pytest's own count from `--collect-only -q`, or None if it never said.

    Read from pytest's summary rather than counted from stdout lines, for the
    same reason runner.py does it: `--collect-only` exits non-zero when ANY
    module fails to import, and the count on the summary line is still correct
    for the modules that did import. Discarding a repo because one optional
    extra is missing is the exact false COLLECT_FAIL that triage.sh had.
    """
    for line in reversed(output.splitlines()):
        line = line.strip()
        # "412 tests collected in 1.20s", "3 tests collected, 1 error in 0.5s"
        if "collected" in line:
            head = line.split()[0]
            if head.isdigit():
                return int(head)
        if line.startswith("no tests ran") or line == "no tests collected":
            return 0
    return None


def cmd_worker(args) -> int:
    """Runs INSIDE the container. Installs one project, reports one JSON line."""
    proj = {"idx": args.idx, "url": args.url, "name": args.name,
            "req": args.req or None, "test_path": args.test_path}
    rec = {
        "recorded_utc": now_utc(),
        "pyver_requested": args.pyver,
        "pyver_full": sys.version.split()[0],
        **proj,
    }
    work = Path("/work/repo")
    started = time.time()

    rc, out = sh(["git", "clone", "--quiet", args.url, str(work)], timeout=900)
    if rc != 0:
        rec.update(verdict="CLONE_FAIL", detail=tail(out))
        return _emit(rec, started)

    # Resolve DyPyBench's date pin to a real sha and record it. MANIFEST §3
    # makes `sha` mandatory: a probe verdict against an unrecorded commit says
    # nothing reproducible.
    rc, out = sh(["git", "log", "-n", "1", f"--until={CHECKOUT_UNTIL}",
                  "--format=%H"], cwd=work, timeout=120)
    sha = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
    if not sha:
        rec.update(verdict="CLONE_FAIL",
                   detail=f"no commit before {CHECKOUT_UNTIL}\n{tail(out)}")
        return _emit(rec, started)
    rec["sha"] = sha
    rc, out = sh(["git", "checkout", "--quiet", sha], cwd=work, timeout=300)
    if rc != 0:
        rec.update(verdict="CLONE_FAIL", detail=tail(out))
        return _emit(rec, started)

    if args.setuptools:
        rc, out = sh([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                      f"setuptools{args.setuptools}"], timeout=600)
        rec["setuptools_pin"] = args.setuptools
        if rc != 0:
            rec.update(verdict="INSTALL_FAIL", detail=tail(out))
            return _emit(rec, started)

    fix = SED_FIXES.get(args.url)
    if fix:
        expr, target = fix
        sh(["sed", "-i.bak", "-e", expr, target], cwd=work, timeout=60)
        rec["sed_fix"] = target

    steps: list[list[str]] = [[sys.executable, "-m", "pip", "install",
                               "--no-cache-dir", "."]]
    if proj["req"]:
        steps.append([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                      "-r", proj["req"]])
    extras = EXTRA_TEST_DEPS.get(args.url, [])
    if extras:
        steps.append([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                      *extras])

    for step in steps:
        rc, out = sh(step, cwd=work, timeout=INSTALL_TIMEOUT)
        if rc != 0:
            rec.update(verdict="INSTALL_FAIL", failed_step=" ".join(step[3:]),
                       detail=tail(out, 40))
            return _emit(rec, started)

    # pytest LAST and only if the project did not pin its own. Upstream's
    # install-all-projects.sh ends with an unconditional `pip install pytest`,
    # which was harmless in Jan 2023 and is not harmless now: it upgrades past
    # the pytest that the project's own requirements pinned, and a 2023-era
    # plugin then fails hook validation. Verified on dbader/schedule, whose
    # requirements-dev.txt brings pytest-flake8: the unconditional upgrade turns
    # a working suite into COLLECT_FAIL. That would be recorded as a verdict
    # about Python 3.11, which it is not.
    rc, out = sh([sys.executable, "-m", "pytest", "--version"], cwd=work, timeout=120)
    if rc != 0:
        rc, out = sh([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                      "pytest"], cwd=work, timeout=INSTALL_TIMEOUT)
        if rc != 0:
            rec.update(verdict="INSTALL_FAIL", failed_step="pytest",
                       detail=tail(out, 40))
            return _emit(rec, started)
        rec["pytest_added"] = True
        rc, out = sh([sys.executable, "-m", "pytest", "--version"], cwd=work, timeout=120)
    rec["pytest_version"] = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""

    # The resolved dependency set, hashed the same way MANIFEST §3 hashes it.
    # Not the corpus pin, but without it a later "it installed on 3.11" cannot
    # be reproduced against the same packages.
    rc, freeze = sh([sys.executable, "-m", "pip", "freeze"], cwd=work, timeout=300)
    rec["lock_sha256"] = hashlib.sha256(freeze.encode()).hexdigest() if rc == 0 else ""
    rec["lock_pkgs"] = len([l for l in freeze.splitlines() if l.strip()]) if rc == 0 else 0

    rc, out = sh([sys.executable, "-m", "pytest", "--collect-only", "-q",
                  "-p", "no:cacheprovider", proj["test_path"]],
                 cwd=work, timeout=COLLECT_TIMEOUT)
    n = collected_count(out)
    rec["collect_rc"] = rc
    rec["n_collected"] = n
    if n is None:
        rec.update(verdict="COLLECT_FAIL", detail=tail(out, 40))
    elif n == 0:
        rec.update(verdict="COLLECT_EMPTY", detail=tail(out, 15))
    else:
        rec.update(verdict="OK", detail="")

    if args.trace_out and rec["verdict"] == "OK":
        _trace(rec, work, proj, Path(args.trace_out))
    return _emit(rec, started)


def _trace(rec: dict, work: Path, proj: dict, out_path: Path) -> None:
    """Trace this project's suite with the tracer, in this same interpreter's
    container. Only reached when the suite actually collects."""
    sys.path.insert(0, str(Path("/tw/static")))
    try:
        import extract  # noqa: PLC0415 -- only needed in trace mode
    except Exception as exc:  # pragma: no cover -- mount problem, not a result
        rec["trace_error"] = f"cannot import extract from /tw/static: {exc}"
        return

    layout = extract.detect_layout(work)
    rec["layout"] = layout["layout"]
    rec["packages"] = layout["packages"]
    if layout["layout"] == "unknown" or not layout["packages"]:
        rec["trace_error"] = "no_python_package_found"
        return
    # Several of these repos ship more than one top-level package. Prefer the
    # one whose name matches the project, so `celery` is traced rather than
    # whatever sorts first, and record the choice either way.
    stem = proj["name"].replace("-", "_").replace(".", "_").lower()
    chosen = next((p for p in layout["packages"]
                   if Path(p).name.lower() in (stem, stem.replace("_", ""))),
                  layout["packages"][0])
    rec["traced_package"] = chosen

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "/tw/demo/tracer.py", "trace-package",
           "--src-root", str(work / layout["src_root"]),
           "--package", str(work / chosen),
           "--workload", "/tw/dypybench/pytest_workload.py",
           "--entry", "entry",
           "--run-id", f"dypybench-{proj['idx']}-{rec['pyver_requested']}",
           "--out", str(out_path)]
    # The workload reads its pytest args from the environment, because
    # trace-package owns argv.
    os.environ["TW_PYTEST_ARGS"] = proj["test_path"]
    rc, out = sh(cmd, cwd=work, timeout=TRACE_TIMEOUT)
    rec["trace_rc"] = rc
    rec["trace_cmd"] = (f"TW_PYTEST_ARGS={shlex.quote(proj['test_path'])} "
                        + " ".join(cmd))
    if rc != 0:
        rec["trace_error"] = tail(out, 40)
    else:
        rec["trace_tail"] = tail(out, 5)


def _emit(rec: dict, started: float) -> int:
    rec["seconds_total"] = round(time.time() - started, 1)
    print(RESULT_SENTINEL + json.dumps(rec), flush=True)
    return 0


# --------------------------------------------------------------------------
# Host driver
# --------------------------------------------------------------------------

def docker_ok() -> bool:
    rc, _ = sh(["docker", "version", "--format", "{{.Server.Arch}}"], timeout=60)
    return rc == 0


def docker_arch() -> str:
    rc, out = sh(["docker", "version", "--format", "{{.Server.Arch}}"], timeout=60)
    return out.strip() if rc == 0 else ""


def worker_cmd(proj: dict, pyver: str, args, trace_out: str | None) -> list[str]:
    inner = ["python3", "/tw/dypybench/probe.py", "worker",
             "--idx", str(proj["idx"]), "--url", proj["url"],
             "--name", proj["name"], "--test-path", proj["test_path"],
             "--pyver", pyver]
    if proj["req"]:
        inner += ["--req", proj["req"]]
    if args.setuptools:
        inner += ["--setuptools", args.setuptools]
    if trace_out:
        inner += ["--trace-out", trace_out]
    cmd = ["docker", "run", "--rm",
           "--name", f"tw-dypy-{pyver.replace('.', '')}-{proj['idx']}",
           f"--memory={args.memory}",
           "-v", f"{TRACEWEAVE}:/tw:ro"]
    if trace_out:
        cmd += ["-v", f"{Path(args.data).resolve()}:/out"]
    cmd += [f"{args.image}:{pyver}", *inner]
    return cmd


def run_one(proj: dict, pyver: str, args, trace_out: str | None = None) -> dict:
    cmd = worker_cmd(proj, pyver, args, trace_out)
    # The container is named, so a client-side timeout can still kill it. The
    # same defect cost Phase 1 four cores to abandoned PyCG containers: `--rm`
    # only fires on exit, and subprocess timeouts kill the client, not the
    # container.
    limit = TRACE_TIMEOUT + 900 if trace_out else INSTALL_TIMEOUT * 3
    rc, out = sh(cmd, timeout=limit)
    for line in reversed(out.splitlines()):
        if line.startswith(RESULT_SENTINEL):
            rec = json.loads(line[len(RESULT_SENTINEL):])
            rec["docker_rc"] = rc
            return rec
    name = f"tw-dypy-{pyver.replace('.', '')}-{proj['idx']}"
    sh(["docker", "kill", name], timeout=120)
    return {"recorded_utc": now_utc(), "pyver_requested": pyver, **proj,
            "verdict": "HARNESS_FAIL", "docker_rc": rc, "detail": tail(out, 40)}


def cmd_run(args) -> int:
    projects = parse_projects(Path(args.projects))
    pyvers = [v.strip() for v in args.pyvers.split(",") if v.strip()]
    if args.limit:
        projects = projects[:args.limit]
    if args.only:
        want = {int(x) for x in args.only.split(",")}
        projects = [p for p in projects if p["idx"] in want]

    data = Path(args.data).expanduser()
    data.mkdir(parents=True, exist_ok=True)
    ledger = data / "probe.jsonl"
    done = {(r.get("pyver_requested"), r.get("idx")) for r in read_jsonl(ledger)
            if r.get("verdict") not in (None, "HARNESS_FAIL")} if not args.force else set()

    jobs = [(p, v) for v in pyvers for p in projects if (v, p["idx"]) not in done]
    log(f"[run] {len(jobs)} of {len(projects) * len(pyvers)} "
        f"(project, pyver) pairs to probe -> {ledger}")
    if args.dry_run:
        for p, v in jobs:
            print(f"  {v}  project{p['idx']:<3} {p['name']:<24} "
                  f"tests={p['test_path']}")
        return 0
    if not docker_ok():
        log("FATAL: docker is not usable")
        return 3
    arch = docker_arch()
    if arch != "amd64":
        log(f"FATAL: docker reports {arch!r}. DyPyBench is amd64 and MANIFEST §1 "
            f"forbids emulated attempts. Run this on the Linux host.")
        return 3

    lock = threading.Lock()
    counts: dict[str, int] = {}

    def work(job):
        proj, pyver = job
        rec = run_one(proj, pyver, args)
        with lock:
            with ledger.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
            log(f"  {pyver} project{proj['idx']:<3} {proj['name']:<24} "
                f"{rec['verdict']:<14} {rec.get('n_collected', '-')} tests "
                f"{rec.get('seconds_total', '?')}s")
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(work, jobs))
    log(f"[run] done: {counts}")
    return 0


def cmd_trace(args) -> int:
    projects = {p["idx"]: p for p in parse_projects(Path(args.projects))}
    if args.project not in projects:
        log(f"FATAL: --project {args.project} is not in {args.projects}")
        return 2
    if not docker_ok():
        log("FATAL: docker is not usable")
        return 3
    proj = projects[args.project]
    data = Path(args.data).expanduser()
    data.mkdir(parents=True, exist_ok=True)
    rel = f"trace-project{proj['idx']}-{args.pyver}.json"
    log(f"[trace] project{proj['idx']} {proj['name']} on {args.pyver} -> {data / rel}")
    rec = run_one(proj, args.pyver, args, trace_out=f"/out/{rel}")
    with (data / "trace.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    log(f"[trace] verdict={rec['verdict']} layout={rec.get('layout')} "
        f"package={rec.get('traced_package')} trace_rc={rec.get('trace_rc')}")
    if rec.get("trace_error"):
        log(f"[trace] error: {rec['trace_error']}")
        return 1
    log(f"[trace] {rec.get('trace_tail', '')}")
    return 0 if rec.get("trace_rc") == 0 else 1


GATE = 25

# The control arm: DyPyBench's own Python version. See the module docstring.
CONTROL = "3.10"


def cmd_report(args) -> int:
    ledger = Path(args.data).expanduser() / "probe.jsonl"
    recs = read_jsonl(ledger)
    if not recs:
        log(f"no records in {ledger}")
        return 2
    # Later records win: a re-run under --setuptools supersedes the first pass.
    latest: dict[tuple, dict] = {}
    for r in recs:
        latest[(r.get("pyver_requested"), r.get("idx"))] = r

    by_ver: dict[str, list[dict]] = {}
    for (pyver, _), r in sorted(latest.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        by_ver.setdefault(pyver, []).append(r)

    print(f"\nDyPyBench Python-version probe  ({len(latest)} records, {ledger})\n")
    print(f"{'pyver':<8}{'OK':>5}{'COLLECT_EMPTY':>15}{'COLLECT_FAIL':>14}"
          f"{'INSTALL_FAIL':>14}{'other':>7}{'tests':>9}")
    for pyver, rows in sorted(by_ver.items()):
        c = {}
        for r in rows:
            c[r["verdict"]] = c.get(r["verdict"], 0) + 1
        known = ("OK", "COLLECT_EMPTY", "COLLECT_FAIL", "INSTALL_FAIL")
        other = sum(v for k, v in c.items() if k not in known)
        tests = sum(r.get("n_collected") or 0 for r in rows)
        print(f"{pyver:<8}{c.get('OK', 0):>5}{c.get('COLLECT_EMPTY', 0):>15}"
              f"{c.get('COLLECT_FAIL', 0):>14}{c.get('INSTALL_FAIL', 0):>14}"
              f"{other:>7}{tests:>9}")

    control = {r["idx"]: r["verdict"] for r in by_ver.get(CONTROL, [])}
    if not control:
        print(f"\nNo {CONTROL} control arm in this ledger. Run "
              f"`--pyvers {CONTROL}` before reading the gate: without it a "
              f"failure caused by three years of dependency drift is "
              f"indistinguishable from one caused by the Python version.")

    print("\nThe gate (plan_pivot_nov2026.md, week 1):")
    for pyver in sorted(by_ver):
        if pyver == CONTROL:
            continue
        rows = by_ver[pyver]
        ok = sum(1 for r in rows if r["verdict"] == "OK")
        # Attributable only when the control passed the same project. A project
        # that fails on 3.10 too failed for a reason that predates the version
        # question, so it is neither a 3.11 success nor a 3.11 failure.
        version_caused = [r["idx"] for r in rows
                          if r["verdict"] != "OK" and control.get(r["idx"]) == "OK"]
        drift = [r["idx"] for r in rows
                 if r["verdict"] != "OK" and control.get(r["idx"]) not in (None, "OK")]
        print(f"  {pyver}: {ok} usable")
        if control:
            print(f"        {len(version_caused)} broken BY the version "
                  f"(pass on {CONTROL}): {version_caused or '-'}")
            print(f"        {len(drift)} broken anyway (fail on {CONTROL} too, "
                  f"not a version verdict): {drift or '-'}")
        if ok >= GATE:
            print(f"        >= {GATE}. Run this subset. co_qualname unchanged.")
        else:
            print(f"        < {GATE}. Backfill qualname on {CONTROL} from "
                  f"co_name plus the self/cls binding in f_locals.")

    failed = [r for r in latest.values() if r["verdict"] != "OK"]
    if failed and args.verbose:
        print("\nEvery non-OK verdict, with the reason:")
        for r in sorted(failed, key=lambda r: (r["pyver_requested"], r["idx"])):
            print(f"\n--- {r['pyver_requested']} project{r['idx']} {r['name']}"
                  f"  {r['verdict']}  step={r.get('failed_step', '-')}")
            print("    " + "\n    ".join((r.get("detail") or "").splitlines()[-8:]))
    elif failed:
        print(f"\n{len(failed)} non-OK verdicts. Re-run with --verbose for the reasons.")
    return 0


def demo() -> None:
    """Self-check on the two pieces with real logic: the positional parse and
    pytest's collected count. Both are silent-wrong-answer risks."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "urls.txt"
        p.write_text(
            "https://github.com/lorien/grab.git rt requirements_dev.txt tests\n"
            "https://github.com/flask-api/flask-api.git t flask_api/tests\n"
            "https://github.com/celery/celery.git rt requirements/test.txt t\n"
            "https://github.com/patx/pickledb.git t ./tests.py\n")
        got = parse_projects(p)
    assert [g["idx"] for g in got] == [1, 2, 3, 4], got
    assert got[0]["req"] == "requirements_dev.txt" and got[0]["test_path"] == "tests"
    assert got[1]["req"] is None and got[1]["test_path"] == "flask_api/tests"
    # celery's test path is the single letter `t`, which is exactly the kind of
    # value a naive parse mistakes for a flag.
    assert got[2]["req"] == "requirements/test.txt" and got[2]["test_path"] == "t"
    assert got[3]["name"] == "pickledb" and got[3]["test_path"] == "./tests.py"
    assert got[1]["name"] == "flask-api"

    assert collected_count("412 tests collected in 1.20s") == 412
    assert collected_count("3 tests collected, 1 error in 0.5s") == 3
    assert collected_count("no tests ran in 0.01s") == 0
    assert collected_count("ERROR: file or directory not found: tests") is None
    # A repo where one module fails to import still reports a usable count, and
    # discarding it would be triage.sh's false COLLECT_FAIL all over again.
    assert collected_count("442 tests collected, 1 error in 3.1s\n"
                           "ERROR tests/test_d.py") == 442
    assert len(parse_projects(PROJECT_LIST)) == 50, "the corpus is 50 projects"
    print("probe: ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--projects", default=str(PROJECT_LIST))
        p.add_argument("--data", default="~/dypybench-data")
        p.add_argument("--image", default="tw-dypybench")
        p.add_argument("--memory", default="4g")
        p.add_argument("--setuptools", default="",
                       help="pin setuptools before installing, e.g. '<66', to "
                            "separate a PEP 440 metadata failure from a real "
                            "Python-version failure")

    r = sub.add_parser("run", help="probe every project on every version")
    common(r)
    r.add_argument("--pyvers", default="3.10,3.11,3.12",
                   help="3.10 is the control arm and the gate is unreadable "
                        "without it")
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--only", default="", help="comma-separated project indices")
    r.add_argument("--force", action="store_true", help="re-probe finished pairs")
    r.add_argument("--dry-run", action="store_true")

    t = sub.add_parser("trace", help="trace one project's suite end to end")
    common(t)
    t.add_argument("--project", type=int, required=True)
    t.add_argument("--pyver", default="3.11")

    rep = sub.add_parser("report", help="the week-1 gate answer")
    rep.add_argument("--data", default="~/dypybench-data")
    rep.add_argument("--verbose", action="store_true")

    w = sub.add_parser("worker", help="internal: runs inside the container")
    w.add_argument("--idx", type=int, required=True)
    w.add_argument("--url", required=True)
    w.add_argument("--name", required=True)
    w.add_argument("--test-path", required=True)
    w.add_argument("--pyver", required=True)
    w.add_argument("--req", default="")
    w.add_argument("--setuptools", default="")
    w.add_argument("--trace-out", default="")

    sub.add_parser("selftest", help="run demo()")

    args = ap.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "trace":
        return cmd_trace(args)
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "worker":
        return cmd_worker(args)
    demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
