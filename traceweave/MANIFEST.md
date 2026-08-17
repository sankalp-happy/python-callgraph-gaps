# MANIFEST — TraceWeave-Core

> **This file is the reproducibility anchor for the whole project.** It is written on day one
> and only ever appended to. If a pin changes, bump `manifest_version`, add a dated row, and
> keep the old row. Nothing in this project may depend on a floating version.

| | |
|---|---|
| **manifest_version** | `1.3` |
| **created** | 2026-07-27 |
| **project** | TraceWeave-Core — static-vs-runtime call-graph completeness on Python repositories (H2a) |
| **internal deadline** | ~2026-10-26 (12 weeks) |
| **scope** | Python only. H2a + DynBench-Core + feasibility survey; bounded H2b-lite/H2c-lite. See `../research_plans.md` D2 for the full program this is a slice of. |
| **host platform** | Linux 6.8.0-124-generic, x86_64, 16 cores, 38 GB RAM, 345 GB free |
| **host python** | 3.10.12 — **note: no `sys.monitoring`.** All tracing runs inside containers; the host never traces. The density scorer must also be run containerised, or 3.11+ syntax silently fails to parse. |
| **docker** | 29.5.3, context `desktop-linux` (**Docker Desktop**) |
| **git** | 2.34.1 |
| **data root** | `$HOME/traceweave-data` — see §1.1, this is not a free choice |

## 1.1 Environment constraints (discovered 2026-07-27, load-bearing)

**Docker Desktop cannot bind-mount `/tmp`.** Verified: `$HOME` and subdirectories mount fine;
`/tmp` is refused with `mounts denied: … not shared from the host`. Since triage, workload
capture and tracing all depend on bind-mounting a repo working copy into a container, **every
corpus path must live under `$HOME`.** ins1 v1.0's use of `~/triage/work` was correct and is kept.

**Consequence for tracer-overhead measurement — carry into the paper.** Docker Desktop runs
containers inside a VM, so bind-mount I/O is materially slower than native. Therefore:

- **Absolute** wall-clock timings from this host are inflated and must not be published as
  representative of native execution.
- **Ratios** (traced ÷ untraced, measured under identical mount conditions) cancel the mount
  penalty and are the correct quantity. The plan already specifies overhead as a ratio against
  ins2's untraced baseline, so this is consistent — but the reason is recorded here so nobody
  later reports raw seconds as an overhead figure.
- Where an absolute number is unavoidable, re-measure with the repo copied *into* the container
  image rather than bind-mounted, and label it separately.

---

## 1. Base images (frozen, dual-platform)

Machine-readable source of truth: [`config/base_images.json`](config/base_images.json).
Both platforms resolved on **2026-07-27**. arm64 variant is `v8`.

| Python | `linux/amd64` digest | `linux/arm64` digest | Tracer | Role |
|---|---|---|---|---|
| **3.12** | `sha256:cab2dbf5…fd0464` | `sha256:55842c72…b3bfc1` | `sys.monitoring` | **Default.** All triage starts here. |
| 3.11 | `sha256:00af38ae…4db045` | `sha256:4fcdc7a1…702448` | `sys.setprofile` | ins1 Recipe 1 → 1 |
| 3.10 | `sha256:e8d6cdad…9655e72` | `sha256:72b24f91…cef39b` | `sys.setprofile` | ins1 Recipe 1 → 2, Recipe 2 → 1 |
| 3.9 | `sha256:dad5b29e…ca8e0d` | `sha256:9a863b2c…703d74` | `sys.setprofile` | ins1 Recipe 1 → 3 |
| 3.8 | `sha256:314bc2fb…5601a5` | `sha256:c37419b5…ffa517b` | `sys.setprofile` | ins1 Recipe 2 → 2. EOL upstream. |

Full digests are in `config/base_images.json`; these are elided for readability only.

**Always reference images by `python@sha256:…`, never by `python:3.12-slim`.** The tag moves; the
digest does not.

### Platform selection

