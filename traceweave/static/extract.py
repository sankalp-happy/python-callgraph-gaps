#!/usr/bin/env python3
"""Static extraction over the corpus: both baselines, one repo at a time.

Phase 1 §1.2's driver. `pycg_baseline.py` and `pyright_baseline.py` are the
atoms -- ONE repo, ONE tool. This is the loop around them, and it takes the
same posture `triage/runner.py` takes toward `triage.sh`:

  checkpoint  every repo's record is appended to the ledger the moment it is
              durable. Static extraction over 60 repos is hours of work and a
              crash must never cost more than the repo in flight.
  clone       triage deletes its working copy once its result is durable
              (runner.py's `reclaim`), so the source is not lying around. Each
              repo is re-cloned at the EXACT `sha_resolved` triage recorded, so
              S is extracted from the same commit the corpus is pinned to.
  compare     the two baselines are diffed against each other per repo. §1.2:
              "if they disagree materially, that disagreement is itself a
              finding worth a paragraph." The number is computed here so the
              paragraph has something to cite.
  refuse      a repo whose ledger row came from another architecture is not
              silently mixed in (MANIFEST §1, "one corpus, one architecture").

### What is analysed, and what is deliberately not

By default only the repo's own package code -- not `tests/`. A test function
that calls into the library is a real caller, but it is a caller the static
graph of the library cannot contain, so counting those edges as missed would be
free credit. The demo hit exactly this and held out 153 entry edges for the
same reason. `--include-tests` widens the universe when that is wanted; the
choice is recorded in every artifact as `include_tests`, because it moves the
denominator.

Usage:
    # the reference set, on the manager host (development output)
    python3 extract.py run --repos-from ../config/reference_repos.txt

    # the corpus, on the execution host, from triage's own ledger
    python3 extract.py run --from-triage ~/traceweave-data/triage/ledger.jsonl

    python3 extract.py report          # per-repo table + baseline agreement

Stdlib only. Exit codes: 0 ok, 2 bad args / missing input, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pycg_baseline
import pyright_baseline
from callsites import CALLSITE_VERSION, analyse_repo, counts as callsite_counts
from nodes import DEFAULT_EXCLUDE_DIRS, INVENTORY_VERSION, inventory_repo

SPEC_VERSION = "1.0"
EXTRACT_VERSION = "1.0"
HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path.home() / "traceweave-data"

# Top-level directories that are not the library under analysis. `tests` is in
# this list by default -- see the module docstring; `--include-tests` drops it.
NON_LIBRARY_TOP = frozenset({
    "tests", "test", "testing", "docs", "doc", "examples", "example", "bench",
    "benchmarks", "scripts", "tools", "ci", "contrib", "sample", "samples",
    # A top-level importable package named exactly `t` is the celery/kombu
    # family's test package, never a library. Without this, celery's node set
    # gains its whole test tree while every other repo's does not -- and the
    # `include_tests` flag in the artifact would then be lying.
    "t",
})


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", file=sys.stderr)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            log(f"WARN: malformed ledger line in {path.name}, skipping")
    return out


# --------------------------------------------------------------------------
# Layout detection
# --------------------------------------------------------------------------

def detect_layout(repo: Path, include_tests: bool = False) -> dict:
    """Where the library's source lives, as a fact about the checkout.

    Guessing wrong here is not a cosmetic error: PyCG's import root decides
    every name it emits, so a wrong root produces a graph whose names cannot be
    mapped and a spuriously enormous miss rate. So the guess is recorded in the
    artifact (`layout`) and the file count is recorded with it, which makes a
    bad guess visible as "3 modules analysed in a 400-module repo".
    """
    skip = set(DEFAULT_EXCLUDE_DIRS) | (set() if include_tests else NON_LIBRARY_TOP)

    def packages_in(parent: Path) -> list[Path]:
        if not parent.is_dir():
            return []
        return [p for p in sorted(parent.iterdir())
                if p.is_dir() and p.name not in skip and (p / "__init__.py").exists()]

    src = repo / "src"
    if src.is_dir():
        pkgs = packages_in(src)
        if pkgs:
            return {"layout": "src", "src_root": "src",
                    "packages": [str(p.relative_to(repo)) for p in pkgs]}
        if list(src.glob("*.py")):
            return {"layout": "src-flat", "src_root": "src", "packages": ["src"]}

    # A real top-level package wins over `lib/` and `python/`, which some repos
    # also use for vendored code. Checked in this order so a repo with both is
    # not misdetected.
    pkgs = packages_in(repo)
    if pkgs:
        return {"layout": "flat", "src_root": ".",
                "packages": [str(p.relative_to(repo)) for p in pkgs]}

    # ansible ships its package as `lib/ansible`, and without this it was
    # recorded `no_python_package_found` -- a 5000-module repo silently skipped
    # by a layout guess, which is the failure mode `detect_layout`'s docstring
    # warns about. Caught by running the reference set through run_corpus.sh.
    for root in ("lib", "python"):
        pkgs = packages_in(repo / root)
        if pkgs:
            return {"layout": root, "src_root": root,
                    "packages": [str(p.relative_to(repo)) for p in pkgs]}

    modules = [p for p in sorted(repo.glob("*.py")) if p.name != "setup.py"]
    if modules:
        return {"layout": "single-module", "src_root": ".", "packages": ["."]}
    return {"layout": "unknown", "src_root": ".", "packages": []}


# --------------------------------------------------------------------------
# Clone
# --------------------------------------------------------------------------

def clone_at_sha(url: str, sha: str, dest: Path, timeout: int = 900) -> dict:
    """Full clone, then checkout the exact sha.

    Not `--depth 1`: the sha triage recorded is usually not the tip by the time
    extraction runs, and a shallow clone cannot reach it. runner.py made the
    same call for the same reason.
    """
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    clone = subprocess.run(["git", "clone", "--quiet", url, str(dest)],
                           capture_output=True, text=True, timeout=timeout)
    if clone.returncode != 0:
        return {"status": "clone_failed", "detail": clone.stderr.strip()[-400:]}
    if sha:
        co = subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", sha],
                            capture_output=True, text=True, timeout=timeout)
        if co.returncode != 0:
            return {"status": "checkout_failed", "detail": co.stderr.strip()[-400:],
                    "sha": sha}
    resolved = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    return {"status": "ok", "sha_resolved": resolved,
            "seconds_clone": round(time.time() - started, 1)}


# --------------------------------------------------------------------------
# One repo
# --------------------------------------------------------------------------

def compare_baselines(pycg_edges: set, pyright_edges: set) -> dict:
    """§1.2's "if they disagree materially" number, per repo.

    Deliberately symmetric and reported both ways: neither baseline is the
    reference for the other. The reference set does not exist until Phase 2.
    """
    both = pycg_edges & pyright_edges
    union = pycg_edges | pyright_edges
    return {
        "pycg_only": len(pycg_edges - pyright_edges),
        "pyright_only": len(pyright_edges - pycg_edges),
        "agreed": len(both),
        "union": len(union),
        "jaccard": round(len(both) / len(union), 4) if union else None,
    }


def extract_repo(repo: Path, out_dir: Path, layout: dict, args,
                 include_tests: bool) -> dict:
    exclude_names = {n for n in (args.exclude or "").split(",") if n}
    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | (
        set() if include_tests else NON_LIBRARY_TOP)
    package_dirs = [repo / p for p in layout["packages"]]
    src_root = repo / layout["src_root"]

    out_dir.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "layout": layout["layout"],
        "src_root": layout["src_root"],
        "packages": layout["packages"],
        "include_tests": include_tests,
    }

    inv = inventory_repo(repo, package_dirs, src_root, exclude_names, exclude_dirs)
    if not inv.modules:
        record["status"] = "no_modules"
        return record
    sites, index = analyse_repo(inv)
    write_json(out_dir / "inventory.json", {
        "inventory_version": INVENTORY_VERSION, "spec_version": SPEC_VERSION,
        "counts": inv.counts(), "parse_failures": inv.parse_failures,
        "nodes": [n.to_json() for n in inv.nodes],
    })
    write_json(out_dir / "callsites.json", {
        "callsite_version": CALLSITE_VERSION, "spec_version": SPEC_VERSION,
        "counts": callsite_counts(sites),
        "call_sites": [s.to_json() for s in sites],
    })
    record["inventory"] = inv.counts()
    record["callsites"] = callsite_counts(sites)

    # -- baseline 1: PyCG ------------------------------------------------
    rel_files = [m.relative_path for m in inv.modules]
    if args.skip_pycg:
        record["pycg"] = {"status": "skipped"}
        pycg_set: set = set()
    else:
        runs = [pycg_baseline.run_pycg(repo, rel_files, layout["src_root"], seed,
                                       args.image, args.pycg_memory, args.pycg_timeout)
                for seed in args.seeds.split(",") if seed]
        graph, spread = pycg_baseline.union_graphs(runs)
        edges, diagnostics = pycg_baseline.normalize(graph, inv)
        write_json(out_dir / "pycg.json", {
            "baseline": "pycg", "tool_pin": pycg_baseline.TOOL_PIN,
            "spec_version": SPEC_VERSION, "run": spread,
            "diagnostics": diagnostics, "edges": edges.to_json(),
        })
        pycg_set = set(edges.in_universe)
        record["pycg"] = {
            "status": "ok" if spread.get("seeds_completed") else "all_runs_failed",
            "in_universe": len(pycg_set),
            "seeds_completed": spread.get("seeds_completed"),
            "deterministic_across_seeds": spread.get("deterministic_across_seeds"),
            "unmapped_names": diagnostics["name_outcomes"]["unmapped"],
            "namespace_merged": diagnostics["name_outcomes"]["namespace_merged"],
        }

    # -- baseline 2: Pyright-assisted ------------------------------------
    if args.skip_pyright:
        record["pyright"] = {"status": "skipped"}
        pyright_set: set = set()
    else:
        work = out_dir / "pyright_work"
        edges2, diag2 = pyright_baseline.extract(
            repo, inv, sites, index, work, image=args.image,
            site_packages=args.site_packages, chunk=args.chunk,
            request_timeout=args.request_timeout,
            ready_timeout=args.ready_timeout, probe_timeout=args.pyright_timeout,
            stream_progress=not args.quiet)
        write_json(out_dir / "pyright.json", {
            "baseline": "pyright", "tool_pin": pyright_baseline.TOOL_PIN,
            "spec_version": SPEC_VERSION, "diagnostics": diag2,
            "edges": edges2.to_json(),
        })
        shutil.rmtree(work, ignore_errors=True)
        pyright_set = set(edges2.in_universe)
        record["pyright"] = {
            "status": diag2.get("probe_status", "?"),
            "in_universe": len(pyright_set),
            "server_restarts": diag2.get("server_restarts"),
            "files_unready": diag2.get("files_unready"),
            "unresolved_call_sites": sum(diag2.get("unresolved_by_edge_type", {}).values()),
        }
        record["unresolved_by_edge_type"] = diag2.get("unresolved_by_edge_type", {})

    if pycg_set or pyright_set:
        record["baseline_comparison"] = compare_baselines(pycg_set, pyright_set)

    # A repo where one baseline died is NOT done. `status: ok` would mark it
    # complete and the resume logic would never come back to it -- so a PyCG OOM
    # on a big machine's second attempt would be lost, and the paper would
    # silently report S for one tool on some repos and two on others.
    failed = [name for name in ("pycg", "pyright")
              if record.get(name, {}).get("status") not in ("ok", "skipped")]
    record["baselines_failed"] = failed
    record["status"] = "ok" if not failed else "partial"
    return record


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------

def targets_from_triage(ledger: Path, host_arch: str,
                        include_survey_only: bool = False) -> list[dict]:
    """Corpus-admitted repos from triage's ledger, latest attempt per repo.

    Two filters, both deliberate:

    Architecture. Rows from another host are refused rather than mixed:
    MANIFEST §1 makes architecture part of a repo's identity, and a mixed ledger
    is exactly what runner.py already refuses to append to.

    Redistribution. MANIFEST §7's gate (decided 2026-08-17) admits `pass` and
    holds `pending` for the ins3 Part 1-R licence review. Both are extracted:
    `pending` is "nobody has read the licence yet", and a repo that becomes
    eligible next week should not need a second hours-long extraction run.
    `survey-only` repos (GPL/LGPL/MPL, archived) are skipped by default --
    the feasibility survey reports their TRIAGE outcome and never needs their
    call graph -- and `--include-survey-only` overrides that.
    """
    rows = read_jsonl(ledger)
    if not rows:
        return []
    arches = {norm_arch(r.get("host_arch", "")) for r in rows if r.get("host_arch")}
    foreign = arches - {host_arch}
    if foreign and arches - foreign == set():
        log(f"FATAL: ledger was built on {sorted(arches)}, this host is "
            f"{host_arch}. MANIFEST §1: one corpus, one architecture.")
        raise SystemExit(3)
    wanted = {"yes", "pending"} | ({"no"} if include_survey_only else set())
    latest: dict[str, dict] = {}
    skipped_survey = 0
    for row in rows:
        if row.get("admit") != "yes":
            continue
        if row.get("host_arch") and norm_arch(row["host_arch"]) != host_arch:
            continue
        # A ledger written before the gate existed has no `corpus_eligible`;
        # treat it as eligible rather than silently extracting nothing.
        eligible = row.get("corpus_eligible", "yes")
        if eligible not in wanted:
            skipped_survey += 1
            continue
        latest[row["repo_url"]] = row
    if skipped_survey:
        log(f"[run] skipping {skipped_survey} survey-only repos (MANIFEST §7 "
            f"redistribution gate); --include-survey-only extracts them too")
    return [
        {"repo_url": r["repo_url"], "repo_name": r.get("repo_name", ""),
         "sha": r.get("sha_resolved", ""), "stratum": r.get("stratum", ""),
         "pyver": r.get("pyver", ""), "row_id": r.get("row_id", ""),
         "corpus_eligible": r.get("corpus_eligible", "yes")}
        for r in latest.values()
    ]


def targets_from_file(path: Path) -> list[dict]:
    """`repo_url [sha]` per line; `#` comments ignored."""
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        url = parts[0]
        out.append({"repo_url": url, "repo_name": url.rstrip("/").split("/")[-1],
                    "sha": parts[1] if len(parts) > 1 else "",
                    "stratum": "", "pyver": "", "row_id": ""})
    return out


# Docker reports amd64/arm64; platform.machine() reports x86_64/aarch64. The
# triage ledger records Docker's spelling (runner.py detect_arch uses
# `docker version --format {{.Server.Arch}}`), so both sides are normalised
# before comparison. Without this, MANIFEST §1's guard fires on a corpus that
# is in fact single-architecture, and the per-repo filter in
# targets_from_triage silently skips every row -- a zero-repo run that looks
# like a success.
_ARCH_ALIASES = {"x86_64": "amd64", "amd64": "amd64",
                 "aarch64": "arm64", "arm64": "arm64"}


def norm_arch(a: str) -> str:
    a = (a or "").strip().lower()
    return _ARCH_ALIASES.get(a, a)


def host_arch() -> str:
    import platform
    return norm_arch(platform.machine())


def cmd_run(args) -> int:
    data = args.data.expanduser()
    static_root = data / "static"
    ledger = static_root / "ledger.jsonl"
    static_root.mkdir(parents=True, exist_ok=True)

    if args.from_triage:
        targets = targets_from_triage(args.from_triage.expanduser(), host_arch(),
                                      args.include_survey_only)
    elif args.repos_from:
        targets = targets_from_file(args.repos_from.expanduser())
    else:
        log("FATAL: one of --from-triage or --repos-from is required")
        return 2
    if not targets:
        log("no targets: nothing admitted, or an empty list")
        return 2
    if args.limit:
        targets = targets[: args.limit]

    done = {r["repo_url"] for r in read_jsonl(ledger)
            if r.get("status") == "ok"} if not args.force else set()
    todo = [t for t in targets if t["repo_url"] not in done]
    if args.shard:
        # i/n: split the REMAINING work n ways, deterministically. Round-robin
        # over repo_url-sorted order rather than contiguous blocks, so the slow
        # repos (a PyCG timeout costs ~90 min) spread evenly instead of piling
        # into one shard. Each shard needs its own --data dir; merge the
        # ledgers afterwards (run_corpus.sh header). Applied after the `done`
        # filter so the split is even in work, not in nominal repo count.
        try:
            i, n = (int(x) for x in str(args.shard).split("/"))
        except ValueError:
            log(f"FATAL: --shard {args.shard!r}: expected the form i/n, e.g. 1/3")
            return 2
        if not 1 <= i <= n:
            log(f"FATAL: --shard {args.shard}: need 1 <= i <= n")
            return 2
        # Deal most-expensive-first rather than by name. A repo already known
        # to cost ~90 min (PyCG timing out on every seed) must not land three
        # deep in one shard while another gets none -- wall clock is the
        # slowest shard, not the average. Cost comes from any prior attempt in
        # this ledger; unseen repos sort as 0 and spread round-robin.
        cost: dict[str, float] = {}
        for r in read_jsonl(ledger):
            u = r.get("repo_url")
            if not u:
                continue
            try:
                sec = float(r.get("seconds_total") or 0)
            except (TypeError, ValueError):
                sec = 0.0
            cost[u] = max(cost.get(u, 0.0), sec)
        ordered = sorted(todo, key=lambda t: (-cost.get(t["repo_url"], 0.0),
                                              t["repo_url"]))
        todo = [t for k, t in enumerate(ordered) if k % n == i - 1]
        log(f"[run] --shard {i}/{n}: this copy takes {len(todo)} of the "
            f"remaining repos")
    log(f"[run] {len(todo)} repos to extract ({len(targets) - len(todo)} already "
        f"in {ledger.name} or another shard), image={args.image}")

    if args.dry_run:
        for t in todo:
            log(f"  would extract {t['repo_name']} @ {t['sha'][:8] or 'HEAD'}")
        return 0

    provenance = read_provenance(args.image)
    check_docker_memory(args.pycg_memory)
    work_root = data / "static-work"
    n_ok = 0
    for i, target in enumerate(todo, 1):
        name = target["repo_name"] or target["repo_url"].rstrip("/").split("/")[-1]
        log(f"[{i}/{len(todo)}] {name}")
        out_dir = static_root / name
        repo_dir = (Path(args.clone_dir).expanduser() / name if args.clone_dir
                    else work_root / name)
        record = {
            "repo_url": target["repo_url"], "repo_name": name,
            "row_id": target.get("row_id", ""), "stratum": target.get("stratum", ""),
            "sha_requested": target.get("sha", ""),
            "corpus_eligible": target.get("corpus_eligible", ""),
            "recorded_utc": now_utc(), "host_arch": host_arch(),
            "extract_version": EXTRACT_VERSION, "spec_version": SPEC_VERSION,
            "image": args.image, "image_provenance": provenance,
        }
        started = time.time()
        try:
            if args.clone_dir and repo_dir.exists():
                record["clone"] = {"status": "reused", "path": str(repo_dir)}
            else:
                record["clone"] = clone_at_sha(target["repo_url"], target["sha"],
                                               repo_dir, args.clone_timeout)
            if record["clone"]["status"] != "ok" and record["clone"]["status"] != "reused":
                record["status"] = record["clone"]["status"]
            else:
                layout = detect_layout(repo_dir, args.include_tests)
                if not layout["packages"]:
                    record["status"] = "no_python_package_found"
                    record["layout"] = layout["layout"]
                else:
                    record.update(extract_repo(repo_dir, out_dir, layout, args,
                                               args.include_tests))
        except KeyboardInterrupt:
            log("[run] interrupted; the ledger is durable, re-run to resume")
            return 1
        except Exception as exc:  # noqa: BLE001 - one repo must not end the run
            record["status"] = "extract_exception"
            record["detail"] = f"{type(exc).__name__}: {exc}"
        record["seconds_total"] = round(time.time() - started, 1)

        with ledger.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        if out_dir.exists():
            write_json(out_dir / "summary.json", record)
        if record.get("status") == "ok":
            n_ok += 1
            log(f"      pycg={record['pycg'].get('in_universe')} "
                f"pyright={record['pyright'].get('in_universe')} "
                f"jaccard={record.get('baseline_comparison', {}).get('jaccard')} "
                f"in {record['seconds_total']}s")
        else:
            detail = record.get("detail") or ",".join(record.get("baselines_failed", []))
            log(f"      {record.get('status')}: {detail}")
        # Reclaim, like runner.py: 60 full clones is tens of GB, and the Mac has
        # 18 GB free (MIGRATION.md §4).
        if not args.keep_clones and not args.clone_dir:
            shutil.rmtree(repo_dir, ignore_errors=True)

    log(f"[run] {n_ok}/{len(todo)} extracted -> {ledger}")
    return 0


def check_docker_memory(requested: str) -> None:
    """Warn when `--pycg-memory` exceeds what the daemon can actually give.

    Worth its own check because the symptom is so misleading: a `--memory=8g`
    container on a 3.8 GB Docker Desktop VM is killed at ~3.8 GB and reports
    `exit 137`, which reads as "PyCG needs more than 8 GB" when it means "this
    host never had 8 GB to give". MIGRATION.md §4 is the reason the two hosts
    differ this much (Mac 8 GB / VM 3.83 GB, Linux box 38 GB).
    """
    units = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    text = requested.strip().lower()
    want = int(float(text[:-1]) * units[text[-1]]) if text[-1] in units else int(text)
    try:
        out = subprocess.run(["docker", "info", "--format", "{{.MemTotal}}"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        have = int(out)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        return
    if have and want > have:
        log(f"WARN: --pycg-memory={requested} exceeds the daemon's "
            f"{round(have / 1024 ** 3, 2)} GB. A PyCG OOM on this host means "
            f"'this machine is too small', not 'PyCG needs more than {requested}'.")


def read_provenance(image: str) -> dict:
    path = HERE / "image_provenance.json"
    if not path.exists():
        return {"warning": "no image_provenance.json -- run ./build_image.sh"}
    payload = json.loads(path.read_text())
    return {"image_id": payload.get("image_id"), "base_image": payload.get("base_image"),
            "platform": payload.get("platform"), "inside": payload.get("inside")}


def cmd_report(args) -> int:
    ledger = args.data.expanduser() / "static" / "ledger.jsonl"
    rows = read_jsonl(ledger)
    if not rows:
        log(f"[report] no ledger at {ledger}")
        return 2
    latest = {r["repo_url"]: r for r in rows}
    ok = [r for r in latest.values() if r.get("status") == "ok"]
    log(f"[report] {len(ok)}/{len(latest)} repos extracted")

    print(f"{'repo':<24} {'stratum':<7} {'nodes':>6} {'sites':>6} {'pycg':>6} "
          f"{'pyright':>7} {'jacc':>6} {'unres':>6}")
    for r in sorted(latest.values(), key=lambda r: r.get("repo_name", "")):
        # A `partial` repo still has real numbers for whatever succeeded; print
        # them, flagged, rather than a row of dashes that hides the work done.
        if "inventory" not in r:
            print(f"{r.get('repo_name', '?'):<24} {r.get('stratum', ''):<7} "
                  f"{'-':>6} {'-':>6} {'-':>6} {'-':>7} {'-':>6}  {r.get('status')}")
            continue
        cmp_ = r.get("baseline_comparison", {})
        flag = "" if r.get("status") == "ok" else \
            f"  PARTIAL({','.join(r.get('baselines_failed', []))})"
        print(f"{r['repo_name']:<24} {r.get('stratum', ''):<7} "
              f"{r['inventory']['callable_nodes']:>6} "
              f"{r['callsites']['call_sites']:>6} "
              f"{r['pycg'].get('in_universe', '-'):>6} "
              f"{r['pyright'].get('in_universe', '-'):>7} "
              f"{cmp_.get('jaccard', '-'):>6} "
              f"{r['pyright'].get('unresolved_call_sites', '-'):>6}{flag}")

    if ok:
        # The §1.2 disagreement number, aggregated. Reported with the per-repo
        # spread, never as a lone mean (metric spec §4.1's discipline).
        jaccards = [r["baseline_comparison"]["jaccard"] for r in ok
                    if r.get("baseline_comparison", {}).get("jaccard") is not None]
        if jaccards:
            print(f"\nbaseline agreement (Jaccard on in-universe edges): "
                  f"min {min(jaccards)} / median "
                  f"{sorted(jaccards)[len(jaccards) // 2]} / max {max(jaccards)} "
                  f"over {len(jaccards)} repos")
        nondet = [r["repo_name"] for r in ok
                  if r["pycg"].get("deterministic_across_seeds") is False]
        if nondet:
            print(f"PyCG differed across seeds on {len(nondet)} repos: "
                  f"{', '.join(nondet[:8])}{' ...' if len(nondet) > 8 else ''}")
    partial = [r for r in latest.values() if r.get("status") == "partial"]
    if partial:
        print(f"\n{len(partial)} repos have a FAILED baseline and are not done. "
              f"Re-running picks them up:")
        for r in partial:
            print(f"  {r['repo_name']:<24} failed: {','.join(r.get('baselines_failed', []))}"
                  f"   pycg={r.get('pycg', {}).get('seeds_completed')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="extract S for each repo")
    run.add_argument("--from-triage", type=Path,
                     help="triage ledger.jsonl; uses corpus-admitted rows")
    run.add_argument("--repos-from", type=Path, help="`repo_url [sha]` per line")
    run.add_argument("--data", type=Path, default=DEFAULT_DATA)
    run.add_argument("--clone-dir", type=Path,
                     help="reuse existing clones here instead of cloning "
                          "(e.g. ~/traceweave-data/refrepos)")
    run.add_argument("--image", default=pycg_baseline.DEFAULT_IMAGE)
    run.add_argument("--seeds", default=",".join(pycg_baseline.DEFAULT_SEEDS))
    run.add_argument("--site-packages")
    run.add_argument("--shard", default=None, metavar="i/n",
                     help="process only shard i of n of the remaining repos "
                          "(1-based). Each shard needs its own --data dir; "
                          "merge the ledgers afterwards.")
    run.add_argument("--include-survey-only", action="store_true",
                     help="also extract repos the MANIFEST §7 redistribution gate "
                          "keeps out of the corpus (feasibility survey only)")
    run.add_argument("--include-tests", action="store_true",
                     help="widen the universe to test code (moves the denominator)")
    run.add_argument("--exclude", default="", help="comma-separated basenames to skip")
    run.add_argument("--chunk", type=int, default=64)
    run.add_argument("--request-timeout", type=float, default=60.0)
    run.add_argument("--ready-timeout", type=float, default=180.0)
    run.add_argument("--pyright-timeout", type=float, default=7200.0)
    run.add_argument("--pycg-memory", default="8g")
    run.add_argument("--pycg-timeout", type=int, default=1800)
    run.add_argument("--clone-timeout", type=int, default=900)
    run.add_argument("--skip-pycg", action="store_true")
    run.add_argument("--skip-pyright", action="store_true")
    run.add_argument("--keep-clones", action="store_true")
    run.add_argument("--limit", type=int)
    run.add_argument("--force", action="store_true", help="re-extract done repos")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--quiet", action="store_true")
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("report", help="per-repo table + baseline agreement")
    rep.add_argument("--data", type=Path, default=DEFAULT_DATA)
    rep.set_defaults(func=cmd_report)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
