#!/usr/bin/env python3
"""Parallel triage queue over the ins1 recipe ladder.

MANIFEST.md §7 item 3. `triage.sh` is the atom -- ONE repo, ONE Python version,
one attempt. This is the loop around it: it walks the ladder in
`config/base_images.json`, runs N repos concurrently, checkpoints every result,
and independently re-derives each outcome from the attempt log.

Four stages of paranoia, in order of how much they cost us if absent:

  checkpoint  Every completed attempt is appended to the ledger immediately.
              Discovery lost 95 minutes to an unhandled IncompleteRead with no
              checkpointing (DISCOVERY_REPORT.md item 5a); a 558-repo triage run
              is ~100 worker-hours and cannot be allowed to lose any of it.
  verify      triage.sh's own `status` is recorded but NOT trusted. The runner
              re-parses attempt.log and computes `status_verified` beside it.
              Disagreement is a recorded, reportable number -- the same posture
              the project already takes toward classify_v10 vs classify_v11.
  admit       Corpus admission (MANIFEST §4 + amendment 2) is computed here, not
              inherited from `status`. AMBER is admissible, but "AMBER" currently
              covers states that cannot supply an ins2 workload at all, and those
              are separated out with an explicit reason rather than silently
              admitted.
  reclaim     triage.sh rm -rf's its work dir at the START of a run and never at
              the end, so 558 full clones accumulate. The runner deletes each
              working copy once its result is durable.

Two verified triage.sh defects this compensates for (see triage_v1.2.patch):

  1. FALSE COLLECT_FAIL. `pytest --collect-only` exits non-zero if ANY module
     fails to import, so one unimportable optional-extra test module discards the
     whole repo. Verified on psf/black: 444 of 445 modules collect in 0.28s, one
     needs the `.[d]` extra, and the repo is recorded COLLECT_FAIL with an EMPTY
     n_collected and its suite never run -- though it is in fact 442-passing.
     The runner recovers the true count from pytest's own summary line in the log
     and marks the state PARTIAL_COLLECT.
  2. RED UNREACHABLE AFTER INSTALL. triage.sh:244 falls back to
     `grep -q INSTALL_OK`, and discards the docker exit code entirely, so any
     post-install catastrophe -- OOM kill, the `timeout 1800` firing, a daemon
     hiccup -- is recorded as admissible AMBER. The runner detects a missing
     collect marker and classifies KILLED.

Usage:
    # the real thing: 558 repos in queue order
    python3 runner.py run --queue ../../candidates/03_queue.csv --jobs 4

    # Step 10 gate: the first 139 positions only
    python3 runner.py run --queue ../../candidates/03_queue.csv --limit 139

    # validate the runner against the frozen reference set
    python3 runner.py run --repos-from ../config/reference_repos.txt

    # no docker, no clones: validate the queue and print the plan
    python3 runner.py run --queue ../../candidates/03_queue.csv --dry-run

    python3 runner.py report          # survival vs MANIFEST §4 floors

Stdlib only, like every other script in this harness.

Exit codes: 0 ok, 2 bad args / missing input, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

SPEC_VERSION = "1.0"
SHEET_VERSION = "v1.1"

HERE = Path(__file__).resolve().parent
TRIAGE_SH = HERE / "triage.sh"
DEFAULT_CONFIG = HERE.parent / "config" / "base_images.json"

# MANIFEST §4. Duplicated from discover_candidates.py deliberately: these are the
# numbers the report is checked against, and a shared import would let a future
# edit to one script silently move the other's floors.
STRATUM_TARGET = {"LOW": 15, "MED": 20, "HIGH": 25}
STRATUM_FLOOR = {"LOW": 10, "MED": 12, "HIGH": 15}

# triage.sh wraps its container in `timeout 1800`. A build that lands within a
# few seconds of the ceiling was almost certainly killed by it rather than
# finishing, and the distinction decides whether the repo is RED or AMBER.
TRIAGE_DOCKER_TIMEOUT_S = 1800
TIMEOUT_SLACK_S = 5

# Wall-clock ceiling for one triage.sh invocation: the container timeout, plus
# room for the clone (full history, not shallow -- ansible took 18s, some take
# minutes) and image pull.
ATTEMPT_TIMEOUT_S = 2400


# --------------------------------------------------------------------------- io


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_env_file(path: Path) -> dict[str, str]:
    """Parse triage.sh's result.env. Flat KEY=VALUE, no embedded newlines (that
    is the whole point of the file), last assignment wins."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        key, sep, val = line.partition("=")
        if sep and key:
            out[key.strip()] = val.strip()
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                log(f"WARN: malformed ledger line in {path.name}, skipping")
    return rows