`active_platform` is `"auto"`: `triage.sh` reads the Docker daemon's architecture and picks the
matching digest, so **moving between an x86_64 host and an Apple Silicon host requires no edit.**
Override with `TW_PLATFORM=linux/arm64` only to force a platform deliberately.

Every triaged repo records `platform`, `host_arch` and `emulated` in its `result.env`, so
provenance stays explicit across machines.

**Emulation is detected and warned about.** Running a foreign-architecture image works — which is
the danger, because it silently invalidates every wall-clock number while producing correct
results. `triage.sh` prints a loud banner and sets `emulated=yes`. Never publish overhead figures
from an emulated run.

### One corpus, one architecture

Most Python dependencies are pure-Python wheels whose versions are platform-independent, so
`lock_sha256` will often match across platforms — verified: re-running `click` on amd64 reproduced
`lock_sha256=10dc90ae…` exactly. **But any repo with compiled extensions** (numpy, lxml,
cryptography, pydantic-core) **can resolve different wheels and therefore a different
`lock_sha256`.** Do not mix platforms within a corpus without re-triaging. See `../MIGRATION.md` §4.

### Consequence to carry into the paper
Only repos that end up on **3.12** get `sys.monitoring`. Every repo rescued onto ≤3.11 by an
ins1 recipe runs the `setprofile` fallback and carries materially higher overhead. Tracer
overhead **must be reported per Python version**, never as a single pooled number, and each
repo's `pyver` is part of its identity (§3).

---

## 2. Tool pins

| Tool | Version | Purpose | Risk |
|---|---|---|---|
| **PyCG** | `0.0.8` | **Static baseline 1** — the published Python call-graph tool (ICSE 2021). Reporting against it makes H2a a claim about the state of the art, not about our extractor. | ⚠️ Latest release is `0.0.8` and it is years old. It parses with the *host* `ast`, so modern syntax (`match`, newer generics, PEP 695 type params) may crash it. **Do not treat a PyCG crash as a bug to hide** — the rate at which the field's standard baseline cannot parse contemporary Python is a reportable result. Log every failure with its traceback into the feasibility survey. ⚠️ **Two hard facts measured 2026-08-09, see §2.1:** the 0.0.8 sdist is *unimportable on Linux* without a `pycg`→`PyCG` symlink, and it *does not run on 3.12 at all*. |
| ~~**tree-sitter-python**~~ | ~~`0.25.0`~~ | ~~Parse layer for static baseline 2.~~ **RETIRED unused, 2026-08-17 (1.3). Baseline 2 parses with CPython's own `ast`.** Row kept per the append-only rule; nothing was ever built on it. | The reason is `docs/metric_spec_h2a.md` §1: node identity must equal CPython's `co_qualname` at runtime, because Phase 2 joins on it. `ast` mirrors that structure (including `<locals>` insertion and PEP 709 comprehension inlining) and tree-sitter would leave us reconstructing it — a reimplementation of the one thing that must not differ. The trade is error tolerance: a file `ast` cannot parse is recorded as a `parse_failure`, which is a reported metric either way (§4.4). Measured: **0 parse failures across click, toolz and chardet** on the 3.12 host. See `docs/static_extraction_spec.md`. |
| **Pyright** | `1.1.411` (npm `pyright`, published 2026-06-25) | Type info for attribute-call resolution in **static baseline 2**. | Installed inside the image, never on the host — §1: the host never traces, and host `npm` is not required (the registry answers over plain HTTPS). Pin the exact version in the image build: `npm i -g pyright` without a version resolves to whatever is current that day. |
| **DuckDB** | `1.5.5` | Graph store over Parquet. Chosen over Neo4j/Kùzu deliberately — k-hop slices and set-difference are columnar-friendly, and no reviewer is evaluating our store. | none material |
| **density scorer** | `1.0` (frozen) | Stratification. Calibrated on a 14-repo reference set; thresholds **4.0 / 10.0**. See [`docs/density_scorer_spec.md`](docs/density_scorer_spec.md). | Four false-positive classes were found and fixed during calibration; the regression fixture guarding them must keep passing. |

Python deps for the harness itself are pinned in `requirements.txt` (generated, committed, and
regenerated only alongside a `manifest_version` bump).

