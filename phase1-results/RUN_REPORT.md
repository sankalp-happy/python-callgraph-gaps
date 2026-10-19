# TraceWeave-Core — Phase 1 execution report

Both unattended jobs from `RUN_ON_LINUX.md` are complete: the candidate triage
(§1.1) and the static extraction of both baselines (§1.2).

| | |
|---|---|
| Host | x86_64 Linux laptop, Ryzen 7 7840HS (8c/16t), 38 GiB RAM — see `PROVENANCE.md` |
| Triage | 2026-08-21 → 2026-08-22 |
| Static extraction | 2026-08-22 → 2026-08-23 |
| Architecture | `linux/amd64` throughout, native, **zero emulated attempts** |
| Compute | 19.0 worker-hours triage + 28.2 worker-hours static |

Four code fixes were required to complete the run. Two are environment-independent
bugs that will hit any host; see §6. All are supplied as patches in `patches/`.

---

## 1. Triage results (§1.1)

**240 repos triaged, 326 attempts, 118 corpus-admissible.**

| Stratum | Triaged | Admissible | Floor | Target |
|---|---|---|---|---|
| LOW | 60 | 31 (51.7%) | 10 ✓ | 15 ✓ |
| MED | 80 | 36 (45.0%) | 12 ✓ | 20 ✓ |
| HIGH | 100 | 51 (51.0%) | 15 ✓ | 25 ✓ |
| **Total** | **240** | **118** | 60 ✓ | ~120 ✓ |

Redistribution gate (MANIFEST §7): **91 eligible**, 14 pending licence review,
13 survey-only.

Data integrity — all clean:

- **0 OOM** records (see §5: this required raising the Docker VM memory first)
- **0/326** runner-vs-`triage.sh` classifier disagreements
- **0** emulated attempts, so all timings are valid per MANIFEST §1.1
- 1 attempt reached the 1800 s container ceiling

The queue was worked as a prefix in two passes: repos 1–200, then 201–240 to
close on the ~120 target. `candidates/extend_40.csv` is the second batch.

### 1a. The 42 `BUILD_FAIL / OTHER` repos — diagnosed, not recovered

42 repos (21% of the first 200) failed with `error_class=OTHER` after a single
attempt. **`OTHER` is not a key in the ladder** (`rungs` covers only
`PYTHON_VERSION` and `DEP_RESOLUTION`), so they never walked to 3.11/3.10/3.9.

We re-ran all 42 with `ladder.default = 3.10` (`config/base_images.py310.json`,
digests untouched). **Result: only 4 became admissible.** 31 failed identically.
The `OTHER` label was correct — these are not interpreter-version failures:

| Cause | Repos |
|---|---|
| flat-layout: "Multiple top-level packages discovered" | **12** |
| unclassified | 10 |
| needs a system `-dev` package (e.g. Archery → mysqlclient) | 2 |
| missing C headers (statsforecast → `Eigen/Core`) | 2 |
| missing native build tool (nicotine-plus → `msgfmt`, itables → `npm`) | 2 |
| setup/metadata generation failure | 2 |
| missing git submodule (jedi → typeshed) | 1 |

**The dominant cause is the harness, not the repos.** `triage.sh` runs
`pip install .` at the repo root, and setuptools refuses when the root holds
several top-level directories. buildbot, sabnzbd and zato are applications and
monorepos whose packages live in subdirectories — installable, just not that
way. This is arguably a finding for §VIII.B rather than a defect to hide: 12 of
200 real repositories cannot be installed by the standard recipe.

`jedi` is a one-line fix: `triage.sh:173` clones without `--recurse-submodules`.

---

## 2. Static extraction results (§1.2)

**105 repos attempted** (91 eligible + 14 pending licence review; 13
survey-only were excluded by the gate).

| Outcome | Repos |
|---|---|
| `ok` — both baselines succeeded | **78** |
| `partial` — PyCG failed on every seed | 22 |
| `no_python_package_found` — layout undetected | 5 |

By stratum: 43 HIGH / 33 MED / 29 LOW.

### Baseline agreement — the §1.2 headline

Jaccard on in-universe edges, n = 78:

```
median 0.6524   mean 0.6586   min 0.0455   max 1.0000
p25    0.564    p75  0.787
below 0.5:  16 repos
0.5 – 0.8:  43 repos
0.8 and up: 19 repos
```

This sits squarely inside the 0.5–0.8 the extraction README predicts. Two tools
reading identical source agree on about two-thirds of call edges.

---

## 3. Two findings not in the original plan

**PyCG is non-deterministic on 36 of 78 repos (46%).** Same source, same tool,
same image — a different `PYTHONHASHSEED` yields a different call graph. This
justifies the 3-seed design retroactively and is a reportable result about a
widely used baseline.