# ------------------------------------------------------------------ verification


MARKER_RE = {
    "install_ok": re.compile(r"###INSTALL_OK###"),
    "install_fail": re.compile(r"###INSTALL_FAIL###"),
    "collect_ok": re.compile(r"###COLLECT_OK###"),
    "collect_fail": re.compile(r"###COLLECT_FAIL###"),
    # v1.2 markers. Kept alongside the v1.1 set rather than replacing it: logs
    # written by v1.1 still have to classify correctly, because the 14-repo
    # spot-check and the reference-set validation runs predate the patch.
    "collect_partial": re.compile(r"###COLLECT_PARTIAL###"),
    "script_end": re.compile(r"###SCRIPT_END###"),
}
NCOLLECT_ERRORS_RE = re.compile(r"###NCOLLECT_ERRORS=(\d+)###")
NCOLLECT_RE = re.compile(r"###NCOLLECT=(\d+)###")
TESTS_RC_RE = re.compile(r"###TESTS_RC=(-?\d+)###")
# pytest's own summary, which triage.sh tails into the log even on the failure
# path. This is what makes a false COLLECT_FAIL recoverable after the fact.
#
# Two forms, and the order matters. A repo that deselects by default prints
# "1965/32965 tests collected (31000 deselected)" -- click does exactly that. The
# selected count is the one that will run; matching the plain form first would
# capture the total out of the middle of the slash form and overstate it 16x.
PYTEST_SELECTED_RE = re.compile(r"(\d+)/(\d+)\s+tests?\s+collected")
PYTEST_COLLECTED_RE = re.compile(r"(?<![\d/])(\d+)\s+tests?\s+collected")
PYTEST_COLLECT_ERRORS_RE = re.compile(r"collected.*?,\s*(\d+)\s+errors?")
PYTEST_INTERRUPTED_RE = re.compile(r"Interrupted:\s*(\d+)\s+error")