## 2.1 PyCG 0.0.8 — two defects in the pin, and what they cost (added 1.2)

The pin is unchanged at `0.0.8`: §2's argument for pinning PyCG at all is that reporting against it
makes H2a a claim about the state of the art, and that wants the *latest published* release. But
0.0.8 as published cannot be used as documented, and that has to be recorded next to the pin rather
than rediscovered from a stack trace in Phase 1. Both facts were verified in the pinned images.

**1. The sdist is unimportable on Linux.** It ships its package directory as `PyCG/` while every
internal import reads `from pycg import …`. On a case-insensitive filesystem (macOS) that works by
accident; on Linux — every container in this project — all four routes fail, including `import
PyCG.pycg`, which is defeated by PyCG's *own* internal import. 0.0.8 also ships no console script,
so the documented `pycg` command does not exist.

> **Every image that installs PyCG MUST create the shim:**
> `ln -sfn "$SP/PyCG" "$SP/pycg"` where `SP` is site-packages.
> `scripts/pycg_parse_rate.py` does this. PyPI 0.0.7 packages correctly as lowercase, so the fault
> is specific to the 0.0.8 release.

**2. It does not run on Python 3.12.** §1 makes 3.12 the default — *"All triage starts here."*
Static baseline 1 cannot run there. A five-line module with two functions and one call fails with
`ImportManagerError: Can't add edge to a non existing node` on 3.12.13 and yields 3 nodes on
3.10.20. Note it is **not** a `SyntaxError`: the failure is in PyCG's import-resolution machinery
under 3.12's `ast`, not in parsing. §2 anticipated the parse risk; this is a larger and different
one.

> **Consequence for the design.** A repo's triaged `pyver` and the interpreter PyCG runs under are
> **independent**. A repo triaged on 3.12 still has its static baseline extracted on ≤3.11. This is
> defensible — PyCG reads source, it does not execute the repo — but it means the static and runtime
> sides of an H2a comparison run under different interpreters, and that must be stated in the paper
> rather than discovered by a reader.

### Measured parse-failure rate (answers §7 item 2)

14-repo reference set at recorded shas, 1311 files, seeded sample (seed 20260727), 120-file cap per
repo with 7342 files skipped and recorded as skipped. Kept **per interpreter and never pooled**, for
the same reason §1 requires tracer overhead to be reported per `pyver`.

| interpreter | slice | failed / analysed | rate |
|---|---|---|---|
| **3.10** | library code only | 9 / 558 | **1.6%** |
| 3.10 | all files | 32 / 1311 | 2.4% |
| 3.10 | test & fixture paths | 23 / 753 | 3.1% |
| **3.12** | all files | 1311 / 1311 | **100.0%** |

On 3.10, by outcome: 17 `SyntaxError`, 8 timeout (>20 s on a single file), 7 other exceptions.
**Report the slices, not the pooled 2.4%.** The failures concentrate in deliberately-exotic files —
`black` alone contributes 11 of 32, all from its own syntax-edge-case corpus (`pep_654.py`,
`type_params.py`, `type_param_defaults.py`). Those are *valid modern Python* that a 3.10 interpreter
cannot parse, so they measure the interpreter's age rather than PyCG's quality.

Tracebacks for every failure: `$TW_DATA/pycg/py<ver>/pycg_failures.jsonl`.
Reproduce: `python3 scripts/pycg_parse_rate.py clone && … measure --pyver 3.10`.

## 2.2 The static-extraction image, and its one unpinned component (added 1.3)

Both baselines' tools live in **one** image, `traceweave-static:latest`, built by
`static/build_image.sh` from the digest-pinned `python:3.10-slim` of §6. One image rather than two
so a reader can name a single artifact that produced both halves of `S`.

Python **3.10**, not 3.12, and not a repo's triaged `pyver`: §2.1 — PyCG 0.0.8 does not run on 3.12
at all. Our own AST inventory therefore runs on the **host's** newest interpreter and never inside
this image, so nothing in the image has to parse contemporary syntax.

