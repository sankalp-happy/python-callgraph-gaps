#!/usr/bin/env python3
"""Measure PyCG 0.0.8's parse-failure rate on the frozen reference set.

MANIFEST.md §7 item 2. §2 is explicit that this number is *itself a reportable
result*, not a defect to work around: "the rate at which the field's standard
baseline cannot parse contemporary Python is a reportable result. Log every
failure with its traceback into the feasibility survey."

    PACKAGING NOTE, and it is load-bearing. The PyPI sdist for PyCG 0.0.8 ships
    its package directory as `PyCG/` while every internal import says
    `from pycg import ...`. On a case-insensitive filesystem (macOS) that works
    by accident; on Linux -- every container in this project -- the package
    cannot be imported by ANY route, and there is no console script either.
    Verified in python@sha256:72b24f91… (3.10.20):

        import pycg            -> ModuleNotFoundError
        import PyCG.pycg       -> ModuleNotFoundError (its own internal import)
        python -m PyCG         -> ModuleNotFoundError
        pycg --help            -> command not found

    A `pycg -> PyCG` symlink in site-packages fixes all four, and is what this
    script installs. PyPI 0.0.7 packages correctly as lowercase, so the fault is
    specific to the 0.0.8 release. The pin stays at 0.0.8 because reporting
    against the latest published release is the point (MANIFEST §2), but the shim
    is a documented deviation and must travel with the pin.

Method. PyCG is invoked per FILE, with the repo as its package root, because a
rate is what §7 asks for and a whole-repo invocation yields one bit per repo.
Each file gets its own wall-clock alarm; a hang is recorded as a failure like any
other. Results are flushed per file, so a hard interpreter death (PyCG hits
RecursionError readily, and recursion in a C-level visitor can abort the process)
loses at most the tail of one repo rather than the run.

Sampling. Repos with more than --max-files Python files are sampled with a seeded
shuffle, and the number skipped is recorded in the output and printed. A silent
cap would read as full coverage.

Usage:
    python3 pycg_parse_rate.py clone                 # shallow-clone the 14 refs
    python3 pycg_parse_rate.py measure --pyver 3.10 --max-files 120
    python3 pycg_parse_rate.py measure --pyver 3.12  # compare: see the note above
    python3 pycg_parse_rate.py report  --pyver 3.10

    # internal: runs inside the pinned container, one repo
    python3 pycg_parse_rate.py worker --repo /repo --out /out/x.jsonl ...

Exit codes: 0 ok, 2 bad args / missing input, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path

PYCG_PIN = "0.0.8"
# Measured per interpreter, and that is not a detail. PyCG parses with the host
# `ast`, so a file can fail on 3.10 and parse cleanly on 3.12 -- PEP 695 type
# params and PEP 654 `except*` are exactly that case. A single pooled rate would
# blame PyCG for the interpreter's age. MANIFEST §1 takes the same line about
# tracer overhead: report per Python version, never pooled.
DEFAULT_MEASURE_PYVER = "3.10"

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config" / "base_images.json"
REFERENCE = HERE.parent / "config" / "reference_repos.txt"

PER_FILE_TIMEOUT_S = 20


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------- worker (in container)


def worker(args) -> int:
    """Analyse one repo, one file at a time. Runs inside the pinned image."""
    import signal

    sys.setrecursionlimit(args.recursion_limit)

    class Alarm(Exception):
        pass

    def _alarm(signum, frame):  # noqa: ANN001, ARG001
        raise Alarm(f"exceeded {PER_FILE_TIMEOUT_S}s")

    signal.signal(signal.SIGALRM, _alarm)

    repo = Path(args.repo)
    files = sorted(p for p in repo.rglob("*.py") if p.is_file())
    n_total = len(files)
    skipped = 0
    if args.max_files and n_total > args.max_files:
        random.Random(args.seed).shuffle(files)
        files = sorted(files[: args.max_files])
        skipped = n_total - len(files)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    from pycg.pycg import CallGraphGenerator  # noqa: PLC0415

    with out.open("w") as fh:
        fh.write(json.dumps({
            "record": "meta", "repo": args.repo_url, "sha": args.sha,
            "pycg_version": PYCG_PIN, "python": sys.version.split()[0],
            "n_py_files_total": n_total, "n_analysed": len(files),
            "n_skipped_by_cap": skipped, "max_files": args.max_files,
            "seed": args.seed, "recursion_limit": args.recursion_limit,
            "per_file_timeout_s": PER_FILE_TIMEOUT_S,
        }) + "\n")
        fh.flush()

        for f in files:
            rel = str(f.relative_to(repo))
            rec = {"record": "file", "path": rel, "outcome": "OK",
                   "exc_type": "", "exc_msg": "", "traceback": ""}
            signal.alarm(PER_FILE_TIMEOUT_S)
            try:
                cg = CallGraphGenerator([str(f)], str(repo),
                                        args.max_iter, "call-graph")
                cg.analyze()
                rec["n_nodes"] = len(cg.output().keys())
            except SyntaxError as e:
                # The headline number: the published baseline cannot PARSE this.
                rec.update(outcome="SYNTAX_ERROR", exc_type="SyntaxError",
                           exc_msg=f"{e.msg} (line {e.lineno})",
                           traceback=traceback.format_exc()[-1500:])
            except RecursionError as e:
                rec.update(outcome="RECURSION_ERROR", exc_type="RecursionError",
                           exc_msg=str(e)[:300],
                           traceback=traceback.format_exc()[-1500:])
            except Alarm as e:
                rec.update(outcome="TIMEOUT", exc_type="Timeout",
                           exc_msg=str(e))
            except MemoryError:
                rec.update(outcome="MEMORY_ERROR", exc_type="MemoryError")
            except BaseException as e:  # noqa: BLE001
                # Deliberately broad. Everything PyCG throws is data, and a
                # crash here would end the repo's run.
                rec.update(outcome="OTHER_ERROR", exc_type=type(e).__name__,
                           exc_msg=str(e)[:300],
                           traceback=traceback.format_exc()[-1500:])
            finally:
                signal.alarm(0)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
    return 0


# ------------------------------------------------------------------ host: clone


def stage_clone(args) -> int:
    urls = [ln.strip() for ln in REFERENCE.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    dest_root = args.data / "refrepos"
    dest_root.mkdir(parents=True, exist_ok=True)
    log(f"[clone] {len(urls)} reference repos -> {dest_root}")
    shas: dict[str, str] = {}
    for i, url in enumerate(urls, 1):
        name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
        dest = dest_root / name
        if not dest.exists():
            # Shallow: the reference set includes ansible and django, and this
            # measurement reads the tree, never the history.
            p = subprocess.run(["git", "clone", "--depth", "1", "--quiet", url,
                                str(dest)], capture_output=True, text=True,
                               timeout=1800)
            if p.returncode != 0:
                log(f"  [{i}/{len(urls)}] {name}: CLONE FAILED "
                    f"{p.stderr.strip()[:160]}")
                continue
        sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        shas[name] = sha
        n_py = sum(1 for _ in dest.rglob("*.py"))
        log(f"  [{i}/{len(urls)}] {name:<12} sha={sha[:12]} py_files={n_py}")
    (dest_root / "_shas.json").write_text(json.dumps(shas, indent=2) + "\n")
    log(f"[clone] shas recorded -> {dest_root / '_shas.json'}")
    return 0


# ---------------------------------------------------------------- host: measure


def resolve_image(pyver: str) -> str | None:
    script = HERE / "resolve_image.py"
    try:
        p = subprocess.run([sys.executable, str(script), pyver],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() or None


def stage_measure(args) -> int:
    root = args.data / "refrepos"
    if not root.exists():
        log(f"[measure] no clones at {root}; run `clone` first")
        return 2
    shas = json.loads((root / "_shas.json").read_text()) if (root / "_shas.json").exists() else {}

    img = resolve_image(args.pyver)
    if not img:
        log(f"[measure] could not resolve a pinned {args.pyver} image — "
            f"is Docker running?")
        return 3
    log(f"[measure] PyCG {PYCG_PIN} inside {img}")
    log(f"[measure] cap {args.max_files} files/repo (seeded {args.seed}); "
        f"skips are recorded, not silent")

    out_root = args.data / "pycg" / f"py{args.pyver}"
    out_root.mkdir(parents=True, exist_ok=True)
    repos = sorted(p for p in root.iterdir() if p.is_dir())

    for i, repo in enumerate(repos, 1):
        out_file = out_root / f"{repo.name}.jsonl"
        if out_file.exists() and args.resume:
            log(f"  [{i}/{len(repos)}] {repo.name}: cached")
            continue
        url = f"https://github.com/?/{repo.name}"
        # NOTE: no --network=none here, unlike density_score.py's container. That
        # one needs no install; this one pip-installs PyCG from PyPI and cannot
        # reach it on an isolated network. PyCG itself makes no network calls --
        # the repo is mounted read-only and the analysis is purely local.
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{repo}:/repo:ro",
            "-v", f"{out_root}:/out",
            "-v", f"{HERE}:/s:ro",
            img, "bash", "-c",
            # The symlink shim. Without it nothing below can import.
            f"pip install -q pycg=={PYCG_PIN} >/dev/null 2>&1; "
            f'SP=$(python -c "import site;print(site.getsitepackages()[0])"); '
            f'ln -sfn "$SP/PyCG" "$SP/pycg"; '
            f"python3 /s/pycg_parse_rate.py worker --repo /repo "
            f"--out /out/{repo.name}.jsonl --repo-url {url} "
            f"--sha {shas.get(repo.name, 'unknown')} "
            f"--max-files {args.max_files} --seed {args.seed} "
            f"--max-iter {args.max_iter} --recursion-limit {args.recursion_limit}",
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=args.repo_timeout)
            tag = "ok" if p.returncode == 0 else f"rc={p.returncode}"
            if p.returncode != 0:
                tag += f" {p.stderr.strip()[-200:]}"
        except subprocess.TimeoutExpired:
            tag = f"TIMEOUT after {args.repo_timeout}s (partial results kept)"
        n = sum(1 for _ in out_file.open()) - 1 if out_file.exists() else 0
        log(f"  [{i}/{len(repos)}] {repo.name:<12} {n:>4} files  {tag}")
    return stage_report(args)


# ----------------------------------------------------------------- host: report


def stage_report(args) -> int:
    out_root = args.data / "pycg" / f"py{args.pyver}"
    # Exclude this stage's own output: it lands in the same directory and would
    # otherwise be re-read as though it were another repo's results.
    files = sorted(p for p in out_root.glob("*.jsonl")
                   if p.name != "pycg_failures.jsonl") if out_root.exists() else []
    if not files:
        log(f"[report] no results in {out_root}; run `measure` first")
        return 2

    grand = Counter()
    total_files = 0
    total_skipped = 0
    per_repo = []
    failures: list[dict] = []

    for f in files:
        meta = None
        c = Counter()
        for line in f.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("record") == "meta":
                meta = r
                continue
            c[r.get("outcome", "?")] += 1
            if r.get("outcome") != "OK":
                failures.append({"repo": f.stem, **r})
        n = sum(c.values())
        if not n:
            continue
        fail = n - c["OK"]
        per_repo.append((f.stem, n, fail, fail / n * 100,
                         meta.get("n_skipped_by_cap", 0) if meta else 0,
                         meta.get("n_py_files_total", n) if meta else n))
        grand.update(c)
        total_files += n
        total_skipped += (meta or {}).get("n_skipped_by_cap", 0)

    log(f"[report] PyCG {PYCG_PIN} on python {args.pyver}, {len(per_repo)} repos, "
        f"{total_files} files analysed, {total_skipped} skipped by the "
        f"--max-files cap")
    log("")
    log(f"{'repo':<14}{'analysed':>9}{'failed':>8}{'rate':>8}   "
        f"{'skipped':>8}{'py_total':>9}")
    for name, n, fail, pct, skip, tot in sorted(per_repo, key=lambda x: -x[3]):
        log(f"{name:<14}{n:>9}{fail:>8}{pct:>7.1f}%   {skip:>8}{tot:>9}")
    log("")

    fail_total = total_files - grand["OK"]
    log(f"[report] OVERALL parse/analysis failure rate: {fail_total}/{total_files} "
        f"= {fail_total / max(1, total_files) * 100:.1f}%")
    log("")
    log("[report] by outcome:")
    for k, n in grand.most_common():
        log(f"         {k:<16} {n:>6}  ({n / max(1, total_files) * 100:5.1f}%)")
    log("")

    # §2: "Log every failure with its traceback into the feasibility survey."
    survey = out_root / "pycg_failures.jsonl"
    with survey.open("w") as fh:
        for r in failures:
            fh.write(json.dumps(r) + "\n")
    log(f"[report] {len(failures)} failures with tracebacks -> {survey}")

    log("")
    log("[report] most common failure messages:")
    msgs = Counter(f"{r['exc_type']}: {r['exc_msg'][:70]}" for r in failures)
    for k, n in msgs.most_common(12):
        log(f"         {n:>4}x  {k}")
    return 0


# ---------------------------------------------------------------------- driver


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["clone", "measure", "report", "worker"])
    ap.add_argument("--data", type=Path,
                    default=Path(os.environ.get("TW_DATA",
                                                Path.home() / "traceweave-data")))
    ap.add_argument("--pyver", default=DEFAULT_MEASURE_PYVER,
                    help="interpreter to measure under. Results are kept per "
                         "version in pycg/py<ver>/ and never pooled")
    ap.add_argument("--max-files", type=int, default=120,
                    help="per-repo cap; overflow is sampled with --seed and the "
                         "skip count is recorded")
    ap.add_argument("--seed", type=int, default=20260727)
    ap.add_argument("--max-iter", type=int, default=-1,
                    help="PyCG's fixpoint iteration cap; -1 = its default")
    ap.add_argument("--recursion-limit", type=int, default=10000,
                    help="RecursionError is a real PyCG failure mode; raising this "
                         "measures parseability rather than stack depth")
    ap.add_argument("--repo-timeout", type=int, default=3600)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    # worker-only
    ap.add_argument("--repo")
    ap.add_argument("--out")
    ap.add_argument("--repo-url", default="")
    ap.add_argument("--sha", default="")
    args = ap.parse_args()

    if args.stage == "clone":
        return stage_clone(args)
    if args.stage == "measure":
        return stage_measure(args)
    if args.stage == "report":
        return stage_report(args)
    if not args.repo or not args.out:
        log("FATAL: worker needs --repo and --out")
        return 2
    return worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
