#!/usr/bin/env python3
"""Build the stratified `candidates` queue that feeds ins1 triage.

MANIFEST.md §7 item 4. Produces the input list for `triage/runner.py` plus a 10%
sample for the human-vs-automated-classifier validation described in README §8.

Three resumable stages, each writing JSONL into `$TW_DATA/candidates/`:

    pool   GitHub repo search, star-sharded to beat the 1000-result search cap.
           Freezes each repo's default-branch HEAD sha ON DISCOVERY DAY (MANIFEST
           §3: v1.1 forbids an empty sha) and checks the tree for a build file and
           a test suite. Licence comes free from the search payload.
    score  Clones each repo AT ITS FROZEN SHA, runs the frozen density scorer
           inside the pinned image, then deletes the clone. Never more than
           --jobs working copies on disk at once.
    queue  Interleaves strata in MANIFEST §4's target ratio (amendment 3), assigns
           row_ids, and draws the seeded QC sample.

Two things this deliberately does NOT do:

  * It does not compute its own density score. `density_score.py` is frozen at
    spec 1.0 and its 4.0/10.0 thresholds were calibrated against a 14-repo
    reference set (`docs/density_scorer_spec.md`). A second counter would leave
    those thresholds describing an instrument nobody is using.
  * It does not silently drop anything. Every repo that leaves the pipeline
    carries an `excluded_reason`, per the "never silently drop a repo" rule —
    silent drops create survivorship bias in a released benchmark.

Stdlib only, like `density_score.py` and `github_meta.py`, so the harness still
needs no pip install.

Auth: GITHUB_TOKEN is effectively mandatory here. 60 requests/hour cannot build a
450-repo pool; a token lifts it to 5000/hour.

Usage:
    export GITHUB_TOKEN=ghp_...
    python3 discover_candidates.py pool   --target 600
    python3 discover_candidates.py score  --jobs 8
    python3 discover_candidates.py queue
    python3 discover_candidates.py all --target 600 --jobs 8

Exit codes: 0 ok, 2 bad args / missing input, 3 environment not usable.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_meta import (  # noqa: E402  (deliberate: reuse the frozen v1.1 mapping)
    LICENCE_MAP,
    REDISTRIBUTION,
    api_get,
    respect_rate_limit,
)

SPEC_VERSION = "1.0"
SHEET_VERSION = "v1.1"

# MANIFEST.md §4 per-stratum corpus targets. Used as interleave weights, so an
# incomplete triage run yields strata in roughly the proportion we need rather
# than the proportion the pool happened to have.
STRATUM_TARGET = {"LOW": 15, "MED": 20, "HIGH": 25}
STRATUM_FLOOR = {"LOW": 10, "MED": 12, "HIGH": 15}

# Pool selection criteria. Not inherited from any spec -- invented here, so they
# are recorded into discovery_run.json to keep the pool reproducible.
DEFAULT_MIN_STARS = 50
DEFAULT_MAX_AGE_DAYS = 365 * 3
BUILD_FILES = ("pyproject.toml", "setup.py")

# GitHub search returns at most 1000 results per query however you paginate, so
# the star axis is sharded until every shard fits under the cap.
SEARCH_CAP = 1000
SEARCH_PAGE = 100
SEARCH_PACE_S = 2.2  # 30 search requests/min authenticated


# --------------------------------------------------------------------------- io


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                log(f"WARN: skipping malformed line in {path.name}")
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ------------------------------------------------------------------ stage: pool


def search_shard(lo: int, hi: int | None, pushed_after: str,
                 token: str | None, pushed_before: str | None = None,
                 splittable: bool = True) -> tuple[list[dict], int]:
    """One (star-range x date-window) query, paginated to the search cap.

    Returns (repos, total). `total` is GitHub's total_count for the query, which
    is what tells the caller whether this shard needs splitting.

    The page-1 peek matters. `total_count` arrives with the very first page, and
    a shard whose total exceeds the cap is going to be split and re-queried
    anyway -- so paginating it first fetches up to nine more pages whose contents
    the caller then throws away. The 2026-08-08 discovery run did exactly that and
    discarded roughly 90% of everything it fetched. When the shard cannot be split
    any further we DO paginate, because those truncated results are the only ones
    we will ever get for that band.
    """
    rng = f"{lo}..{hi}" if hi is not None else f">={lo}"
    window = (f"{pushed_after}..{pushed_before}" if pushed_before
              else f">={pushed_after}")
    q = f"language:python stars:{rng} pushed:{window}"
    out: list[dict] = []
    total = 0
    for page in range(1, SEARCH_CAP // SEARCH_PAGE + 1):
        path = (f"/search/repositories?q={q.replace(' ', '+')}"
                f"&sort=stars&order=desc&per_page={SEARCH_PAGE}&page={page}")
        data, status, headers = api_get(path, token)
        if status == 403:
            wait = 60
            log(f"  403 (secondary limit); sleeping {wait}s")
            time.sleep(wait)
            continue
        if not isinstance(data, dict):
            log(f"  search failed HTTP {status} for stars:{rng} pushed:{window}")
            break
        total = int(data.get("total_count") or 0)
        items = data.get("items") or []
        out.extend(items)
        respect_rate_limit(headers)
        time.sleep(SEARCH_PACE_S)
        if len(items) < SEARCH_PAGE:
            break
        if page == 1 and total > SEARCH_CAP and splittable:
            # Over the cap and splittable: stop here, the caller will subdivide.
            break
    return out, total


def shard_pool(min_stars: int, pushed_after: str,
               token: str | None) -> tuple[list[dict], dict]:
    """Bisect until every shard is under the search cap. Returns (repos, report).

    Two axes, because one is not enough. Star-bisection alone leaves bands where
    every repo has the SAME star count -- `stars:50..50` cannot be split further
    -- and GitHub still refuses to page past 1000. The 2026-08-08 run lost 2,378
    repos that way in the 50..62 band alone. So when the star axis is exhausted,
    the `pushed:` window is bisected instead: a date range is always splittable
    down to a single day, and the union of the sub-windows is the full band.

    Every truncation that still survives both axes is recorded in the returned
    report and ends up in `01_pool_meta.json`. A cap that is not written down
    reads, later, as complete coverage.
    """
    seen: dict[str, dict] = {}
    today = date.today().isoformat()
    # (lo, hi, after, before); hi=None is the open-ended top star shard,
    # before=None means "up to now".
    todo: list[tuple[int, int | None, str, str | None]] = [
        (min_stars, None, pushed_after, None)]
    truncations: list[dict] = []
    n_queries = 0

    while todo:
        lo, hi, after, before = todo.pop(0)
        star_splittable = hi is None or hi > lo
        date_splittable = date.fromisoformat(after) < date.fromisoformat(before or today)
        items, total = search_shard(lo, hi, after, token, before,
                                    splittable=star_splittable or date_splittable)
        n_queries += 1
        span = (f"stars:{lo}..{hi if hi is not None else 'inf'} "
                f"pushed:{after}..{before or 'now'}")

        if total > SEARCH_CAP and star_splittable:
            # Geometric midpoint: star counts are heavily power-law distributed,
            # so splitting arithmetically leaves the low shard still over the cap.
            if hi is None:
                mid = max(lo + 1, lo * 4)
                todo.append((lo, mid - 1, after, before))
                todo.append((mid, None, after, before))
            else:
                mid = max(lo + 1, int((lo * hi) ** 0.5))
                if mid >= hi:
                    mid = lo + (hi - lo) // 2 + 1
                todo.append((lo, mid - 1, after, before))
                todo.append((mid, hi, after, before))
            log(f"  {span}: {total} > cap, splitting stars")
            continue

        if total > SEARCH_CAP and date_splittable:
            # Star axis exhausted; bisect the date window instead.
            d_lo = date.fromisoformat(after)
            d_hi = date.fromisoformat(before or today)
            mid = date.fromordinal((d_lo.toordinal() + d_hi.toordinal()) // 2)
            if mid <= d_lo:
                mid = d_lo + timedelta(days=1)
            todo.append((lo, hi, after, (mid - timedelta(days=1)).isoformat()))
            todo.append((lo, hi, mid.isoformat(), before))
            log(f"  {span}: {total} > cap and stars unsplittable, splitting dates")
            continue

        if total > SEARCH_CAP:
            lost = total - len(items)
            log(f"  {span}: {total} > cap, BOTH axes exhausted — "
                f"TRUNCATED at {len(items)}, {lost} unreachable")
            truncations.append({"span": span, "total": total,
                                "kept": len(items), "lost": lost})

        for it in items:
            fn = it.get("full_name")
            if fn:
                seen.setdefault(fn, it)
        log(f"  {span}: total={total} kept={len(items)} pool={len(seen)}")

    report = {
        "search_queries": n_queries,
        "shards_truncated": len(truncations),
        "repos_unreachable": sum(t["lost"] for t in truncations),
        "truncations": truncations,
        "axes": "stars bisected geometrically, then pushed-date bisected",
    }
    if truncations:
        log(f"[pool] {len(truncations)} shard(s) still truncated after both axes; "
            f"{report['repos_unreachable']} repos unreachable (recorded, not hidden)")
    return list(seen.values()), report


def classify_licence(lic: dict | None) -> tuple[str, str]:
    """github_meta.py's rule, reused verbatim: a licence file GitHub cannot
    identify is OTHER; no licence at all is NONE_FOUND (ins3 §3 distinguishes)."""
    lic = lic or {}
    spdx = lic.get("spdx_id")
    if spdx in (None, "", "NOASSERTION"):
        return ("OTHER" if lic else "NONE_FOUND"), (spdx or "none")
    return LICENCE_MAP.get(spdx, "OTHER"), spdx


def inspect_tree(owner: str, name: str, sha: str,
                 token: str | None) -> dict:
    """One trees call answers build-file, tests-dir and test-file all at once."""
    data, status, headers = api_get(
        f"/repos/{owner}/{name}/git/trees/{sha}?recursive=1", token)
    respect_rate_limit(headers)
    if not isinstance(data, dict):
        return {"tree_status": f"HTTP_{status}", "tree_truncated": False,
                "build_file": "unknown", "has_tests_dir": "unknown",
                "has_test_files": "unknown", "n_py_files": 0}
    paths = [e.get("path", "") for e in (data.get("tree") or [])
             if e.get("type") == "blob"]
    found = [b for b in BUILD_FILES if b in paths]
    tests_dir = any(p.startswith(("tests/", "test/")) for p in paths)
    test_files = any(
        (p.rsplit("/", 1)[-1].startswith("test_") and p.endswith(".py"))
        or p.endswith("_test.py")
        for p in paths
    )
    return {
        "tree_status": "OK",
        "tree_truncated": bool(data.get("truncated")),
        "build_file": "+".join(found) if found else "none",
        "has_tests_dir": "yes" if tests_dir else "no",
        "has_test_files": "yes" if test_files else "no",
        "n_py_files": sum(1 for p in paths if p.endswith(".py")),
    }


def stage_pool(args, paths: dict[str, Path], token: str | None) -> int:
    pushed_after = (datetime.now(timezone.utc)
                    - timedelta(days=args.max_age_days)).date().isoformat()
    log(f"[pool] language:python stars:>={args.min_stars} pushed:>={pushed_after}")

    raw, shard_report = shard_pool(args.min_stars, pushed_after, token)
    n_matched = len(raw)
    log(f"[pool] {n_matched} distinct repos matched")

    # Enrichment costs 2 API calls per repo, and the criteria match far more repos
    # than we need -- so sample rather than enrich everything. Seeded shuffle, NOT
    # top-by-stars: research_plans.md D2 M0 forbids selecting repos by eyeballing,
    # and a stars-ranked prefix would bias the corpus toward famous, well-typed,
    # statically-tractable code -- exactly the wrong direction for H2a.
    random.Random(args.pool_seed).shuffle(raw)
    log(f"[pool] enriching in seeded random order (seed {args.pool_seed}) "
        f"until {args.target} eligible")

    overlap = load_overlap(args.benchmark_overlap)
    if overlap:
        log(f"[pool] {len(overlap)} names loaded for benchmark_overlap tagging")

    existing = {r["repo_url"]: r for r in read_jsonl(paths["pool"])}
    rows: list[dict] = []
    n_eligible = 0
    for i, it in enumerate(raw, 1):
        if n_eligible >= args.target:
            log(f"[pool] reached {n_eligible} eligible after {i - 1} enriched; "
                f"{n_matched - (i - 1)} matched repos left untouched")
            break
        full = it.get("full_name") or ""
        owner, _, name = full.partition("/")
        url = f"https://github.com/{full}"
        if args.resume and url in existing and existing[url].get("sha"):
            rows.append(existing[url])
            n_eligible += existing[url].get("excluded_reason") == "none"
            continue

        licence, spdx = classify_licence(it.get("license"))
        row = {
            "repo_url": url,
            "owner": owner,
            "name": name,
            "sha": "",
            "sha_frozen_date": date.today().isoformat(),
            "default_branch": it.get("default_branch") or "unknown",
            "stars": int(it.get("stargazers_count") or 0),
            "last_commit_date": (it.get("pushed_at") or "")[:10] or "unknown",
            "size_kb": int(it.get("size") or 0),
            "archived": bool(it.get("archived")),
            "fork": bool(it.get("fork")),
            "licence": licence,
            "licence_spdx": spdx,
            "redistribution_class": REDISTRIBUTION.get(licence, "REVIEW_NEEDED"),
            "benchmark_overlap": "yes" if full.lower() in overlap else "no",
            "spec_version": SPEC_VERSION,
            "sheet_version": SHEET_VERSION,
        }

        # Freeze the sha. MANIFEST §3: v1.1 has no empty sha column.
        ref, status, headers = api_get(
            f"/repos/{owner}/{name}/git/ref/heads/{row['default_branch']}", token)
        respect_rate_limit(headers)
        if isinstance(ref, dict) and isinstance(ref.get("object"), dict):
            row["sha"] = ref["object"].get("sha") or ""
        if not row["sha"]:
            row["excluded_reason"] = "SHA_UNRESOLVED"
            row["tree_status"] = "SKIPPED"
            rows.append(row)
            log(f"  [{i}/{len(raw)}] {full}: sha unresolved (HTTP {status})")
            continue

        row.update(inspect_tree(owner, name, row["sha"], token))
        row["excluded_reason"] = pool_exclusion(row, args)
        n_eligible += row["excluded_reason"] == "none"
        rows.append(row)
        if i % 25 == 0:
            log(f"  [{i}/{len(raw)}] enriched, {n_eligible} eligible")
            write_jsonl(paths["pool"], rows)

    write_jsonl(paths["pool"], rows)
    paths["pool_meta"].write_text(json.dumps({
        "matched": n_matched,
        "enriched": len(rows),
        "pool_seed": args.pool_seed,
        "sampling": "seeded shuffle then enrich-until-target; NOT stars-ranked",
        "searched": date.today().isoformat(),
        "pushed_after": pushed_after,
        "search": shard_report,
    }, indent=2) + "\n")
    eligible = [r for r in rows if r["excluded_reason"] == "none"]
    log(f"[pool] wrote {len(rows)} rows -> {paths['pool']}")
    log(f"[pool] {len(eligible)} eligible to score; "
        f"{len(rows) - len(eligible)} excluded (reasons recorded, not dropped)")
    for reason in sorted({r["excluded_reason"] for r in rows} - {"none"}):
        n = sum(1 for r in rows if r["excluded_reason"] == reason)
        log(f"         {reason}: {n}")
    if len(eligible) < args.target:
        log(f"[pool] NOTE: {len(eligible)} eligible < target {args.target}. "
            f"Lower --min-stars or widen --max-age-days and re-run with --resume.")
    return 0


def pool_exclusion(row: dict, args) -> str:
    if row["fork"]:
        return "FORK"  # duplicates upstream; would double-count edges
    if row["build_file"] == "none":
        return "NO_BUILD_FILE"
    if row["has_tests_dir"] == "no" and row["has_test_files"] == "no":
        # ins2 requires >=1 kind:test_suite workload per repo, so a repo with no
        # tests cannot reach DONE even if it triages GREEN.
        return "NO_TESTS"
    if args.min_size_kb and row["size_kb"] < args.min_size_kb:
        return "LIKELY_TOO_SMALL"
    if args.max_size_kb and row["size_kb"] > args.max_size_kb:
        return "LIKELY_TOO_LARGE"
    return "none"


def load_overlap(path: Path | None) -> set[str]:
    """owner/name per line -> benchmark_overlap tag. Tagged, never unioned in:
    selecting *from* a Java->Python benchmark would reimport the Direction 1
    framing that SOP v1.1 amendment 4 deleted."""
    if not path or not path.exists():
        return set()
    return {ln.strip().lower().removeprefix("https://github.com/").rstrip("/")
            for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")}


# ----------------------------------------------------------------- stage: score


def resolve_image(pyver: str) -> str | None:
    script = Path(__file__).resolve().parent / "resolve_image.py"
    try:
        p = subprocess.run([sys.executable, str(script), pyver],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() or None


def fetch_at_sha(url: str, sha: str, branch: str, dest: Path) -> tuple[bool, str]:
    """Materialise exactly the frozen commit. Returns (ok, scored_sha).

    A plain `--depth 1` clone gives current HEAD, which drifts away from the sha
    frozen at pool time -- you would score one tree and triage another. So fetch
    the sha itself, and if the server refuses, fall back to the branch tip and
    report the drift rather than hiding it.
    """
    dest.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-C", str(dest), *a], capture_output=True, text=True, timeout=600)
    try:
        run("init", "-q")
        run("remote", "add", "origin", url)
        if run("fetch", "--depth", "1", "-q", "origin", sha).returncode == 0:
            if run("checkout", "-q", "FETCH_HEAD").returncode == 0:
                return True, sha
        if run("fetch", "--depth", "1", "-q", "origin", branch).returncode != 0:
            return False, ""
        if run("checkout", "-q", "FETCH_HEAD").returncode != 0:
            return False, ""
        got = run("rev-parse", "HEAD").stdout.strip()
        return True, got
    except (OSError, subprocess.SubprocessError):
        return False, ""


def score_one(row: dict, img: str, scripts: Path, workroot: Path) -> dict:
    url, sha = row["repo_url"], row["sha"]
    dest = workroot / f"{row['owner']}__{row['name']}"
    out = dict(row)
    try:
        shutil.rmtree(dest, ignore_errors=True)
        ok, scored_sha = fetch_at_sha(url, sha, row["default_branch"], dest)
        if not ok:
            out.update(score_status="CLONE_FAILED", excluded_reason="CLONE_FAILED")
            return out
        out["scored_sha"] = scored_sha
        out["sha_drift"] = "yes" if scored_sha != sha else "no"

        p = subprocess.run(
            ["docker", "run", "--rm", "--network=none",
             "-v", f"{dest}:/repo:ro", "-v", f"{scripts}:/s:ro", img,
             "python3", "/s/density_score.py", "/repo",
             "--repo-url", url, "--sha", scored_sha],
            capture_output=True, text=True, timeout=900)
        if p.returncode != 0 or not p.stdout.strip():
            out.update(score_status=f"SCORER_RC_{p.returncode}",
                       excluded_reason="SCORE_FAILED",
                       score_stderr=p.stderr.strip()[-400:])
            return out
        d = json.loads(p.stdout)
        src = d.get("source") or {}
        out.update(
            score_status="OK",
            density_score=d.get("density_score"),
            stratum=d.get("stratum"),
            source_sloc=src.get("sloc"),
            parse_failures=src.get("parse_failures"),
            frameworks=",".join(src.get("frameworks") or []) or "none",
            scorer_spec_version=d.get("spec_version"),
        )
        if out["stratum"] == "TOO_SMALL":
            # Corpus-ineligible by construction (records died here at 495 SLOC),
            # but recorded with a reason rather than dropped.
            out["excluded_reason"] = "TOO_SMALL"
        return out
    except subprocess.TimeoutExpired:
        out.update(score_status="TIMEOUT", excluded_reason="SCORE_FAILED")
        return out
    except (OSError, json.JSONDecodeError) as e:
        out.update(score_status=f"ERROR_{type(e).__name__}",
                   excluded_reason="SCORE_FAILED")
        return out
    finally:
        shutil.rmtree(dest, ignore_errors=True)


def stage_score(args, paths: dict[str, Path]) -> int:
    pool = read_jsonl(paths["pool"])
    if not pool:
        log(f"[score] no pool at {paths['pool']}; run `pool` first")
        return 2

    img = resolve_image(args.pyver)
    if not img:
        log("[score] could not resolve a pinned image — is Docker running?")
        return 3
    log(f"[score] scoring inside {img}")

    done = {r["repo_url"]: r for r in read_jsonl(paths["scored"])} if args.resume else {}
    todo = [r for r in pool
            if r.get("excluded_reason") == "none" and r["repo_url"] not in done]
    carried = [r for r in pool if r.get("excluded_reason") != "none"]
    log(f"[score] {len(todo)} to score, {len(done)} cached, {len(carried)} pre-excluded")
    if args.limit:
        todo = todo[: args.limit]
        log(f"[score] --limit {args.limit}")

    scripts = Path(__file__).resolve().parent
    workroot = paths["work"] / "_discover"
    workroot.mkdir(parents=True, exist_ok=True)

    results = list(done.values())
    lock = threading.Lock()
    n_done = 0

    def flush() -> None:
        write_jsonl(paths["scored"], results + carried)

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=args.jobs) as pool_ex:
            futs = {pool_ex.submit(score_one, r, img, scripts, workroot): r
                    for r in todo}
            for fut in as_completed(futs):
                row = fut.result()
                with lock:
                    results.append(row)
                    n_done += 1
                    if n_done % 10 == 0:
                        flush()
                        log(f"  [{n_done}/{len(todo)}] scored")
    finally:
        flush()
        shutil.rmtree(workroot, ignore_errors=True)

    ok = [r for r in results if r.get("score_status") == "OK"]
    log(f"[score] wrote {len(results) + len(carried)} rows -> {paths['scored']}")
    for s in ("HIGH", "MED", "LOW", "TOO_SMALL"):
        log(f"         {s}: {sum(1 for r in ok if r.get('stratum') == s)}")
    drift = sum(1 for r in ok if r.get("sha_drift") == "yes")
    if drift:
        log(f"[score] WARNING: {drift} repos scored at a DIFFERENT sha than frozen "
            f"(server refused fetch-by-sha). `scored_sha` records what was read.")
    failed = sum(1 for r in results if r.get("score_status") not in ("OK", None))
    if failed:
        log(f"[score] {failed} failed to score (excluded_reason set; not dropped)")
    return 0


# ----------------------------------------------------------------- stage: queue


def interleave(by_stratum: dict[str, list[dict]]) -> list[dict]:
    """Amendment 3. Emit strata in MANIFEST §4's target ratio so that ANY prefix
    of the queue carries all three, rather than the pool's own proportions.

    Deficit round-robin: repeatedly emit from whichever stratum is furthest
    behind its target share. Degrades gracefully when a stratum runs dry.
    """
    cursor = {s: 0 for s in by_stratum}
    emitted = {s: 0 for s in by_stratum}
    out: list[dict] = []
    total = sum(len(v) for v in by_stratum.values())
    while len(out) < total:
        avail = [s for s in by_stratum if cursor[s] < len(by_stratum[s])]
        if not avail:
            break
        pick = min(avail, key=lambda s: ((emitted[s] + 1) / STRATUM_TARGET.get(s, 1), s))
        out.append(by_stratum[pick][cursor[pick]])
        cursor[pick] += 1
        emitted[pick] += 1
    return out


def stage_queue(args, paths: dict[str, Path]) -> int:
    scored = read_jsonl(paths["scored"])
    if not scored:
        log(f"[queue] no scored rows at {paths['scored']}; run `score` first")
        return 2

    queued = [r for r in scored
              if r.get("score_status") == "OK" and r.get("excluded_reason") == "none"]
    excluded = [r for r in scored if r not in queued]

    by_stratum: dict[str, list[dict]] = {}
    for r in queued:
        by_stratum.setdefault(r.get("stratum", "LOW"), []).append(r)
    # Within a stratum, most-starred first: a proxy for "installs today and has
    # documented commands", which is what ins2 yield actually depends on.
    for s in by_stratum:
        by_stratum[s].sort(key=lambda r: -int(r.get("stars") or 0))

    ordered = interleave(by_stratum)

    rng = random.Random(args.qc_seed)
    n_qc = max(1, round(len(ordered) * args.qc_fraction)) if ordered else 0
    qc_idx = set(rng.sample(range(len(ordered)), n_qc)) if n_qc else set()

    rows: list[dict] = []
    for i, r in enumerate(ordered):
        rows.append({**r,
                     "row_id": f"C{i + 1:04d}",
                     "queue_position": i + 1,
                     "qc_sample": "yes" if i in qc_idx else "no"})
    for r in excluded:
        rows.append({**r, "row_id": "", "queue_position": "", "qc_sample": "no"})

    write_jsonl(paths["queue_jsonl"], rows)

    cols = ["row_id", "repo_url", "sha", "sheet_version", "stratum",
            "density_score", "source_sloc", "parse_failures", "frameworks",
            "stars", "last_commit_date", "licence", "redistribution_class",
            "build_file", "has_tests_dir", "has_test_files", "size_kb",
            "archived", "benchmark_overlap", "sha_drift", "qc_sample",
            "excluded_reason", "queue_position", "sha_frozen_date"]
    with paths["queue_csv"].open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # The QC sample is deliberately bare: row_id + url + sha only. README §8 —
    # the annotator must not be able to see what the classifier decided, and is
    # told not to guess it.
    with paths["qc_csv"].open("w", newline="") as fh:
        w = csv.writer(fh)
        # `result_line_seen` is required by ins1 v1.1 §6, which calls it "new in
        # v1.1 and the most useful column on the sheet": when the human and the
        # classifier disagree it distinguishes "saw different output" from "saw the
        # same output and read the table differently". Omitting it from the QC
        # sample defeated the sample's only purpose.
        w.writerow(["row_id", "repo_url", "sha", "status", "error_class",
                    "fix_applied", "n_failing", "minutes_spent", "log_file",
                    "result_line_seen", "notes", "your_name", "date",
                    "sheet_version"])
        for r in rows:
            if r.get("qc_sample") == "yes":
                w.writerow([r["row_id"], r["repo_url"], r["sha"],
                            "", "", "", "", "", "", "", "", "", "", SHEET_VERSION])

    provenance = {
        "spec_version": SPEC_VERSION,
        "sheet_version": SHEET_VERSION,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "criteria": {
            "language": "python",
            "min_stars": args.min_stars,
            "max_age_days": args.max_age_days,
            "build_files": list(BUILD_FILES),
            "requires_tests": True,
            "min_size_kb": args.min_size_kb,
            "max_size_kb": args.max_size_kb,
            "note": "star/recency floors are decisions of this tool, "
                    "not inherited from any frozen spec",
        },
        "pool": json.loads(paths["pool_meta"].read_text())
                if paths["pool_meta"].exists() else {},
        "interleave_weights": STRATUM_TARGET,
        "qc": {"fraction": args.qc_fraction, "seed": args.qc_seed,
               "n": n_qc,
               "validates": "automated classifier vs one human pass (README §8)"},
        "counts": {"queued": len(ordered), "excluded": len(excluded),
                   "by_stratum": {s: len(v) for s, v in sorted(by_stratum.items())}},
    }
    paths["run"].write_text(json.dumps(provenance, indent=2) + "\n")

    log(f"[queue] {len(ordered)} queued, {len(excluded)} excluded")
    log(f"         {paths['queue_csv']}")
    log(f"         {paths['qc_csv']} ({n_qc} rows, seed {args.qc_seed})")
    log("")
    log("[queue] prefix composition (this is what amendment 3 buys):")
    for frac in (0.25, 0.50, 0.75, 1.0):
        cut = ordered[: max(1, int(len(ordered) * frac))]
        comp = {s: sum(1 for r in cut if r.get("stratum") == s)
                for s in sorted(by_stratum)}
        log(f"         first {int(frac * 100):>3}%  n={len(cut):<4} " +
            "  ".join(f"{s}={n}" for s, n in comp.items()))
    log("")
    log("[queue] survival needed to hit MANIFEST §4 floors:")
    for s in ("LOW", "MED", "HIGH"):
        have = len(by_stratum.get(s, []))
        floor = STRATUM_FLOOR[s]
        if have < floor:
            log(f"         {s:<4} {have:>4} queued -> floor {floor}: UNREACHABLE even at "
                f"100% survival. Need >= {floor} queued, realistically {floor * 4}+.")
        else:
            log(f"         {s:<4} {have:>4} queued -> floor {floor}"
                f"  needs {floor / have * 100:5.1f}% to survive triage + >=3 workloads")
    log("")
    log("         research_plans.md D2 §3: over-recruit 1.5x, and expect HIGH to")
    log("         be the binding stratum on a random sample.")
    return 0


# ---------------------------------------------------------------------- driver


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["pool", "score", "queue", "all"])
    ap.add_argument("--data", type=Path,
                    default=Path(os.environ.get("TW_DATA",
                                                Path.home() / "traceweave-data")))
    ap.add_argument("--target", type=int, default=450,
                    help="eligible-pool size to aim for (MANIFEST §4: ~450)")
    ap.add_argument("--min-stars", type=int, default=DEFAULT_MIN_STARS)
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    ap.add_argument("--min-size-kb", type=int, default=0,
                    help="0 = off. Cheap pre-filter for the scorer's 500-SLOC gate")
    ap.add_argument("--max-size-kb", type=int, default=0,
                    help="0 = off. Guards Phase 2 tracing cost on huge repos")
    ap.add_argument("--benchmark-overlap", type=Path,
                    help="file of owner/name lines to TAG (never union in)")
    ap.add_argument("--jobs", type=int, default=8,
                    help="concurrent clone+score; also the disk bound")
    ap.add_argument("--pyver", default="3.12")
    ap.add_argument("--limit", type=int, help="score at most N (smoke test)")
    ap.add_argument("--qc-fraction", type=float, default=0.10)
    ap.add_argument("--qc-seed", type=int, default=20260727)
    ap.add_argument("--pool-seed", type=int, default=20260727,
                    help="seeds the sample order; record it, it defines the pool")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    args = ap.parse_args()

    cand = args.data / "candidates"
    cand.mkdir(parents=True, exist_ok=True)
    paths = {
        "pool": cand / "01_pool.jsonl",
        "pool_meta": cand / "01_pool_meta.json",
        "scored": cand / "02_scored.jsonl",
        "queue_jsonl": cand / "03_queue.jsonl",
        "queue_csv": cand / "03_queue.csv",
        "qc_csv": cand / "03_qc_sample.csv",
        "run": cand / "discovery_run.json",
        "work": args.data / "work",
    }

    token = os.environ.get("GITHUB_TOKEN")
    if args.stage in ("pool", "all") and not token:
        log("FATAL: GITHUB_TOKEN not set. 60 req/hr cannot build a 450-repo pool")
        log("       (needs ~3 calls/repo). export GITHUB_TOKEN=... for 5000/hr.")
        return 3

    if args.stage == "pool":
        return stage_pool(args, paths, token)
    if args.stage == "score":
        return stage_score(args, paths)
    if args.stage == "queue":
        return stage_queue(args, paths)
    rc = stage_pool(args, paths, token)
    if rc:
        return rc
    rc = stage_score(args, paths)
    return rc or stage_queue(args, paths)


if __name__ == "__main__":
    raise SystemExit(main())
