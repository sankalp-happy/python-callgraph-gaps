# TraceWeave-Core

**Measuring what static call-graph extraction misses on real Python repositories — and releasing the benchmark that lets anyone re-measure it.**

| | |
|---|---|
| **Started** | 2026-07-27 |
| **Deadline** | ~2026-10-26 (12 weeks) |
| **Staffing** | 1 engineer + 2–3 annotators |
| **Current state** | **Phase 0 complete.** Phase 1 not started. |
| **Approved plan** | `~/.claude/plans/given-the-convo-history-cheerful-pizza.md` |
| **Parent research doc** | `../research_plans.md` (Direction 2) |
| **Underlying review** | `../final_paper.pdf` |

---

## Table of contents

1. [What this project claims](#1-what-this-project-claims)
2. [How we got here — the decision log](#2-how-we-got-here--the-decision-log)
3. [The 12-week plan](#3-the-12-week-plan)
4. [Repository layout](#4-repository-layout)
5. [Prerequisites and two hard environment constraints](#5-prerequisites-and-two-hard-environment-constraints)
6. [How to use each tool](#6-how-to-use-each-tool)
7. [The data root](#7-the-data-root)
8. [The five SOP amendments and the human reallocation](#8-the-five-sop-amendments-and-the-human-reallocation)
9. [What is frozen, and how to change it](#9-what-is-frozen-and-how-to-change-it)
10. [Findings log](#10-findings-log)
11. [What is not built yet](#11-what-is-not-built-yet)
12. [Health checks](#12-health-checks)
13. [Troubleshooting](#13-troubleshooting)
14. [Glossary](#14-glossary)

---

## 1. What this project claims

The systematic review in `../final_paper.pdf` (§VIII.B) identifies static graph quality as a
bottleneck for repository-level code modernization: dynamic languages and dynamic features break
graph extraction, and the review argues "the bottleneck is therefore graph construction and the
amount of information that can be represented."

**The hypothesis we test (H2a):**

> Static call-graph extraction misses a substantial fraction of the call edges that actually occur
> at runtime on real Python repositories, and the misses concentrate in identifiable construct
> classes (reflective dispatch, dynamic imports, plugin/DI registration) rather than being diffuse.

This is deliberately a measurement **of programs, not of models**. Whatever number comes back is a
publishable fact. It requires no frontier-model baseline whose pricing and capability will move
under us, and no fine-tuning spend. If the number is small, that is *still the paper* — "static
extraction is more complete than the field assumes, except at these specific constructs" is a
useful, publishable negative result.

**We do not pre-commit to a threshold.** `research_plans.md` phrases H2a as "≥25%". A 14% miss rate
concentrated entirely in dependency-injection sites is a **better** result than a diffuse 30%,
because it names a mechanism. The conditional claim is the strong one.

**Secondary deliverables** — DynBench-Core (pinned repos + replayable workloads + reference edge
sets + harness), a tracing-feasibility survey, and one bounded downstream experiment (H2b-lite)
showing the missing edges change task outcomes.

---

## 2. How we got here — the decision log

### 2.1 Why Direction 2, not Direction 1

`research_plans.md` proposes two 40-week programs. Its own sequencing note recommends running
Direction 1 (GRAFT — small-model migration with deterministic scaffolding) first, on the grounds
that D1's infrastructure is ~70% reusable by D2.

We chose **D2 first**, for three reasons that outweigh the reuse argument:

1. **D2 has a guaranteed floor; D1 does not.** H2a is a measurement. D1's headline is a
   *comparative* claim (14B + scaffold vs. frontier + naive retrieval at <10% cost) whose truth
   depends on a frontier baseline and an API price curve that will both move before submission.
2. **H2a de-risks D1 cheaply.** If static graphs turn out near-complete, D2 dies for ~$0 in oracle
   spend and D1 learns its k-hop CPG slice is a sound substrate. If they miss 30%, D1 learns its
   slices are silently lossy. Nothing in D1's early milestones returns comparable information
   about D2.
3. **Cost asymmetry.** D2's primary arm needs no fine-tuning and no distillation corpus. D1 gates
   on a frontier-oracle run across training repos plus QLoRA — the single largest irreversible
   spend, committed *before* knowing whether the representation being fed to the model is adequate.

The reuse argument is also weaker than it looks: D2's dependency-frontier ledger, interface-freeze
contracts and rollback machinery are only needed for *end-to-end whole-repo migration*. H2a needs
none of it.

### 2.2 The four scoping answers

| Question | Answer | Consequence |
|---|---|---|
| Deadline | **3 months** | The 40-week D2 plan does not fit. We deliver ~30% of it, chosen so the 30% is a self-contained paper rather than a third of every milestone. |
| Staffing | 2–3 annotators + 1 engineer | ins2 becomes the bottleneck by design; ins1 gets automated to free people for it. |
| Corpus language | **Python**; ins3 Part 2 vestigial | ins3's port-search was inherited from D1's Java→Python contamination screen and is meaningless for a Python corpus. Deleted. |
| Scope | **D2 only**, D1 as future work | No fine-tuning, no oracle spend, no distillation corpus. |

### 2.3 What is explicitly out of scope

Recorded so it is not relitigated mid-project. All become "future work" in the paper.

- **Arm B** (GNN / CGM-style graph-conditioned adapter) — needs compute and time we lack.
- **Java / Spring / JVMTI / ByteBuddy** secondary track — a second full toolchain.
- **eBPF / strace** system-telemetry layer — language-level audit hooks cover env/subprocess/socket adequately.
- **End-to-end whole-repo migration**, dependency-frontier ledger, interface-freeze contracts, transactional rollback.
- **All of Direction 1.**

### 2.4 The insight that shaped Phase 0

The three `ins*.md` files are **not separate work** — they already *are* Direction 2's M0:

| SOP | What it produces | What H2a needs it for |
|---|---|---|
| `ins1.md` | Build triage → GREEN/AMBER/RED + failure taxonomy | Repos that install and run; the feasibility survey |
| `ins2.md` | ≥3 replayable workloads per repo, exit codes verified twice | **The execution oracle.** Every dynamic edge's provenance points to a replayable workload ID |
| `ins3.md` | Licence, stars, and env vars mentioned in docs | Artifact-release clearance; `EnvNode` seeds; the documentation-gap finding |

They are well-written, and the human process is a genuine QA layer. Phase 0 changed **allocation,
pinning, and stratification** — not their substance.

---

## 3. The 12-week plan

| Phase | Weeks | Deliverable | Status |
|---|---|---|---|
| **0** | 1 | Freeze rules, amend SOPs, stratify the queue | ✅ **complete** |
| **1** | 2–4 | Automated triage at scale + two static extractors | ⬜ next |
| **2** | 3–6 | Tracer (`sys.monitoring` + fallback) + normalization to Parquet | ⬜ |
| **3** | 5–8 | Trace→node mapping, fusion, **the H2a numbers**, GO/NO-GO | ⬜ |
| **4** | 8–11 | H2b-lite + H2c-lite — one bounded, pre-registered experiment | ⬜ |
| **5** | 10–12 | DynBench-Core release + writing | ⬜ |

**The Week 8 seam is deliberate.** H2a + DynBench + the feasibility survey is already a complete
paper. Phase 4 is additive by construction.

**Cut order if 12 weeks slips (decided in advance):** H2c-lite → Phase 4 entirely → the LOW
stratum beyond its floor of 10. **Never** cut the placebo arm while keeping Phase 4, and **never**
cut pinning.

---

## 4. Repository layout

```
traceweave/
├── README.md                     ← this file
├── MANIFEST.md                   ← THE reproducibility anchor. Read first.
│                                   Base-image digests, tool pins, identity tuples,
│                                   corpus targets, environment constraints (§1.1),
│                                   outstanding-before-Phase-1 checklist (§7).
│
├── config/
│   └── base_images.json          ← 5 pinned image digests + the ins1 recipe ladder
│                                   as executable policy. Machine-readable source of
│                                   truth; MANIFEST.md §1 is its human mirror.
│
├── docs/
│   ├── metric_spec_h2a.md        ← PRE-REGISTRATION, frozen 2026-07-27 before any
│   │                               extraction code existed. Defines node identity,
│   │                               what counts as a call edge, the comparable
│   │                               universe, recall vs. the thing we refuse to call
│   │                               precision, and the threats it pre-empts.
│   ├── density_scorer_spec.md    ← Calibration record. Observed distribution on 14
│   │                               reference repos, the four false-positive classes
│   │                               found and fixed, frozen thresholds, feature weights.
│   └── sop_v1.1_changelog.md     ← ANNOTATOR-FACING. Hand this to the team. Written
│                                   in the register of the ins*.md files.
│
├── scripts/
│   ├── density_score.py          ← AST-based dynamic-feature scorer → LOW/MED/HIGH
│   ├── github_meta.py            ← replaces ins3 Part 1 via the GitHub REST API
│   └── workload_shell.sh         ← opens the certified environment for ins2 capture
│
└── triage/
    └── triage.sh                 ← v1.1: one repo, one Python version, one attempt
```

Nothing here is generated. Every file is hand-authored and every pin in it was resolved by
querying the real registry or a real API, not guessed.

---

## 5. Prerequisites and two hard environment constraints

### Prerequisites

| Need | Verified present | Note |
|---|---|---|
| Docker | 29.5.3, context `desktop-linux` | Docker **Desktop** — see constraint 1 |
| git | 2.34.1 | |
| python3 (host) | 3.10.12 | Used only to *drive* containers — see constraint 2 |
| jq | present | convenience only |
| disk | 345 GB free | corpus + traces will want most of it |
| cores / RAM | 16 / 38 GB | supports ~6–8 concurrent triage jobs |
| `GITHUB_TOKEN` | **not set** | optional; lifts API limit 60/hr → 5000/hr |

### Constraint 1 — Docker cannot bind-mount `/tmp`

Verified: `$HOME` and its subdirectories mount fine; `/tmp` is refused with
`mounts denied: … not shared from the host`.

Triage, workload capture and tracing **all** depend on bind-mounting a repo working copy into a
container. Therefore **every corpus path must live under `$HOME`.** ins1 v1.0's use of
`~/triage/work` was correct and is preserved as `~/traceweave-data/`.

> If you put anything in `/tmp`, it will fail at the `docker run` with a mounts-denied error.

### Constraint 2 — the host is Python 3.10; all analysis runs in containers

`sys.monitoring` (PEP 669) requires Python 3.12+. Two consequences:

- **The tracer never runs on the host.** It runs inside the pinned container.
- **The density scorer must also be run containerised.** On the 3.10 host it cannot parse 3.11+
  syntax (`except*`, PEP 695 type parameters) and would *silently undercount* those files.
  §6.1 shows the correct containerised invocation.

### Constraint 2b — a methodological consequence, recorded so it is not published wrongly

Docker Desktop runs containers inside a VM, so bind-mount I/O is materially slower than native.

- **Absolute** wall-clock timings from this host are inflated and must **not** be published as
  representative of native execution.
- **Ratios** (traced ÷ untraced, measured under identical mount conditions) cancel the mount
  penalty. The plan already specifies tracer overhead as a ratio against ins2's untraced baseline,
  so this is consistent — but the reason is written down so nobody later reports raw seconds as an
  overhead figure.
- Where an absolute number is unavoidable, re-measure with the repo copied *into* the image rather
  than bind-mounted, and label it separately.

---

## 6. How to use each tool

All commands assume you are in the repo root (`traceweave/`), with `$IMG` resolved to the pinned
3.12 image **for your platform**:

```bash
IMG="$(python3 scripts/resolve_image.py 3.12)"
echo "$IMG"
```

**Never hardcode a digest.** `config/base_images.json` carries both `linux/amd64` and
`linux/arm64`; `scripts/resolve_image.py` is the single source of truth and picks the one matching
your Docker daemon. Hardcoding the amd64 pin on an arm64 host emulates silently — it still
*works*, which is exactly why it is dangerous: every wall-clock number becomes meaningless while
the results look fine.

`triage.sh` and `workload_shell.sh` do this resolution internally, so you only need `$IMG` for the
ad-hoc `docker run` invocations below.

### 6.1 `scripts/density_score.py` — assign a repo its stratum

Scores dynamic-feature density from the AST and returns LOW / MED / HIGH / TOO_SMALL. This gates
corpus admission (amendment 3), so it must run **before** triage.

**Run it containerised.** Do not run it on the host.

```bash
docker run --rm --network=none \
  -v "$HOME/traceweave-data/refrepos":/repos:ro \
  -v "$PWD/scripts":/s:ro \
  "$IMG" python3 /s/density_score.py /repos/flask --repo-url https://github.com/pallets/flask
```

Emits JSON on stdout:

```json
{
  "spec_version": "1.0",
  "density_score": 16.74,
  "stratum": "HIGH",
  "source":  { "features": {...}, "frameworks": ["celery","flask"], "sloc": 7385, "parse_failures": 0 },
  "tests":   { "...": "scored separately, does NOT affect the stratum" },
  "thresholds": { "low_med": 4.0, "med_high": 10.0 }
}
```

**Reading the output:**

| Field | Meaning |
|---|---|
| `density_score` | Weighted dynamic-feature hits per KLOC of **source**, plus 1.5 per framework. **This continuous score is the primary analysis covariate** — miss-rate is regressed on it. |
| `stratum` | LOW `<4.0`, MED `4.0–10.0`, HIGH `≥10.0`, or `TOO_SMALL` (<500 source SLOC). Bins exist for *sampling balance* and readable table strata. **A bin boundary is not a claim about a repo.** |
| `source` vs `tests` | Scored separately, and the stratum comes from **source only**. Test suites use `getattr`/`mock`/`monkeypatch` for reasons unrelated to the repo's architecture; scoring them together made every pytest-using project look HIGH. |
| `parse_failures` | Files the parser could not read. Should be ~0 on 3.12. Non-zero on the host is a symptom of constraint 2. |

**Three design rules to know before you touch the weights:**

- `getattr(o, "literal")` is weighted **0.3**; `getattr(o, name)` is **2.0**. The literal form is
  statically resolvable and is *not* a blind spot. Conflating them is the commonest way to
  overstate dynamic density.
- Builtin-derived features require an **unqualified** call. `re.compile` is not `compile`.
- The per-KLOC denominator is **floored at 1000 SLOC**. Below 1 KLOC, per-KLOC *amplifies* rather
  than normalises (a 29-line fixture scored 701 before the floor).

### 6.2 `triage/triage.sh` — does one repo install and run?

One repo, one Python version, one attempt. The recipe ladder and parallelism belong to
`runner.py` (not yet built — §11).

```bash
cd triage
./triage.sh <github-url> [commit-sha|none] [python-version]

# examples
./triage.sh https://github.com/pallets/click
./triage.sh https://github.com/pallets/click 00e592ce 3.11
```

Environment overrides: `TW_DATA` (default `$HOME/traceweave-data`), `TW_CONFIG` (default
`../config/base_images.json`).

**Prints the v1.0 RESULT block verbatim** — unchanged so the 10% human-vs-script audit compares
like with like:

```
----------------------------------------
RESULT: BUILD_OK TESTS_OK
LOG:    /home/…/traceweave-data/out/click/py3.12/attempt.log
----------------------------------------
```

**Writes three artifacts** to `~/traceweave-data/out/<name>/py<ver>/`:

| File | Contents |
|---|---|
| `result.env` | flat `KEY=VALUE`, no embedded newlines — parse this, never the log |
| `attempt.log` | full transcript with `###MARKER###` lines |
| `lock.txt` | `pip freeze` of the resolved environment — **amendment 1, the critical pin** |

A real `result.env`:

```ini
sheet_version=v1.1
repo_url=https://github.com/pallets/click
pyver=3.12
pinned_ref=python@sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
image_digest=sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
sha_requested=none
sha_resolved=00e592cea702e0b2caa0dee42489fdb1c22cd845     # auto-resolved; mandatory in v1.1
seconds_clone=4
seconds_build=89
lock_sha256=10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
lock_pkgs=9
python_full=3.12.13
n_collected=1965
status=GREEN
error_class_v10=NONE
error_class_v11=NONE
n_failing=0
result_line=BUILD_OK TESTS_OK
seconds_total=93
```

**Status values and what they mean for the corpus:**

| `status` | Meaning | Corpus-eligible? |
|---|---|---|
| `GREEN` | installs, collects, all tests pass | ✅ |
| `AMBER` | installs and runs, but tests fail or collection fails | ✅ **yes** — amendment 2 |
| `RED` | did not build | ❌ but stays in the feasibility survey |

> **`AMBER` counts.** H2a needs repos that **run**, not repos that **pass**. A failing test still
> executes code, which is exactly what the tracer watches. Excluding AMBER would have discarded an
> estimated 20–40% of a usable corpus.

**Two `error_class` columns, on purpose.** ins1 v1.0's classifier tests the `python_requires`
pattern **first and unconditionally**, so any repo whose metadata merely *mentions* it is labelled
`PYTHON_VERSION` regardless of the real failure. `error_class_v10` preserves that behaviour
verbatim (the audit needs comparability); `error_class_v11` reorders most-specific-first and
requires the version pattern to co-occur with an actual failure. `classifier_disagree=yes|no` is
recorded per repo — **their disagreement rate is a reportable number, not a bug to hide.**

### 6.3 `scripts/workload_shell.sh` — open the certified environment (for ins2)

Replaces ins2 v1.0 Step 3's hand-typed install block.

```bash
./scripts/workload_shell.sh <repo-name> [pyver]
./scripts/workload_shell.sh                    # no args: lists triaged repos
```

It auto-detects which Python version triage actually succeeded on (GREEN **or** AMBER), opens that
exact pinned image, installs from `lock.txt` with `--no-deps`, and drops you at a shell in `/repo`.

It prints the three values annotators must copy into every workload YAML:

```
 pyver:              3.12
 base_image_digest:  sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
 lock_sha256:        10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
```

**Why this exists.** If workload capture resolves its own dependencies from PyPI, then triage,
workload capture and tracing each run a *different* dependency set and none of the three can be
compared. This one command is what keeps them identical. It is the whole point of amendment 1.

### 6.4 `scripts/github_meta.py` — replaces ins3 Part 1

```bash
export GITHUB_TOKEN=ghp_…                     # optional: 60/hr → 5000/hr
python3 scripts/github_meta.py urls.txt --out meta.jsonl
python3 scripts/github_meta.py --url https://github.com/psf/requests
```

Emits one JSON object per repo using **ins3 §6's exact vocabulary**, so rows drop straight into the
sheet: `licence ∈ {MIT, Apache, BSD, GPL, LGPL, MPL, PUBLIC_DOMAIN, NONE_FOUND, OTHER}`.

Validated against ins3 §2's own qualification check — requests → `Apache`, click → `BSD`,
django → `BSD`. All three match.

**It is ~90% automatable, not 100%.** For roughly 1 repo in 10 GitHub returns `NOASSERTION` and the
script writes `OTHER`. Example: `celery` comes back `OTHER` although it is really BSD-3-Clause,
because its licence file has an unusual preamble. Those rows — and only those — go to a human for a
~30-second check per ins3 §3's table.

Also emits `redistribution_class ∈ {PERMISSIVE, WEAK_COPYLEFT, COPYLEFT, REVIEW_NEEDED}` so the
DynBench release decision is explicit rather than accidental. `ansible` is GPL; we publish
metadata, edge sets and workload YAMLs rather than source, but the flag makes that a decision
rather than an oversight.

`port_exists` is emitted as `NA_V11` — the column is retained so the sheet schema stays stable, and
the value makes the deletion explicit rather than looking like an omission.

---

## 7. The data root

Everything mutable lives at `$HOME/traceweave-data` (**not** in this repo, and **not** in `/tmp` —
constraint 1).

```
~/traceweave-data/
├── candidates/          discovery + density output, the stratified queue
├── refrepos/            14 shallow clones used to calibrate the scorer (250 MB)
├── work/<name>/         live working copy, bind-mounted into containers
├── out/<name>/py<ver>/  result.env + attempt.log + lock.txt   ← the durable record
├── logs/                runner-level logs
└── traces/              Phase 2 output (Parquet)
```

### Repo identity — the mandatory 5-tuple

```
(repo_url, sha, pyver, base_image_digest, lockfile_sha256)
```

**All five are required. A repo missing any one is not in the corpus.** ins1 v1.0 allowed an empty
`sha`; v1.1 does not — the runner resolves and records `HEAD` at clone time.

`lockfile_sha256` is the single most important pin in the project. Without it, PyPI resolution
drift silently invalidates every trace and every one of ins2's "same both times" claims.

### Node identity — frozen

```
(repo_url, sha, relative_path, qualified_symbol)
```

**Line numbers are deliberately not part of identity.** They move under reformatting and differ
between the static parse and the runtime frame. Lines are a disambiguation *hint* only.

### Corpus targets

| | Target | Floor |
|---|---:|---:|
| Candidates discovered & scored | ~450 | 300 |
| Green build + pinned lockfile | ~120 | 60 |
| **+ ≥3 replayable workloads** | **~60** | **40** |
| — LOW stratum | ~15 | **10 (hard)** |
| — MED stratum | ~20 | 12 |
| — HIGH stratum | ~25 | 15 |

**The LOW floor of 10 is not negotiable.** LOW is the placebo arm for H2b-lite and the honesty
check for the whole paper. It is the last thing cut, not the first.

---

## 8. The five SOP amendments and the human reallocation

Hand `docs/sop_v1.1_changelog.md` to the annotators. Summary:

| # | Amendment | Why it was urgent |
|---|---|---|
| **A1** | **Pin the environment.** Emit `pip freeze` lockfile + image **digest** (not tag) + resolved `pyver` for every non-RED repo. | `python:3.12-slim` is a moving tag and PyPI resolves differently week to week. Every trace, and ins2's entire reproducibility premise, silently rots without this. Cheap now; a re-do of 300 annotated repos later. |
| **A2** | **Stop discarding AMBER.** ins2's input becomes `GREEN ∪ GREEN_AFTER_FIX ∪ AMBER`. | H2a needs repos that *run*, not repos that *pass*. ins2 §4 already accepted exit code 1 when tests genuinely ran. |
| **A3** | **Stratify before triage.** Density scorer gates entry to Sheet 1; rows interleaved by bin. | ins1 works strictly top-to-bottom. Unstratified input ⇒ bin distribution is whatever chance gives, and the HIGH stratum comes out thin — the exact risk `research_plans.md` §D2.3 names. |
| **A4** | **ins3: Part 2 deleted, Part 1 automated, Part 3 starts now.** | Part 2 searched for Python ports of Python repos — meaningless, inherited from D1's Java→Python screen. Part 1 is three fields an API returns exactly. Together ~30 person-days returned. |
| **A5** | **Exact seconds, not rounded to 5.** | `duration_s` is the denominator for tracer-overhead ratios. Rounding a 3-second command to 5 makes that measurement meaningless. |

### The reallocation — the biggest schedule lever

**ins1's loop was already a script:** run `triage.sh`, read the RESULT line, look it up in a fixed
table, apply a fixed recipe. A queue runner reproduces every step with no 12-minute timebox and no
inter-annotator disagreement.

**ins2 is the opposite** — reading prose READMEs, deciding whether a grey box is a runnable command,
finding the demo script nobody linked. Irreplaceably human, and the true bottleneck for H2a.

So: **automate ins1, move all annotators to ins2.** At the SOP's 15 repos/week/person, 3 people
reach a 60-repo corpus in ~2 weeks of steady state instead of ~4 weeks serialized behind triage.

**The 10% double-coding is repurposed, not dropped.** Instead of annotator-vs-annotator, one
annotator manually triages a 10% sample and it is compared against the automated classifier. That
converts a QA metric into a *reportable validation of automated triage* — which the paper needs
anyway. Annotators are told **not** to guess what the script said; a disagreement they found is
worth more than an agreement they produced.

---

## 9. What is frozen, and how to change it

Three documents are frozen. They were written **before** the code that consumes them, which is what
makes the eventual number a measurement rather than a search.

| Frozen | Version | To change it |
|---|---|---|
| `docs/metric_spec_h2a.md` | `1.0` | Bump `spec_version`, add a dated §9 entry, **re-run everything**. Never a silent edit. |
| `docs/density_scorer_spec.md` + the thresholds in `density_score.py` | `1.0` | Same discipline. Thresholds were calibrated **once**, during Phase 0, before any corpus admission or H2a measurement. |
| `config/base_images.json` / `MANIFEST.md` | `1.0` | Append a new dated entry; keep the old one. Never edit a digest in place. |

**Analysis discipline, pre-committed:**

- No threshold or definition may be tuned after seeing H2a results.
- Aggregates always accompanied by per-stratum and per-edge-type breakdowns; a mean is never shown alone.
- Any excluded repo is listed with a reason. **Silent drops are forbidden** — they create survivorship bias in DynBench. `trace-failed` repos stay in the release with a status.
- **No LLM-as-judge** anywhere in validation or headline metrics. LLM judgment is permitted only in failure *analysis*, clearly marked.

**Two definitional choices worth internalising** (full reasoning in `metric_spec_h2a.md`):

1. **C/builtin and third-party calls are excluded from the primary denominator.** Static tools do
   not model them at all; including them would produce an enormous "miss rate" that is purely an
   artifact. This is the easiest way to accidentally fabricate a headline number, so it is
   excluded by construction.
2. **We never call `|S∩R|/|S|` "precision".** A static edge not observed at runtime may be a
   genuine edge no workload exercised, or a real over-approximation — and traces cannot separate
   those. It is labelled *workload-confirmed fraction* everywhere. Genuine precision comes only
   from the manual audit, with its sample size, and is never extrapolated to a headline.

---

## 10. Findings log

Seven things discovered by *running* Phase 0 rather than planning it.

1. **Docker Desktop cannot bind-mount `/tmp`.** All corpus paths moved under `$HOME`. ins1's
   `~/triage/work` was right all along. Methodological consequence recorded in `MANIFEST.md` §1.1:
   bind-mount I/O on Desktop is slow, so absolute overhead numbers would be inflated — publish
   ratios.
2. **The density scorer's first run was useless** — 10 of 14 repos landed HIGH, no discrimination.
   Four false-positive classes, all fixed before freezing:
   - `re.compile` counted as `eval_exec` at weight 3.0 (drove `requests` to a spurious HIGH)
   - `@t.overload` / `@v.setter` counted as registry decorators (`click` scored 16.4/KLOC on pure typing machinery)
   - `importlib.metadata` mislabelled as a framework, giving nearly every repo a spurious +1.5
   - `sys.modules` counted on bare reads, not just mutation
3. **The scorer corrected two of my a-priori labels, and it was right.** I expected `requests` to
   be LOW; it scores mid-range because it genuinely does
   `locals()[package] = __import__(package)` and `importlib.import_module(lib)` in its compat
   layer — precisely the edge class H2a is about. `toolz` similarly uses `globals()` in `curry`.
   Reported rather than quietly reconciled; it is mild evidence the metric tracks something real.
4. **PyCG's latest release is 0.0.8** and years old. It parses with the host `ast`, so modern
   syntax may crash it. Rather than hide this, its **parse-failure rate becomes a reported
   metric** — how often the field's standard static baseline cannot read contemporary Python is a
   completeness result about the state of the art.
5. **ins3 Part 1 is ~90% automatable, not 100%.** `NOASSERTION` for ~1 in 10 repos; `celery`
   returns `OTHER` when it is really BSD-3-Clause. Only those rows go to a human.
6. **ins1's classifier has an ordering bug** (`python_requires` tested first and unconditionally).
   Kept verbatim as `error_class_v10` for audit comparability; added a corrected
   `error_class_v11`; the disagreement rate is now measurable.
7. **`records` — one of ins2's own practice repos — is 495 source SLOC**, just under the 500 gate.
   `TOO_SMALL`, so corpus-ineligible despite triaging GREEN. Fine for practice. A useful reminder
   that build-green ≠ corpus-eligible.

**Verified working end-to-end:** `click` triaged GREEN in 93 s → 9-package lockfile with sha256 →
`workload_shell.sh` reproduced that exact environment → 1940 tests passed. `sha_resolved` was
auto-recorded even though the sheet supplied no sha.

---

## 11. What is not built yet

### Blocking Phase 1

- [ ] **Pin Pyright.** The npm version query returned only notices. Needed before static baseline 2.
- [ ] **Install PyCG 0.0.8** in a dedicated container and measure its parse-failure rate on the 14 reference repos. Expected non-trivial and itself reportable (finding 4).
- [ ] **`triage/runner.py`** — parallel queue walking the recipe ladder in `config/base_images.json`. ~6–8 concurrent jobs on this host. Must emit `result.json` aggregating each repo's ladder.
- [ ] **`scripts/discover_candidates.py`** — discovery to ~450 candidates, then density-score and interleave by bin into the stratified queue.

### Known gap worth fixing early

- [ ] **The regression fixtures are not durable.** The two guards in §12 currently read from `/tmp` and the session scratchpad, so they will vanish. Commit them as `tests/fixtures/false_positives.py` and `tests/fixtures/all_features.py` with a small runner. The *checks* pass; their *inputs* are not yet version-controlled.

### Later phases

Phase 2 tracer (`tracer/monitor.py`, `tracer/profile_fallback.py`, `tracer/hooks.py`), Phase 3
mapping and DuckDB store, Phase 4 slicer and task generator, Phase 5 release. See the approved plan
for the full file list.

---

## 12. Health checks

Run these before trusting anything. Both must pass.

```bash
cd /home/sankalp.shankar/Project/major/traceweave

# 1. No false positives: re.compile, @t.overload, @v.setter, bare sys.modules read
#    must together produce ZERO features.
mkdir -p /tmp/fp && cat > /tmp/fp/a.py <<'EOF'
import re, typing as t, sys
PAT = re.compile(r"x")
class C:
    @property
    def v(self): return self._v
    @v.setter
    def v(self, x): self._v = x
    @t.overload
    def f(self, a: int) -> int: ...
def g():
    return 1 if "os" in sys.modules else 0
EOF
python3 scripts/density_score.py /tmp/fp | python3 -c "
import json,sys; f=json.load(sys.stdin)['source']['features']
bad=[k for k in ('eval_exec','registry_decorator','sys_modules') if f.get(k,0)]
print('false-positive guard:', 'PASS' if not bad else 'FAIL '+str(bad))"

# 2. Licence mapping still reproduces ins3 §2's qualification answers
python3 scripts/github_meta.py \
  --url https://github.com/psf/requests \
  --url https://github.com/pallets/click \
  --url https://github.com/django/django 2>/dev/null | python3 -c "
import json,sys
EXP={'requests':'Apache','click':'BSD','django':'BSD'}
ok=all(json.loads(l)['licence']==EXP[json.loads(l)['repo_url'].split('/')[-1]] for l in sys.stdin)
print('ins3 §2 qualification:', 'PASS' if ok else 'FAIL')"
```

Recalibration sweep over the 14 reference repos (should give **6 HIGH / 4 MED / 3 LOW / 1
TOO_SMALL**) is in `docs/density_scorer_spec.md` §2, with the full expected table.

---

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `mounts denied: … not shared from the host` | You used a path outside `$HOME`. Constraint 1. Move it under `~/traceweave-data`. |
| `density_score.py` reports `parse_failures > 0` | You ran it on the 3.10 host. Constraint 2 — run it containerised (§6.1). |
| `FATAL: no pinned image for python X` | `X` is not in `config/base_images.json`. Add it *with a resolved digest*; never fall back to a tag. |
| `workload_shell.sh`: `no GREEN or AMBER triage attempt found` | Triage has not reached that repo, or it is RED. Note the `AMBER` in the message — AMBER is valid input (A2). |
| `triage.sh` hangs at `[2/4]` | Almost always a slow `pip install`. It has an internal 1800 s timeout; let it hit. |
| `WARNING: no GITHUB_TOKEN` | Works, but 60 requests/hour. `export GITHUB_TOKEN=…` for 5000. |
| `lock_pkgs=0` on a GREEN repo | `pip freeze` failed inside the container. Treat the repo as not-pinned and re-run; do **not** admit it to the corpus (§7, 5-tuple). |
| Disk filling up | `docker system prune -af` and clear `~/traceweave-data/work/*`. Weekly, per ins1 §8. |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **H2a** | The hypothesis this project measures: static extraction misses runtime call edges, concentrated in identifiable constructs. |
| **H2b-lite** | Phase 4's bounded downstream experiment: do the missing edges change task outcomes? Same slicer and prompts in both conditions; the *only* variable is which edges exist. |
| **H2c-lite** | Marking unobserved regions (`UnresolvedDispatch`) and measuring whether models honestly abstain instead of guessing. |
| **Placebo arm** | LOW-stratum / no-dynamic-edge cones, where H2b-lite predicts **no** improvement. A confirmed null is what converts "we added data and got better" into a causal representation claim. Pre-registered before running. |
| **DS-CPG** | Dual-State Code Property Graph — static and dynamic layers separately materialized, **fused on read** so static-only / dynamic-only / fused ablations stay possible. |
| **DynBench-Core** | The released artifact: pinned repos, workloads, reference edge sets, harness. Benchmarks outlive methods. |
| **Reference edge set (R)** | Union of call edges observed while executing all recorded workloads. **A lower bound, conditional on workloads** — this wording is mandatory in every metric definition, not just threats-to-validity. |
| **Comparable universe** | Edges where caller and callee are both in-repo, Python-level, statically representable. Excludes C/builtins, third-party, and phantom targets from the primary denominator. |
| **PhantomNode** | A runtime entity with no static counterpart (`eval`'d code, synthesized classes). Counted as its own, separate — and strong — claim. |
| **UnresolvedDispatch** | A statically unresolvable call site that no workload exercised. The honest unknowns. |
| **Wrapper transparency** | Collapsing `caller → decorator_wrapper → f` to `caller → f` for the primary metric, so decorators do not manufacture fake "misses". Specified before extraction. |
| **`fn_coverage`** | Fraction of static callable nodes activated at least once. Every recall figure is conditioned on it — a high miss rate at 8% coverage means something very different from the same rate at 70%. |
| **Stratum** | LOW / MED / HIGH by density score. For sampling balance and table readability; the **continuous score** is the analysis covariate. |
| **GREEN / AMBER / RED** | ins1 triage outcomes. GREEN and AMBER are both corpus-eligible; RED stays in the feasibility survey. |

---

*Phase 0 complete, 2026-07-27. Start Phase 1 at `MANIFEST.md` §7.*