**PyCG cannot analyse 21% of the corpus (22 of 105).** Every one recorded
`all_runs_failed` with `seeds_completed: []` — all three seeds hit the 1800 s
timeout. Pyright completed every one of those repos.

### Do NOT re-run to clear the 22 partials

`run_corpus.sh` closes with "Re-run this script to pick up anything recorded
'partial'". For these 22 that is a trap: **22 out of 22 completed zero seeds**,
so a re-run costs ~33 worker-hours to reproduce the same 22 failures. They
should be recorded as a result, not retried.

---

## 4. The 5 `no_python_package_found` repos — root causes

All five returned `layout=unknown`. Diagnosed against fresh checkouts; three
share two cheap fixes in `detect_layout` (`extract.py:107`):

| Repo | Package actually at | Why the guess failed |
|---|---|---|
| `ufo2ft` | `Lib/ufo2ft/` | `detect_layout` tries `("lib", "python")` — **case-sensitive**, so `Lib` is missed |
| `python-genai` | `google/genai/` | PEP 420 namespace package: `google/` has no `__init__.py`, and `packages_in()` requires one |
| `cocotbext-axi` | `cocotbext/axi/` | same namespace-package cause |
| `excel-mcp-server` | under `src/`, no `__init__.py` anywhere | the `src-flat` branch globs `src/*.py` only, non-recursively |
| `Vibe-Trading` | `agent/src/` | monorepo, package two levels below a non-standard top dir — needs a per-repo override |

Fixing the case-sensitivity and namespace-package cases recovers 3 repos for a
few lines. These were left unfixed deliberately: `detect_layout`'s guess decides
every name PyCG emits, so changing it alters extracted graphs and is a
methodology call, not a bug fix.

---

## 5. Environment issue: the Docker VM memory ceiling

`MIGRATION.md:145` records this host as "38 GB", and `run_corpus.sh:40` says
`PYCG_MEMORY=8g` is "Real on this host, unlike on the Mac's 3.83 GB Docker VM."

**Both are misleading.** Docker Desktop runs containers in a VM whose memory is
a *setting*, independent of host RAM. It defaulted to **7.75 GiB** here. So:

- at `--jobs 8`, triage gave each container ~970 MB — the docs' own warning
  says OOM-killed containers are recorded as `error_class=OOM` and healthy
  repos wrongly excluded;
- `--pycg-memory 8g` **exceeded the whole daemon**, which is exactly the
  misleading failure `extract.py:492`'s `check_docker_memory` warns about.

It was raised to **26.42 GiB** before triage began. Result: 0 OOM records in
326 triage attempts and 0 in static extraction. 26 GB was chosen over 32 GB to
leave host headroom against only 2 GB of swap; peak observed container use was
under 1 GB.

**Recommend correcting `MIGRATION.md`'s host table** to record the Docker VM
ceiling alongside host RAM, since that is the number that governs both jobs.

### Disk

`Docker.raw` is a sparse file that grows and never shrinks: it reached 231 GB
while Docker itself held only ~17 GB live. `docker system prune` frees space
*inside* it without shrinking the file. It was purged between runs (231 GB →
53 GB). `RUN_ON_LINUX.md`'s "~30 GB free" is low by roughly 5×; budget 150 GB+
or plan a purge between phases.

---

## 6. Code fixes applied (`patches/`)

All four are unified diffs against the files as received. Originals kept as
`*.bak` on the host. The 45 `tests/test_static.py` guards pass after every one.

### 6.1 `extract.py` — architecture name mismatch (BLOCKER)

Static extraction refused to start:

```
FATAL: ledger was built on ['amd64'], this host is x86_64.
       MANIFEST §1: one corpus, one architecture.
```

Same machine. `triage/runner.py:detect_arch` reports Docker's spelling
(`docker version --format {{.Server.Arch}}` → `amd64`); `extract.py:390` used
`platform.machine()` → `x86_64`. The guard compared the two and always fires.

**This would block any host, on any architecture.** Worse than the crash: the
per-repo filter at `extract.py:354` silently `continue`s on the same mismatch,
so bypassing the FATAL would have extracted **0 of 105 repos and reported
success.**

Fix: normalise both sides through an alias map (`x86_64`↔`amd64`,
`aarch64`↔`arm64`). Verified: selection went from 0 to 105 repos.

### 6.2 `pycg_baseline.py` — container leak on timeout (SEVERE)

`subprocess.run(..., timeout=)` kills the `docker run` **client**, not the
container. With no `--name` and no `docker kill`, the container keeps running in
the daemon at 100% CPU forever; `--rm` only fires on exit, which never happens.