def verify_attempt(env: dict[str, str], log_path: Path) -> dict:
    """Re-derive the outcome from the attempt log, independently of triage.sh.

    Returns the verified fields. Never raises: a missing or unreadable log is
    itself a finding (LOG_MISSING), not an exception -- a crash here would lose
    the attempt, which is the one thing the ledger exists to prevent.
    """
    v: dict = {
        "status_verified": "UNKNOWN",
        "error_class_runner": "NONE",
        "n_collected_verified": "",
        "n_collect_errors": "",
        "tests_rc": "",
        "verify_note": "",
    }
    try:
        text = log_path.read_text(errors="replace") if log_path.exists() else ""
    except OSError as e:
        v.update(status_verified="RED", error_class_runner="LOG_UNREADABLE",
                 verify_note=str(e)[:200])
        return v
    if not text:
        v.update(status_verified="RED", error_class_runner="LOG_MISSING",
                 verify_note=f"no log at {log_path}")
        return v

    seen = {k: bool(rx.search(text)) for k, rx in MARKER_RE.items()}
    m = TESTS_RC_RE.search(text)
    tests_rc = int(m.group(1)) if m else None
    v["tests_rc"] = "" if tests_rc is None else str(tests_rc)

    m = NCOLLECT_RE.search(text)
    ncollect = int(m.group(1)) if m else None
    # Recovery path: on the COLLECT_FAIL branch triage.sh emits no NCOLLECT
    # marker but does tail pytest's summary, which states the real count.
    recovered = None
    for mm in PYTEST_SELECTED_RE.finditer(text):
        recovered = int(mm.group(1))
    if recovered is None:
        for mm in PYTEST_COLLECTED_RE.finditer(text):
            recovered = int(mm.group(1))
    if ncollect is None and recovered is not None:
        ncollect = recovered
        v["verify_note"] = "n_collected recovered from pytest summary"
    if ncollect is not None:
        v["n_collected_verified"] = str(ncollect)

    # v1.2 states the collect-error count directly; v1.1 logs only imply it.
    n_err = None
    mm = NCOLLECT_ERRORS_RE.search(text)
    if mm:
        n_err = int(mm.group(1))
    else:
        for mm in PYTEST_COLLECT_ERRORS_RE.finditer(text):
            n_err = int(mm.group(1))
        if n_err is None:
            mm = PYTEST_INTERRUPTED_RE.search(text)
            if mm:
                n_err = int(mm.group(1))
    if n_err is not None:
        v["n_collect_errors"] = str(n_err)

    try:
        seconds_build = int(env.get("seconds_build") or 0)
    except ValueError:
        seconds_build = 0
    hit_ceiling = seconds_build >= TRIAGE_DOCKER_TIMEOUT_S - TIMEOUT_SLACK_S

    # --- the ladder of verified states -------------------------------------
    if env.get("status") == "CONFIG_ERROR":
        v.update(status_verified="RED", error_class_runner="CONFIG_ERROR")
        return v

    if env.get("error_class_v11") == "CLONE" or env.get("sha_resolved") == "none":
        v.update(status_verified="RED", error_class_runner="CLONE")
        return v

    if not seen["install_ok"]:
        # Build never completed. triage.sh's own classifier is the authority for
        # *why* -- it owns the v1.0/v1.1 regex vocabulary and its disagreement
        # rate is a reported number. The runner only confirms the outcome.
        v.update(status_verified="RED",
                 error_class_runner=env.get("error_class_v11") or "OTHER")
        return v

    # Install succeeded. Everything below is where v1.1's triage.sh stopped being
    # able to reach RED, so the runner has to.
    reached_collect = (seen["collect_ok"] or seen["collect_fail"]
                       or seen["collect_partial"])
    if not reached_collect:
        v.update(status_verified="RED")
        if hit_ceiling:
            v.update(error_class_runner="TIMEOUT",
                     verify_note=f"no collect marker; seconds_build="
                                 f"{seconds_build} at the 1800s container ceiling")
        else:
            # v1.2 also records docker_rc, which names the killer outright.
            rc = env.get("docker_rc", "")
            named = {"124": "TIMEOUT", "137": "OOM"}.get(rc)
            v.update(error_class_runner=named or "KILLED",
                     verify_note="install succeeded but no collect marker"
                                 + (f"; docker_rc={rc}" if rc else "")
                                 + ("" if named else
                                    ": container died (OOM is the usual cause)"))
        return v

    if seen["collect_partial"]:
        # v1.2's explicit partial state: some modules collected, some failed to
        # import, and the suite DID run. Verified on psf/black: 444 collected,
        # 1 optional-extra import error, 442 passed. Fall through to the
        # tests-ran ladder below so TESTS_RC decides GREEN/AMBER/OOM, and only
        # tag the partial collect.
        v["error_class_runner"] = "PARTIAL_COLLECT"
        v["verify_note"] = (
            (v["verify_note"] + "; " if v["verify_note"] else "")
            + f"{ncollect if ncollect is not None else '?'} collected despite "
              f"{v['n_collect_errors'] or '?'} import error(s)")
    elif seen["collect_fail"]:
        if ncollect and ncollect > 0:
            # v1.1's FALSE COLLECT_FAIL: the same situation as above, but the old
            # script aborted before running the suite and recorded no count. The
            # count is recovered from pytest's summary in the log tail.
            v.update(status_verified="AMBER",
                     error_class_runner="PARTIAL_COLLECT",
                     verify_note=(v["verify_note"] + "; " if v["verify_note"] else "")
                     + f"{ncollect} collected despite "
                       f"{v['n_collect_errors'] or '?'} import error(s); "
                       f"suite was NOT run (triage.sh v1.1 behaviour)")
            return v
        else:
            # Zero tests collected. triage.sh calls this AMBER; it is admissible
            # under amendment 2 but cannot satisfy ins2's >=1 test_suite
            # workload, so admission is decided in admit_verdict(), not here.
            v.update(status_verified="AMBER", error_class_runner="COLLECT_EMPTY",
                     verify_note="collect failed with 0 tests collected")
        return v

    # The suite ran. A partial collect is carried through as the error class
    # rather than being flattened to NONE -- a repo where some test modules never
    # imported is usable but not clean, and ins2 needs to know which modules it
    # cannot draw a workload from. A kill outranks it: those branches keep their
    # own class below.
    clean_class = "PARTIAL_COLLECT" if seen["collect_partial"] else "NONE"
    if tests_rc == 0:
        v.update(status_verified="GREEN", error_class_runner=clean_class)
    elif tests_rc == 137:
        # 128+9 = SIGKILL. On a memory-capped Docker VM this is the OOM killer.
        # ins1 v1.1 §6 has no rule for it (see ins1_v1.1_amendment_draft.md) and
        # triage.sh records it as an ordinary AMBER test failure.
        v.update(status_verified="RED", error_class_runner="OOM",
                 verify_note="TESTS_RC=137 = 128+SIGKILL: the suite was killed, "
                             "not failed. Timings and pass counts are invalid.")
    elif tests_rc == 124:
        v.update(status_verified="RED", error_class_runner="TIMEOUT",
                 verify_note="TESTS_RC=124 = timeout(1) killed the suite")
    elif tests_rc is None:
        v.update(status_verified="RED", error_class_runner="KILLED",
                 verify_note="collect ok but no TESTS_RC marker: killed mid-suite")
    else:
        v.update(status_verified="AMBER", error_class_runner=clean_class)
    return v


