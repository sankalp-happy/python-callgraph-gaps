# TraceWeave-Core — Discovery handoff report

Run date: 2026-08-08. Host: Linux x86_64, 16 cores, Docker 29.5.3 (amd64 native).
Artifact: `candidates-result.tar.gz` (539K, 7 files) — sent alongside this report.

Result: **558 repos queued** (target 450–600), strata HIGH=135 / MED=177 / LOW=246.

---

## 1. §1 prerequisite output (including `arch=`)

```
docker server: 29.5.3 arch=amd64
git version 2.34.1
Python 3.10.12
/dev/nvme0n1p2  468G  112G  333G  26% /
16 cores
--- power / sleep state ---
  sleep inhibitor: ACTIVE (lid-switch + sleep + idle blocked for this run)
  power: on AC
GITHUB_TOKEN: set, 93 chars (value not logged)
--- live GitHub rate limit ---
  core: 5000/5000 remaining
  search: 30/30 remaining
```

Docker was **not running at first contact**. Docker Desktop for Linux 4.78.0 is installed as a
*user* unit, shipped `disabled`/`inactive`; context `desktop-linux` pointed at a socket that did
not exist. `systemctl --user start docker-desktop` fixed it. Worth a line in §1 for Linux hosts —
the failure presents as a missing daemon, not as a disabled service.

Provenance verified before anything ran:

```
lock.txt lines: 9 (expect 9)
lock_sha256=10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
```

## 2. `run_checks.sh` result

Baseline, run before the pipeline:

```
 passed: 6   failed: 0
```

`--full`, including the calibration sweep (captured in `logs/run_checks_full.txt`):

```
=== 7. full calibration sweep (expects 6 HIGH / 4 MED / 3 LOW / 1 TOO_SMALL) ===
        got: HIGH=6 LOW=3 MED=4 TOO_SMALL=1
  PASS  calibration reproduces the frozen distribution

 passed: 7   failed: 0
```

The frozen distribution reproduces exactly on this host. Re-run **after** the `github_meta.py`
patch in item 5 and still 7/0, so the patch does not disturb the calibration.

## 3. Full `queue` console output (verbatim)

```
[queue] 558 queued, 1203 excluded
         /home/sankalp.shankar/traceweave-data/candidates/03_queue.csv
         /home/sankalp.shankar/traceweave-data/candidates/03_qc_sample.csv (56 rows, seed 20260727)

[queue] prefix composition (this is what amendment 3 buys):
         first  25%  n=139  HIGH=58  LOW=35  MED=46
         first  50%  n=279  HIGH=116  LOW=70  MED=93
         first  75%  n=418  HIGH=135  LOW=121  MED=162
         first 100%  n=558  HIGH=135  LOW=246  MED=177

[queue] survival needed to hit MANIFEST §4 floors:
         LOW   246 queued -> floor 10  needs   4.1% to survive triage + >=3 workloads
         MED   177 queued -> floor 12  needs   6.8% to survive triage + >=3 workloads
         HIGH  135 queued -> floor 15  needs  11.1% to survive triage + >=3 workloads

         research_plans.md D2 §3: over-recruit 1.5x, and expect HIGH to
         be the binding stratum on a random sample.
```

### Reading of the HIGH row (the thing you said matters most)

**HIGH is binding, as D2 §3 predicted.** It needs 2.7x the survival rate of LOW.

- **11.1%** clears the bare MANIFEST §4 floor of 15.
- **16.7%** clears the 1.5x over-recruitment target (22.5 surviving HIGH), which is what D2 §3
  actually asks for. That is the number we would plan against, not 11.1%.

Two structural facts about how HIGH sits in the queue:

- **HIGH is heavily front-loaded.** 58 of 135 HIGH repos fall in the first 139 positions (42% of
  that prefix). Triaging only the first quarter needs 25.9% HIGH survival to reach the floor;
  working the full queue drops that to 11.1%.
- **HIGH saturates at the 75% mark** (135 at both 75% and 100%) — the final quarter contains no
  HIGH at all. That is the pool being genuinely exhausted of HIGH candidates, not an interleaver
  bug. There is no way to get more HIGH out of this queue by triaging further; only a wider pool
  would do it.

HIGH did **not** come out thin relative to the floor, but it has the least headroom of the three
and no reserve behind it.

## 4. Wall-clock and peak disk

```
pool     95m39s   exit=1   <- crashed, see item 5
pool     279m05s  exit=0   <- full re-run from scratch
score    5m42s    exit=0
peak ~/traceweave-data/work usage: 623 MB
```