Every PyCG timeout leaked one container. A repo PyCG cannot analyse leaks one
per seed. Observed live: 5 containers where 1 was expected, the oldest 3h13m
old, start times spaced exactly 30 minutes apart — 4 of 16 cores lost to work
already abandoned. Left alone, ~22 hopeless repos × 3 seeds would have leaked
~66 containers, each permitted 8 GB.

Fix: `--name` plus a best-effort `docker kill` on the timeout path. Verified by
reproducing the leak and confirming the kill; after the fix, 14 hours of running
and roughly a dozen timeout episodes left exactly 1 container alive.

### 6.3 `pyright_baseline.py` — same leak

Identical pattern at `run_probe`, with a 7200 s timeout. Not observed firing,
but the same defect. Same fix, guarded on `in_docker` so `--image none` is
unaffected.

### 6.4 `extract.py` — new `--shard i/n` (feature, not a fix)

Serial extraction was projecting ~50 worker-hours. `run_corpus.sh`'s header
suggests sharding by hand, but the `--repos-from` path
(`extract.py:375 targets_from_file`) hardcodes `stratum: ""`, `pyver: ""`,
`row_id: ""` — sharding that way silently drops each repo's stratum, which the
per-stratum analysis needs.

`--shard i/n` instead partitions **after** the `done` filter, keeping every
field from the triage ledger. Repos are dealt most-expensive-first using prior
`seconds_total`, so known ~90-minute repos spread evenly rather than piling into
one shard (naive round-robin gave 6/3/1; cost-ordered gives 4/3/3).

Used as 3 shards with separate `--data` dirs: **~50 worker-hours → 13 hours
wall clock.** Verified disjoint and complete before launch (28+28+27 = 83
repos, 83 unique, no overlaps).

Note the same `--repos-from` metadata trap exists in `triage/runner.py:532`
(`stratum: "REFERENCE"`, no `redistribution_class`, empty `sha`). Both recovery
and extension passes therefore used filtered CSVs, not `--repos-from`.

---

## 7. Open items

1. **ins3 Part 1-R licence review** — 14 admissible repos unresolved. Clearing
   them lifts the corpus from 91 toward 105.
2. **ins2 workload capture (§1.3)** — the real bottleneck, unblocked by this run.
   Caution: **18 of the 118 admissible repos collected fewer than 10 tests**
   (median 134), so they will struggle to yield 3 replayable workloads. Realistic
   usable pool ≈ 100, still well clear of the floor of 60.
3. **The 22 PyCG failures** — record as a result; do not retry (§3).
4. **The 5 layout failures** — 3 are cheap to recover (§4), but it is a
   methodology call.
5. **The 12 flat-layout triage failures** — either teach `triage.sh` a smarter
   install strategy or disclose the exclusion. As-is the corpus is biased against
   applications and monorepos.
6. **Correct `MIGRATION.md`'s host table** to state the Docker VM ceiling (§5).

---

## 8. Archive contents

```
RUN_REPORT.md            this file
PROVENANCE.md            host, Docker, image digests, tool versions
triage/ledger.jsonl      326 attempt records over 240 repos
triage_report.txt        runner.py report output
static/                  per-repo artifacts + ledger.jsonl (105 records)
static_report.txt        extract.py report output, incl. the per-repo table
patches/*.patch          the four code changes, unified diffs
queues/                  the filtered CSVs used for the recovery and extension
```

`static/ledger.jsonl` is the merged result of three shards, deduped by
`repo_url` preferring `ok` over `partial` and later records over earlier.
Pre-merge inputs are retained on the host as `ledger.pre-shard.jsonl` and
`ledger.beforemerge.bak`.

`static/` holds 100 per-repo artifact directories against 105 ledger records.
The 5 without artifacts are exactly the `no_python_package_found` repos from §4:
layout detection fails before either baseline runs, so there is nothing to write.

Per-repo artifacts were produced across four data roots (the pre-shard run plus
three shards) and consolidated here; the host's `~/traceweave-data/static/` was
consolidated to match.

---

## Erratum (2026-10-19)

§3 says the 22 PyCG failures all hit the 1800 s timeout on every seed. The per-seed records in
`static/<repo>/pycg.json` say otherwise: 15 timed out on every seed, 4 crashed on every seed
(bitstring, confection, unyt: `IndexError` in PyCG's `_get_fun_defaults`; jaxpruner:
`AttributeError` on `get_name_pointer`), 1 was OOM-killed on every seed (matlab2python), and on 2
the failure mode changed with the seed (alphagenome_research: two timeouts and a crash; xDiT: two
timeouts and an OOM kill). The advice not to re-run them stands. `paper/make_numbers.py` computes
these counts from the records.