| Component | Pinned by | Notes |
|---|---|---|
| base image | `config/base_images.json` digest, resolved per platform | never hardcoded in the Dockerfile — an amd64 pin silently emulates on arm64 and invalidates timings |
| PyCG | `pycg==0.0.8` + the §2.1 symlink shim | |
| Pyright | `pyright@1.1.411` (npm) | the npm package ships its own bundled JS, so the container needs no network at run time |
| **node** | **NOT pinned** — comes from the base image's Debian repos | The one floating component. `static/build_image.sh` records the resolved version into `static/image_provenance.json` beside the image id, and `extract.py` copies that into every repo's record, so a rebuild that moves node is visible in the artifact instead of invisible in the results. Recorded on the manager host 2026-08-17: **node v20.19.2**. |

`build_image.sh` builds with `--provenance=false --sbom=false`: buildx otherwise exports an OCI
image *index* with attestation manifests, and `docker image inspect` then exits non-zero on a tag
that is present and working — which reads to every preflight check as "the image is not built".

---

## 3. Repo identity

A corpus repo is identified by the **5-tuple**:

```
(repo_url, sha, pyver, base_image_digest, lockfile_sha256)
```

All five are mandatory. A repo missing any one of them is not in the corpus.

- `sha` — resolved commit. ins1 v1.0 allowed an empty `sha` column; **v1.1 does not.** If the
  candidate sheet has no sha, the runner resolves and records `HEAD` at clone time.
- `lockfile_sha256` — sha256 of `pip freeze` output captured inside the container after a
  successful install. **This is amendment 1 and it is the single most important pin in the
  project.** Without it, PyPI resolution drift silently invalidates every trace and every one of
  ins2's "same both times" reproducibility claims.

### Node identity (frozen — see `docs/metric_spec_h2a.md`)

```
(repo_url, sha, relative_path, qualified_symbol)
```

**Line numbers are deliberately NOT part of node identity.** They move under formatting and
they differ between the static parse and the runtime frame. Lines are a *mapping hint* used to
disambiguate, never an identity component.

---

## 4. Corpus targets

| | Target | Floor |
|---|---|---|
| Candidates discovered & density-scored | ~450 | 300 |
| Triaged (automated) | all candidates | — |
| Green build + pinned lockfile | ~120 | 60 |
| **+ ≥3 replayable workloads (ins2)** | **~60** | **40** |
| — of which LOW stratum | ~15 | **10 (hard floor)** |
| — of which MED stratum | ~20 | 12 |
| — of which HIGH stratum | ~25 | 15 |

The **LOW floor of 10 is not negotiable**: LOW is the placebo arm for H2b-lite and the honesty
check for the entire paper. It is the last thing cut, not the first.

Corpus admission requires `status ∈ {GREEN, GREEN_AFTER_FIX, AMBER}` — **AMBER included**, per
amendment 2. H2a needs repos that *run*, not repos that *pass*.

---

## 5. What is deliberately NOT in this project

Recorded here so it is not relitigated mid-project. All are future work in the paper.

- Arm B (GNN / CGM-style graph-conditioned adapter)
- Java / Spring / JVMTI / ByteBuddy secondary track
- eBPF / strace system-telemetry layer
- End-to-end whole-repo migration, dependency-frontier ledger, interface-freeze contracts, rollback
- All of Direction 1 (no fine-tuning, no distillation corpus, no frontier oracle spend)

---

## 6. Change log