`score` ran at `--jobs 12`. 600 repos in 342 s is ~6.8 s/repo of worker time, which is right for a
`--depth 1` single-commit fetch plus one AST pass. Disk was never a constraint — peak 623 MB
against 333 GB free. The real ceiling was the Docker VM's 8.32 GB RAM, which is what capped jobs at
12 rather than the 16 available cores.

**`pool` is far slower than §6 suggests** — 4h39m, not the documented estimate. Cause in item 5.

## 5. Everything that failed or looked wrong

### 5a. `pool` crashed after 95 minutes on an uncaught `IncompleteRead` — 100% of that work lost

```
  File ".../scripts/discover_candidates.py", line 228, in stage_pool
    raw = shard_pool(args.min_stars, pushed_after, token)
  File ".../scripts/discover_candidates.py", line 157, in shard_pool
    items, total = search_shard(lo, hi, pushed_after, token)
  File ".../scripts/discover_candidates.py", line 131, in search_shard
    data, status, headers = api_get(path, token)
  File ".../scripts/github_meta.py", line 113, in api_get
    return json.load(r), r.status, dict(r.headers)
  File "/usr/lib/python3.10/http/client.py", line 641, in _safe_read
    raise IncompleteRead(data, amt - len(data))
http.client.IncompleteRead: IncompleteRead(524585 bytes read, 35071 more expected)
```

`http.client.IncompleteRead` is an `HTTPException`, **not** a `URLError` — `URLError` is an
`OSError`. So it matched none of `api_get`'s three `except` clauses and killed the process.

**The handoff's claim that "all three stages resume" is false for `pool`'s search phase.**
`stage_pool` runs the entire star-shard search in memory (`discover_candidates.py:228`) and writes
`01_pool.jsonl` only once enrichment starts. Nothing had been written, so the full 95 minutes was
unrecoverable and the re-run started from zero. Checkpointing the search — even just the `seen`
dict and the pending `todo` queue — would have turned a 95-minute loss into a few minutes.

### 5b. Workaround applied: `github_meta.py` `api_get` retry (our one deviation)

The obvious fix — adding `HTTPException` to the existing `except` list — would have been **worse
than the crash**. `search_shard` treats a `None` return as "search failed" and `break`s out of its
page loop, so a single truncated response would have silently dropped repos from that star shard
and biased the pool with no diagnostic. We retried instead, and only fall back to the original
`(None, 0, {})` contract after 5 attempts.

Backup of the original is at `scripts/github_meta.py.orig`.

```diff
@@ -25,6 +25,7 @@
 import argparse
+import http.client
@@ -36,6 +37,8 @@
 API = "https://api.github.com"
 SPEC_VERSION = "1.0"
+RETRIES = 5           # attempts per request before giving up on a transient fault
+RETRY_BACKOFF_S = 3   # doubles each attempt: 3s, 6s, 12s, 24s
@@ -108,13 +111,34 @@
-    try:
-        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
-            return json.load(r), r.status, dict(r.headers)
-    except urllib.error.HTTPError as e:
-        return None, e.code, dict(e.headers or {})
-    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
-        return None, 0, {}
+    last_transient = None
+    for attempt in range(1, RETRIES + 1):
+        try:
+            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
+                return json.load(r), r.status, dict(r.headers)
+        except urllib.error.HTTPError as e:
+            return None, e.code, dict(e.headers or {})
+        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
+                http.client.HTTPException, ConnectionError, OSError) as e:
+            last_transient = e
+            if attempt == RETRIES:
+                break
+            back = RETRY_BACKOFF_S * (2 ** (attempt - 1))
+            print(f"  transient {type(e).__name__} on {path[:60]}; "
+                  f"retry {attempt}/{RETRIES - 1} in {back:.0f}s", file=sys.stderr)
+            time.sleep(back)
+    print(f"  GAVE UP after {RETRIES} attempts: "
+          f"{type(last_transient).__name__}: {last_transient}", file=sys.stderr)
+    return None, 0, {}
```

`HTTPError` is deliberately still not retried — callers depend on seeing 403 and 404 immediately.

Tested against a mocked `urlopen` before the re-run: (1) `IncompleteRead` x2 then success → 3
attempts, status 200, real data; (2) `HTTPError` 403 → 1 attempt, no retry; (3) persistent
transient → 5 attempts, returns `(None, 0, {})`. `run_checks.sh` still 7/0 afterwards.