def admit_verdict(v: dict, env: dict) -> tuple[str, str]:
    """Corpus admission per MANIFEST §4 + amendment 2, computed explicitly.

    Amendment 2 admits AMBER because H2a needs repos that RUN, not repos that
    PASS. But two states currently wearing the AMBER label cannot produce an ins2
    workload at all, and admitting them would put repos in the corpus with no
    evidence a single test executes. They are excluded with a stated reason
    rather than silently, per the project's never-silently-drop rule.
    """
    status = v["status_verified"]
    if status not in ("GREEN", "GREEN_AFTER_FIX", "AMBER"):
        return "no", f"status_verified={status}/{v['error_class_runner']}"
    if v["error_class_runner"] == "COLLECT_EMPTY":
        return "no", "0 tests collected: cannot supply an ins2 test_suite workload"
    if env.get("lock_sha256") in ("", "none", None):
        # MANIFEST §3: all five identity components are mandatory. No lockfile,
        # no identity, not in the corpus.
        return "no", "no lock_sha256: identity 5-tuple incomplete (MANIFEST §3)"
    if not env.get("sha_resolved") or env["sha_resolved"] == "unknown":
        return "no", "no resolved sha: identity 5-tuple incomplete (MANIFEST §3)"
    return "yes", "-"


# ------------------------------------------------------------------- the attempt


def load_ladder(config: Path) -> tuple[str, dict[str, list[str]]]:
    cfg = json.loads(config.read_text())
    ladder = cfg.get("ladder") or {}
    default = ladder.get("default") or "3.12"
    rungs = {k: v for k, v in ladder.items() if not k.startswith("_") and k != "default"}
    return default, rungs


def run_triage(url: str, sha: str, pyver: str, env_extra: dict[str, str]) -> int:
    """One triage.sh invocation. Returns its exit code (or a synthetic one)."""
    env = dict(os.environ, **env_extra)
    try:
        p = subprocess.run([str(TRIAGE_SH), url, sha or "none", pyver],
                           capture_output=True, text=True,
                           timeout=ATTEMPT_TIMEOUT_S, env=env)
        return p.returncode
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 126