| manifest_version | date | change |
|---|---|---|
| 1.0 | 2026-07-27 | Initial. Base images + tool pins + identity tuples + corpus targets frozen. Pyright version outstanding. |
| 1.0 | 2026-07-27 | Added §1.1 environment constraints (Docker Desktop `/tmp` unmountable; bind-mount overhead ⇒ report ratios not absolutes). Density scorer calibrated and frozen at 4.0/10.0. |
| **1.1** | 2026-07-27 | **Added `linux/arm64` digests for all 5 images** (migration to Apple Silicon). `active_platform: auto` with daemon detection; `triage.sh` records `platform`/`host_arch`/`emulated` and warns on emulation. No amd64 digest changed — the 1.0 pins are preserved intact. |
| **1.3** | 2026-08-17 | **Phase 1 §1.2 built: `static/`, both baselines.** Added **§2.2** — the static-extraction image, and the fact that **node is its one unpinned component** (recorded per build, not assumed). **Retired the unused `tree-sitter-python 0.25.0` pin**: baseline 2 parses with CPython's `ast`, because node identity must equal `co_qualname` and tree-sitter would mean reimplementing exactly that (§2, `docs/static_extraction_spec.md`). No image digest and no tool pin changed, so `config/base_images.json` stays at `manifest_version 1.1`. §7: the ins1 amendment **shipped** as SOP v1.2 (`docs/sop_v1.2_changelog.md`), and the **redistribution gate is decided** — PERMISSIVE + non-archived, with the ins3 Part 1-R licence review run first; enforced by `runner.py`'s `redistribution_verdict()` as a field beside `admit`, never merged into it. |
| **1.2** | 2026-08-09 | **Pinned Pyright `1.1.411`** (published 2026-06-25), closing the last blank pin. Added **§2.1**: the **PyCG 0.0.8** sdist is unimportable on Linux and requires a `pycg`→`PyCG` symlink shim, and it does not run on Python 3.12 at all — so static extraction runs on ≤3.11 independently of a repo's triaged `pyver`. PyCG pin **unchanged**; measured parse-failure rate recorded per interpreter. **No image digest changed**, so `config/base_images.json` keeps `manifest_version 1.1` — it versions the image pins, and none moved. Host topology settled in `../MIGRATION.md` §4: Mac is the manager host, the x86_64 box is the execution host, and **the corpus is amd64**. |

## 7. Outstanding before Phase 1

- [x] Pin the **Pyright** version — `1.1.411`, published 2026-06-25. §2. Host `npm` turned out not to be on the critical path: Pyright is installed inside the image, and the registry answers over HTTPS.
- [x] Install **PyCG 0.0.8** in a dedicated container and measure its parse-failure rate on the reference set — `scripts/pycg_parse_rate.py`. **1.6% on library code under 3.10; 100% under 3.12, where it does not run at all.** Non-trivial as expected, and larger than expected. See §2.1.
- [x] `triage/runner.py` — parallel queue over the recipe ladder in `config/base_images.json`. Checkpoints every attempt before anything else happens, re-derives each outcome from the attempt log rather than trusting `triage.sh`'s `status`, computes corpus admission explicitly against §4 + amendment 2, and refuses to append to a ledger built on another architecture (§1, "one corpus, one architecture").
- [x] `scripts/discover_candidates.py` — candidate discovery to ~450 repos. Delivered **558 queued** (HIGH 135 / MED 177 / LOW 246), against a §4 target of ~450 and a floor of 300.

### Opened by the above, and outstanding