**In the successful 4h39m re-run the patch never fired** — 0 retries, 0 `GAVE UP`. So the original
crash was a genuine one-off transport fault, not something structural about this host. The patch is
insurance that was never billed.

### 5c. `search_shard` discards ~90% of what it fetches — this is why `pool` takes 4.5 hours

`shard_pool` only needs `total_count` to decide whether to split a shard, and `total_count` arrives
on page 1. But `search_shard` (`discover_candidates.py:127`) unconditionally paginates all 10 pages
before returning. Every shard that gets split therefore costs 10 search requests, 9 of which are
computed, transferred, and thrown away.

In this run **130 of the first 196 shards were splits** — roughly 1,300 discarded pages, about two
of the first three hours. A page-1 peek before committing to full pagination should cut `pool`
wall-clock by well over half.

### 5d. The low-star end of the corpus is silently truncated

Twelve single-star-wide shards exceeded `SEARCH_CAP` and hit the `unsplittable — TRUNCATED` branch:

```
stars:50..50: 1363 > cap and unsplittable — TRUNCATED at 1000
stars:51..51: 1398 > cap and unsplittable — TRUNCATED at 1000
stars:52..52: 1281 > cap and unsplittable — TRUNCATED at 1000
stars:53..53: 1311 > cap and unsplittable — TRUNCATED at 1000
stars:54..54: 1244 > cap and unsplittable — TRUNCATED at 1000
stars:55..55: 1222 > cap and unsplittable — TRUNCATED at 1000
stars:56..56: 1180 > cap and unsplittable — TRUNCATED at 1000
stars:57..57: 1167 > cap and unsplittable — TRUNCATED at 1000
stars:58..58: 1140 > cap and unsplittable — TRUNCATED at 1000
stars:59..59: 1019 > cap and unsplittable — TRUNCATED at 1000
stars:60..60: 1037 > cap and unsplittable — TRUNCATED at 1000
stars:62..62: 1016 > cap and unsplittable — TRUNCATED at 1000
```

**2,378 repos dropped**, all from the densest part of the corpus. The star axis cannot be bisected
below one-star width, so this is a hard floor of the star-sharding design, not a tuning problem.

Impact on *this* run is small: sampling is a seeded shuffle across all 98,416 matched repos, not
star-ranked, so the effect is a mild under-weighting of the 50–62 star band. It would matter a great
deal to anyone re-running with a lower `--min-stars`, where truncation would spread across many more
shards. A second sharding axis (e.g. `pushed:` date within a star bucket) would fix it properly.

### 5e. One repo failed to score — repo's fault, not the host's

```
Baekalfen/PyBoy   SCORER_RC_1
RecursionError: maximum recursion depth exceeded   (ast.py generic_visit)
```

`density_score.py`'s AST visitor hits CPython's recursion limit on a deeply nested tree. Not
`RC_137`/`RC_139`, so not an OOM from our `--jobs 12` choice — this will reproduce on your hardware.
Row retained with `excluded_reason=SCORE_FAILED`, not dropped.

### 5f. Two 403 secondary-rate-limit hits

Both during `pool` search; handled by the existing 60 s sleep-and-retry path and recovered. No data
lost. Noting them only because §7 asks for anything that looked wrong.

## Run integrity

- **`sha_drift=yes`: 0 of 600.** Every repo was materialised at exactly its frozen SHA — scoring and
  triage will read identical trees. No silent fallback to branch tip anywhere.
- Pool funnel: 98,416 matched → 1,761 enriched → 600 eligible. Exclusions: `NO_BUILD_FILE` 937,
  `NO_TESTS` 224. Of the 600 scored: 599 OK, 1 failed, 41 `TOO_SMALL`.
- Density distribution: min 0.0, median 4.433, max 88.975. Thresholds untouched at 4.0 / 10.0.
- `03_queue.csv` contains **1,761 rows, not 558** — excluded repos are retained with
  `excluded_reason` set and an empty `queue_position`, per §8 rule 6. Filter on `queue_position` to
  get the 558.

## Rules observed

`triage/triage.sh` not run and Phase 1 not started; `out/` untouched; no edits to `traceweave/docs/`,
`MANIFEST.md`, or `config/base_images.json`; density thresholds unchanged; no cloned repo's source
modified; no failing repo cleaned up; every image referenced by digest
(`python@sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464`), never by tag.

The single deviation from shipped code is the `github_meta.py` patch in 5b, disclosed above with its
original preserved at `github_meta.py.orig`.

No token appears in this report, in any log, or in any file in the tarball.