def triage_one(row: dict, default_py: str, rungs: dict[str, list[str]],
               root: Path, args) -> list[dict]:
    """Walk the ladder for one repo. Returns one ledger record per attempt.

    Sequential within a repo (a rung only exists because the previous one failed)
    and concurrent across repos, which is where the parallelism belongs: the
    container is the expensive part and it is one-per-attempt either way.
    """
    url = row["repo_url"]
    sha = row.get("sha") or "none"
    name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    records: list[dict] = []
    plan = [default_py]
    attempt_no = 0
    network_retried = False

    while plan:
        pyver = plan.pop(0)
        attempt_no += 1
        started = utcnow()
        rc = run_triage(url, sha, pyver, {})
        out_dir = root / "out" / name / f"py{pyver}"
        env = read_env_file(out_dir / "result.env")
        v = verify_attempt(env, out_dir / "attempt.log")
        admit, admit_reason = admit_verdict(v, env)

        rec = {
            "row_id": row.get("row_id", ""),
            "queue_position": row.get("queue_position", ""),
            "stratum": row.get("stratum", ""),
            "repo_url": url,
            "repo_name": name,
            "attempt": attempt_no,
            "pyver": pyver,
            "triage_rc": rc,
            "recorded_utc": started,
            # --- identity 5-tuple, MANIFEST §3 ---------------------------------
            "sha_requested": sha,
            "sha_resolved": env.get("sha_resolved", ""),
            "image_digest": env.get("image_digest", ""),
            "lock_sha256": env.get("lock_sha256", ""),
            "lock_pkgs": env.get("lock_pkgs", ""),
            # --- provenance ----------------------------------------------------
            "platform": env.get("platform", ""),
            "host_arch": env.get("host_arch", ""),
            "emulated": env.get("emulated", ""),
            "python_full": env.get("python_full", ""),
            "seconds_clone": env.get("seconds_clone", ""),
            "seconds_build": env.get("seconds_build", ""),
            "seconds_total": env.get("seconds_total", ""),
            # timings are only meaningful native and unmounted; MANIFEST §1.1
            "timings_valid": "no" if env.get("emulated") == "yes" else "yes",
            # --- triage.sh's verdict, recorded but not trusted -----------------
            "status_triage": env.get("status", ""),
            "result_line": env.get("result_line", ""),
            "error_class_v10": env.get("error_class_v10", ""),
            "error_class_v11": env.get("error_class_v11", ""),
            "classifier_disagree": env.get("classifier_disagree", ""),
            "n_collected_triage": env.get("n_collected", ""),
            # v1.2 only. The pre-deselection total: click collects 32965 and runs
            # 1965. Recorded because a repo that deselects 94% of its suite by
            # default is a different ins2 proposition from one that runs it all.
            "n_collected_total": env.get("n_collected_total", ""),
            "n_failing": env.get("n_failing", ""),
            # --- the runner's independent verdict ------------------------------
            **v,
            "verify_disagree": ("yes" if env.get("status")
                                and env["status"] != v["status_verified"] else "no"),
            "admit": admit,
            "admit_reason": admit_reason,
            "log_file": str(out_dir / "attempt.log"),
            "spec_version": SPEC_VERSION,
            "sheet_version": SHEET_VERSION,
        }
        records.append(rec)

        if v["status_verified"] in ("GREEN", "AMBER"):
            break

        # --- ins1 recipe ladder ------------------------------------------------
        cls = v["error_class_runner"]
        if cls == "NETWORK" and not network_retried:
            # A DNS blip should not burn a repo. One retry at the same rung,
            # recorded as its own attempt so the ledger stays honest.
            network_retried = True
            plan.insert(0, pyver)
            continue
        if attempt_no == 1 and cls in rungs:
            plan = list(rungs[cls])
        elif not plan:
            break

    if not args.keep_work:
        # triage.sh only cleans at the start of the NEXT run of the same repo, so
        # without this 558 full-history clones accumulate. Results live in
        # out/, never in work/, so this is safe once the ledger is written.
        shutil.rmtree(root / "work" / name, ignore_errors=True)
    return records


# ------------------------------------------------------------------ queue input