- [x] **`triage.sh` v1.2 is applied; ins1's allowed values are amended to match.** Shipped 2026-08-17 as **SOP v1.2** — `docs/sop_v1.2_changelog.md` amends ins1 §5 (columns and allowed values) and §8 (when something goes wrong). `error_class` gains `OOM` / `TIMEOUT` / `KILLED`, `n_failing` gains `collect_partial`, and a killed run is `RED` with `n_failing=na`, never `AMBER`. `scripts/validate_sheet.py` now gates the new vocabulary on **the row's own `sheet_version`** rather than on a `--v12` flag, which enforces the amendment and the no-pooling rule below in one check. `make_operator_sheets.py` stamps ins1 sheets `v1.2` (ins2/ins3 stay `v1.1` — the amendment touches ins1 only); `runner.py` records `v1.2`.
- [ ] **Re-run the 10% human-vs-classifier audit entirely under v1.2.** v1.1 and v1.2 rows are not comparable on the three new classes, because under v1.1 the machine could not emit them at all. The 14 returned spot-check rows stay v1.1 evidence and must not be pooled with the 558. **Human task; blocked on operator time, not on code.**
- [x] **`redistribution_class` gates corpus admission — decided 2026-08-17.** The release ships repo source, so a corpus repo must be redistributable. **Admission requires `redistribution_class = PERMISSIVE` and `archived = False`**, and the ins3 Part 1-R licence review (`handoff/ins3_part1R_licence_review_91.csv`, already generated) runs **before** admission so `REVIEW_NEEDED` rows are resolved rather than discarded.

  Why in that order — the queue as scored:

  | stratum | queued | PERMISSIVE | PERMISSIVE + non-archived | + REVIEW_NEEDED resolved | §4 floor | survival needed |
  |---|---|---|---|---|---|---|
  | HIGH | 135 | 87 | **82** | 105 | 15 | 11.1% → 18.3% → **14.3%** |
  | MED | 177 | 132 | 127 | 149 | 12 | 6.8% → 9.4% → **8.1%** |
  | LOW | 246 | 180 | 176 | 218 | 10 | 4.1% → 5.7% → **4.6%** |

  The 567 `REVIEW_NEEDED` rows are 386 `NONE_FOUND` + 181 `OTHER`, i.e. mostly a missing licence file rather than a restrictive one — which is exactly what a human resolves cheaply and a script cannot. Gating without the review first would raise HIGH's required survival to 18.3% by discarding rows nobody has read. `COPYLEFT` (179 GPL) and `WEAK_COPYLEFT` (20 LGPL/MPL) repos stay in the **feasibility survey**, which reports on repos it does not redistribute, so their triage and tracing outcomes are not lost.

---

## 8. Phase 1 §1.2 — what is built, and what it is pinned to (added 1.3)

`static/` produces `S(r)` for both baselines. Design decisions and the direction each one biases
the result: **[`docs/static_extraction_spec.md`](docs/static_extraction_spec.md)**. Node and edge
definitions remain frozen in `docs/metric_spec_h2a.md`; nothing in `static/` may change them.

| | |
|---|---|
| **extraction_version** | `1.0` |
| **image** | `traceweave-static:latest`, §2.2. Its `image_provenance.json` is copied into every repo's record. |
| **PyCG seed policy** | `PYTHONHASHSEED ∈ {0, 1, 42}`; `S` is the **union of the runs that completed**, with the per-seed spread recorded. Not an implementation detail: PyCG's fixpoint iterates over sets, so without a seed policy "PyCG's graph for repo R" is not a value (`scripts/pycg_determinism.py`). Union gives the published baseline maximum credit, so a high miss rate cannot be answered with "you picked its worst run". |
| **universe** | The repo's own package code. `tests/` is excluded by default and the choice is recorded per repo as `include_tests`, because it moves the denominator. §2.1's first condition (both endpoints in-repo) is what makes a test→library call out-of-universe rather than a miss. |
| **artifacts** | `$TW_DATA/static/<repo>/{inventory,callsites,pycg,pyright,summary}.json` + an append-only `ledger.jsonl`. Resumable; a repo where one baseline failed is recorded `partial` and **is retried**, so a PyCG OOM is never mistaken for a finished repo. |
| **guards** | `tests/test_static.py`, 39 checks, wired into `tests/run_checks.sh` as check 7. Asserted on click as well as on fixtures — every invariant in there, when it broke, silently *deleted* edges rather than raising. |

**Validated on the manager host** (arm64, `--seeds 0,42`; development output, **not** corpus records
— §1 and `../MIGRATION.md` §4 put the corpus on the x86_64 box):

| repo | callable nodes | call sites | PyCG `S` | Pyright `S` | Jaccard | unresolved sites |
|---|---|---|---|---|---|---|
| chardet | 102 | 722 | 141 | 123 | 0.808 | 128 |
| click | 540 | 2129 | 448 | 567 | 0.564 | 162 |
| toolz | 457 | 585 | 111 | 122 | 0.494 | 55 |

The two baselines disagree substantially, which §1.2 of the plan anticipated and asked to be
reported. Two PyCG behaviours already documented in `docs/` reproduced themselves through the new
harness: on **click** seed 0 was OOM-killed while seed 42 completed, and on **chardet** the two
seeds returned different graphs. Both are recorded per repo rather than smoothed over.