def load_queue(args) -> list[dict]:
    if args.repos_from:
        urls = [ln.strip() for ln in args.repos_from.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
        return [{"repo_url": u, "sha": "", "row_id": f"R{i:04d}",
                 "queue_position": i, "stratum": "REFERENCE"}
                for i, u in enumerate(urls, 1)]

    path = args.queue
    if not path or not path.exists():
        log(f"FATAL: no queue at {path}. Pass --queue or --repos-from.")
        return []
    if path.suffix == ".jsonl":
        rows = read_jsonl(path)
    else:
        with path.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
    queued = [r for r in rows
              if (r.get("excluded_reason") or "none") == "none"
              and str(r.get("queue_position") or "").strip()]
    queued.sort(key=lambda r: int(r["queue_position"]))
    return queued


def detect_arch() -> str:
    try:
        p = subprocess.run(["docker", "version", "--format", "{{.Server.Arch}}"],
                           capture_output=True, text=True, timeout=30)
        return p.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------------------------------------------------------------------- stage run


def stage_run(args) -> int:
    root = args.data
    ledger = root / "triage" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)

    if not TRIAGE_SH.exists():
        log(f"FATAL: {TRIAGE_SH} not found")
        return 3

    queue = load_queue(args)
    if not queue:
        return 2

    default_py, rungs = load_ladder(args.config)

    prior = read_jsonl(ledger)
    # A repo is done when one of its attempts reached a terminal verified state.
    # Attempt-level granularity means a crash mid-ladder resumes at the right rung
    # instead of re-running the rungs that already answered.
    done_terminal = {r["repo_url"] for r in prior
                     if r.get("status_verified") in ("GREEN", "AMBER")}
    done_exhausted: dict[str, int] = {}
    for r in prior:
        if r.get("status_verified") not in ("GREEN", "AMBER"):
            done_exhausted[r["repo_url"]] = max(
                done_exhausted.get(r["repo_url"], 0), int(r.get("attempt") or 1))
    # Exhausted = tried the default rung plus every rung its error class offers.
    max_rungs = 1 + max((len(v) for v in rungs.values()), default=0)
    done = done_terminal | {u for u, n in done_exhausted.items() if n >= max_rungs}

    todo = [r for r in queue if r["repo_url"] not in done] if args.resume else queue
    if args.limit:
        todo = todo[: args.limit]

    arch = detect_arch()
    log(f"[run] host_arch={arch}  ladder default=py{default_py}  "
        f"rungs={ {k: v for k, v in rungs.items()} }")
    log(f"[run] {len(queue)} queued, {len(done)} already terminal, {len(todo)} to run")
    if args.limit:
        log(f"[run] --limit {args.limit}: this is a PREFIX, not a sample. "
            f"Amendment 3 interleaving means it still carries all three strata.")

    # MANIFEST: "one corpus, one architecture." Repos with compiled extensions can
    # resolve different wheels and therefore a different lock_sha256, which is part
    # of repo identity -- so mixing architectures silently forks the corpus.
    prior_arches = {r.get("host_arch") for r in prior if r.get("host_arch")}
    if prior_arches and arch not in prior_arches and not args.allow_mixed_arch:
        log(f"FATAL: ledger was built on {sorted(prior_arches)}, this host is "
            f"{arch}. lock_sha256 is part of repo identity (MANIFEST §3) and "
            f"compiled-extension repos resolve different wheels per platform.")
        log("       Re-triage on one architecture, or pass --allow-mixed-arch "
            "and accept that the corpus is forked.")
        return 3

    by_stratum: dict[str, int] = {}
    for r in todo:
        by_stratum[r.get("stratum", "?")] = by_stratum.get(r.get("stratum", "?"), 0) + 1
    log(f"[run] to run by stratum: {dict(sorted(by_stratum.items()))}")

    if args.dry_run:
        log("[run] --dry-run: no containers, no clones. Queue validation only.")
        bad_sha = [r for r in todo if not (r.get("sha") or "").strip()]
        names: dict[str, list[str]] = {}
        for r in todo:
            n = r["repo_url"].rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
            names.setdefault(n, []).append(r["repo_url"])
        collide = {k: v for k, v in names.items() if len(v) > 1}
        log(f"       rows missing sha: {len(bad_sha)} "
            f"(MANIFEST §3 forbids an empty sha; triage.sh resolves HEAD)")
        log(f"       basename collisions: {len(collide)} "
            f"(triage.sh keys work/ and out/ on basename alone)")
        for k, v in list(collide.items())[:10]:
            log(f"         {k}: {v}")
        for r in todo[:5]:
            log(f"       would run: py{default_py}  {r['repo_url']}  "
                f"sha={(r.get('sha') or 'none')[:12]}")
        log(f"       ... {len(todo)} total")
        return 0

    lock = threading.Lock()
    n_done = 0
    counts: dict[str, int] = {}

    def append(records: list[dict]) -> None:
        """Durable before anything else happens. One flush per repo."""
        with lock:
            with ledger.open("a") as fh:
                for rec in records:
                    fh.write(json.dumps(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futs = {pool.submit(triage_one, r, default_py, rungs, root, args): r
                    for r in todo}
            for fut in as_completed(futs):
                row = futs[fut]
                try:
                    records = fut.result()
                except Exception as e:  # noqa: BLE001 -- never lose a worker
                    records = [{
                        "repo_url": row["repo_url"],
                        "row_id": row.get("row_id", ""),
                        "queue_position": row.get("queue_position", ""),
                        "stratum": row.get("stratum", ""),
                        "attempt": 1,
                        "status_verified": "RED",
                        "error_class_runner": f"RUNNER_{type(e).__name__}",
                        "verify_note": str(e)[:300],
                        "admit": "no",
                        "admit_reason": "runner exception",
                        "recorded_utc": utcnow(),
                    }]
                append(records)
                final = records[-1]
                with lock:
                    n_done += 1
                    key = f"{final['status_verified']}/{final['error_class_runner']}"
                    counts[key] = counts.get(key, 0) + 1
                    if final.get("verify_disagree") == "yes":
                        log(f"  ! verify_disagree {final['repo_url']}: "
                            f"triage={final.get('status_triage')} "
                            f"runner={final['status_verified']}"
                            f"/{final['error_class_runner']}")
                    if final.get("emulated") == "yes":
                        log(f"  ! EMULATED {final['repo_url']}: timings invalid")
                    if n_done % 10 == 0 or n_done == len(todo):
                        log(f"  [{n_done}/{len(todo)}] {dict(sorted(counts.items()))}")
    except KeyboardInterrupt:
        log(f"[run] interrupted after {n_done}; ledger is durable, "
            f"re-run to resume from {ledger}")
        return 1

    log(f"[run] {n_done} repos -> {ledger}")
    for k, n in sorted(counts.items()):
        log(f"       {k}: {n}")
    return stage_report(args)


# ------------------------------------------------------------------- stage report


def stage_report(args) -> int:
    ledger = args.data / "triage" / "ledger.jsonl"
    rows = read_jsonl(ledger)
    if not rows:
        log(f"[report] no ledger at {ledger}")
        return 2

    # One record per repo: its last attempt is its outcome.
    final: dict[str, dict] = {}
    for r in rows:
        u = r.get("repo_url")
        if not u:
            continue
        if u not in final or int(r.get("attempt") or 1) >= int(final[u].get("attempt") or 1):
            final[u] = r

    log(f"[report] {len(final)} repos, {len(rows)} attempts")
    log("")

    log("[report] verified status:")
    st: dict[str, int] = {}
    for r in final.values():
        k = f"{r.get('status_verified')}/{r.get('error_class_runner')}"
        st[k] = st.get(k, 0) + 1
    for k, n in sorted(st.items(), key=lambda x: -x[1]):
        log(f"         {k:<28} {n}")
    log("")

    disagree = [r for r in final.values() if r.get("verify_disagree") == "yes"]
    log(f"[report] triage.sh vs runner disagreement: {len(disagree)}/{len(final)}"
        f" ({len(disagree) / max(1, len(final)) * 100:.1f}%) — reportable, not a bug to hide")
    dk: dict[str, int] = {}
    for r in disagree:
        k = f"{r.get('status_triage')} -> {r.get('status_verified')}/{r.get('error_class_runner')}"
        dk[k] = dk.get(k, 0) + 1
    for k, n in sorted(dk.items(), key=lambda x: -x[1]):
        log(f"         {k:<48} {n}")
    log("")

    emul = [r for r in final.values() if r.get("emulated") == "yes"]
    if emul:
        log(f"[report] WARNING: {len(emul)} repos ran EMULATED. Correctness usable, "
            f"ALL TIMINGS INVALID (MANIFEST §1.1). Never publish overhead from these.")
        log("")

    admitted = [r for r in final.values() if r.get("admit") == "yes"]
    log(f"[report] corpus-admissible (MANIFEST §4 + amendment 2): "
        f"{len(admitted)}/{len(final)}")
    rej: dict[str, int] = {}
    for r in final.values():
        if r.get("admit") != "yes":
            rej[r.get("admit_reason", "?")] = rej.get(r.get("admit_reason", "?"), 0) + 1
    for k, n in sorted(rej.items(), key=lambda x: -x[1]):
        log(f"         rejected: {k[:64]:<64} {n}")
    log("")

    log("[report] green-build floor is MANIFEST §4: ~120 target / 60 floor")
    green = sum(1 for r in admitted if r.get("status_verified") == "GREEN")
    log(f"         GREEN {green}   AMBER {len(admitted) - green}   "
        f"admissible total {len(admitted)}")
    log("")

    # A --repos-from run (e.g. the frozen reference set) carries no stratum, so the
    # §4 table would report every floor as unmet and mean nothing by it.
    if any(r.get("stratum") in ("LOW", "MED", "HIGH") for r in final.values()):
        log("[report] per-stratum, against MANIFEST §4 floors:")
        log("         (floors are on repos with >=3 ins2 workloads, which is DOWNSTREAM")
        log("          of this table — these counts are the pool ins2 draws from.)")
        for s in ("LOW", "MED", "HIGH"):
            n_all = sum(1 for r in final.values() if r.get("stratum") == s)
            n_ok = sum(1 for r in admitted if r.get("stratum") == s)
            floor, target = STRATUM_FLOOR[s], STRATUM_TARGET[s]
            surv = n_ok / n_all * 100 if n_all else 0.0
            verdict = ("OK" if n_ok >= target
                       else "above floor" if n_ok >= floor else "BELOW FLOOR")
            log(f"         {s:<4} triaged {n_all:>4}  admissible {n_ok:>4} "
                f"({surv:5.1f}%)  floor {floor:>2} target {target:>2}  {verdict}")
            if s == "LOW" and n_ok < floor:
                log("              LOW is the H2b-lite placebo arm. MANIFEST §4: "
                    "this floor is NOT negotiable and is the last thing cut.")
    else:
        log("[report] no stratified repos in the ledger — skipping the MANIFEST §4 "
            "floor table (this looks like a --repos-from validation run).")

    csv_out = args.data / "triage" / "triage_results.csv"
    cols = ["row_id", "queue_position", "stratum", "repo_url", "attempt", "pyver",
            "status_triage", "status_verified", "error_class_runner",
            "verify_disagree", "admit", "admit_reason", "sha_resolved",
            "image_digest", "lock_sha256", "python_full", "n_collected_verified",
            "n_collected_total", "n_collect_errors", "tests_rc", "n_failing",
            "platform", "host_arch",
            "emulated", "timings_valid", "seconds_total", "log_file", "verify_note"]
    with csv_out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(final.values(),
                        key=lambda r: int(r.get("queue_position") or 0)):
            w.writerow(r)
    log("")
    log(f"[report] {csv_out}")
    return 0


# ---------------------------------------------------------------------- driver


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["run", "report"])
    ap.add_argument("--data", type=Path,
                    default=Path(os.environ.get("TW_DATA",
                                                Path.home() / "traceweave-data")),
                    help="$TW_DATA. MANIFEST §1.1: must live under $HOME — "
                         "Docker Desktop refuses to bind-mount /tmp")
    ap.add_argument("--queue", type=Path,
                    help="03_queue.csv or .jsonl from discover_candidates.py")
    ap.add_argument("--repos-from", type=Path,
                    help="plain list of repo URLs, e.g. config/reference_repos.txt")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--jobs", type=int, default=4,
                    help="concurrent repos. Each is a container running a test "
                         "suite; OOM shows up as TESTS_RC=137, so raise this only "
                         "with RAM to match")
    ap.add_argument("--limit", type=int,
                    help="run only the first N of the queue (a prefix, not a sample)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate the queue and print the plan; no docker")
    ap.add_argument("--keep-work", action="store_true",
                    help="do not delete each clone after its result is durable")
    ap.add_argument("--allow-mixed-arch", action="store_true",
                    help="append to a ledger built on another architecture. "
                         "Forks the corpus; see MANIFEST 'one corpus, one architecture'")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    args = ap.parse_args()

    if args.stage == "run":
        return stage_run(args)
    return stage_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
