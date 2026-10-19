# TraceWeave-Core: a 12-week plan to a publishable H2a result + DynBench

## Context

**Why this plan exists.** `research_plans.md` lays out two 40-week research directions building on the systematic review in `final_paper.pdf`. The decision already taken is Direction 2 (TraceWeave) only, led by **H2a** — the claim that static CPG extraction misses a substantial fraction of true runtime call edges — because H2a is a measurement of *programs*, not of models: whatever number comes back is a publishable fact, it needs no frontier baseline and no fine-tuning spend, and it does not perish when the next model ships.

**The new binding constraint.** The deadline is ~3 months (today 2026-07-27 → **~2026-10-26**), staffed by 1 engineer (you) + 2–3 annotators. D2 as written is a 40-week program. This plan delivers ~30% of it, chosen so that the 30% is a *self-contained paper* rather than a third of every milestone.

**The three `ins*.md` files are already D2's M0.** They are not separate work — ins1 (build triage), ins2 (replayable workload capture), ins3 (background checks) produce exactly the assets H2a consumes: green-building repos, versioned replayable workloads with provenance IDs, and env-var seeds for `EnvNode`s. They are well-written and the human process is a real QA layer. What this plan changes is **allocation, pinning, and stratification** — not the SOPs' substance.

**Intended outcome.** One paper: an empirical study of static-vs-runtime call-graph completeness on Python repositories, with a released benchmark (DynBench), a tracing-feasibility survey, and a bounded downstream experiment showing the missing edges change task outcomes. Target: internal deadline late Oct 2026; external venue MSR 2027 (technical papers typically due ~Dec 2026/Jan 2027 — the timing lines up directly after the internal submission), with ISSTA/SANER as alternates.

---

## Scope decisions (explicit, so they are not relitigated)

**In scope**
- Python only. `sys.monitoring` primary tracer.
- H2a: static-vs-traced call-edge recall/precision, per stratum, per edge type.
- DynBench-Core: pinned repos + workloads + reference edge sets + harness.
- Tracing-feasibility survey (from the triage + tracing failure taxonomies).
- H2b-lite and H2c-lite: one bounded, pre-registered downstream experiment (Phase 4).

**Explicitly out of scope — state as future work in the paper**
- Arm B (GNN/CGM-style graph-conditioned adapter). Needs compute and time we do not have.
- Java/Spring/JVMTI/ByteBuddy secondary track. A second full toolchain.
- eBPF/strace system-telemetry layer. Language-level audit hooks cover env/subprocess/socket adequately for this paper.
- End-to-end whole-repo migration, the dependency-frontier ledger, interface-freeze contracts, transactional rollback. H2a/H2b-lite/H2c-lite do not need any orchestration.
- All of Direction 1 (no fine-tuning, no distillation corpus, no oracle spend).

---

## Phase 0 — Week 1 (Jul 27 – Aug 2): freeze rules, amend SOPs, stratify the queue

This week is the highest-leverage week in the plan. Everything here is cheap now and expensive-to-irreversible once annotators have processed 300 repos.

### 0.1 Five SOP amendments → reissue as `v1.1`

Bump `sheet_version` to `v1.1` and re-brief. In priority order:

1. **Pin the environment (critical).** Neither ins1 nor ins2 captures a resolved dependency set or an image digest. `python:3.12-slim` is a moving tag and PyPI resolves differently week to week. Every trace, and ins2's entire second-run reproducibility premise, silently rots without this. Amend `triage.sh` to emit, for every non-RED repo: `pip freeze > lock.txt`, the base image **digest** (`docker inspect --format='{{index .RepoDigests 0}}'`, not the tag), and the resolved `pyver`. These three become part of each repo's identity.
2. **Stop discarding AMBER.** ins2 §0 takes only `GREEN` and `GREEN_AFTER_FIX` rows as input. But H2a needs repos that *run*, not repos that *pass* — a failing test still exercises code paths, and ins2 §4 already accepts exit code 1 when tests genuinely ran. Excluding AMBER likely throws away 20–40% of a usable corpus we cannot afford to lose. Amend ins2's input to `GREEN ∪ GREEN_AFTER_FIX ∪ AMBER`.
3. **Stratify `candidates` before triage, not after.** ins1 §3 works strictly top-to-bottom. If the input list is not pre-binned, the bin distribution is whatever chance gives us and the HIGH stratum comes out thin — the exact risk `research_plans.md` §D2.3 names. A density scorer must gate entry to Sheet 1, and rows must be **interleaved by bin** so that stopping early still leaves balanced strata.
4. **ins3: drop Part 2, automate Part 1, keep Part 3.** Part 2 (hunting for Python ports) is vestigial from Direction 1's Java→Python contamination screen and is meaningless for a Python corpus — confirmed. Delete it; that alone returns ~6 min/repo. Part 1 (licence, stars, `last_commit_date`) is three fields the GitHub REST API returns exactly and instantly — script it, do not spend ~30 person-days reading sidebars. Keep Part 3 (env vars in docs) with grep assistance; it is the only genuine human-judgment part and it feeds both `EnvNode` seeds and a free bonus finding (§Bonus below).
5. **Record untraced wall-clock precisely.** ins2's `duration_s` "round to nearest 5" is too coarse to be the denominator for tracer-overhead numbers the paper must report. Record whole seconds via `time`.

### 0.2 Reallocate the humans — the biggest schedule win available

ins1's loop is *already a script*: run `triage.sh`, read the RESULT line, look it up in a fixed table, apply a fixed recipe. There is no judgment in it that a queue runner cannot reproduce, and a runner has no 12-minute timebox and no inter-annotator disagreement. ins2 is the opposite: reading prose READMEs, deciding what is a runnable command, finding demo scripts under `examples/` — irreplaceably human, and **it is the true bottleneck for H2a.**

- **Automate:** candidate discovery, density scoring, ins1 triage end-to-end (including Recipes 1–3 as retry logic), ins3 Part 1, env-var grep.
- **All 2–3 annotators → ins2 workload capture.** At the SOP's 15 repos/week/person, 3 people reach a 60-repo corpus in ~2 weeks of steady state instead of ~4 weeks serialized behind triage.
- **Keep ins1 §10's 10% double-coding — repurposed.** Instead of annotator-vs-annotator agreement, have one annotator manually triage a 10% sample and compare against the automated classifier. That converts a QA metric into a *reportable validation of automated triage*, which the paper needs anyway.
- **After ins2 saturates (~Week 6),** annotators move to the 5% reference-edge-set audit in Phase 3 — the two-annotator + Cohen's κ task that H2a's ground truth requires.

### 0.3 Pre-register the H2a metric spec, in writing, before any extraction

Written and timestamped in-repo now, frozen thereafter:
- What counts as a **call edge** (caller node → callee node; how bound methods, `super()`, decorators, comprehensions, and C-extension boundaries are treated).
- **Node identity keying** — `(repo, sha, relative_path, qualified_symbol)`. Line numbers are *not* part of identity (they move); they are a mapping hint only.
- Precisely what recall and precision mean against a **workload-conditional** reference set, and the exact wording that this is a lower bound. This wording goes in every metric definition, not only threats-to-validity.
- The per-edge-type breakdown to be reported: direct call, method call via inheritance, dynamic import, `getattr`/reflective dispatch, `eval`/`exec`, callback/registration, subprocess/IPC, env read.

### 0.4 Corpus sizing

Over-recruit 1.5× per D2's risk section: target **~450 candidates → ~60 repos** with green build + ≥3 replayable workloads. Interleaved LOW/MED/HIGH, with a floor of **≥10 in LOW** — LOW is the placebo arm in Phase 4 and the honesty check for the whole paper.

**Files created:** `MANIFEST.md`, `docs/metric_spec_h2a.md` (pre-registration), `docs/sop_v1.1_changelog.md`, `scripts/discover_candidates.py`, `scripts/density_score.py`.

---

## Phase 1 — Weeks 2–4: automated triage at scale + static extractor

### 1.1 Triage queue runner
Wrap ins1's existing `triage.sh` classifier logic — reuse its `classify()` regex taxonomy verbatim so automated and human results are comparable — into a parallel queue runner. Per repo emits: status, `error_class`, `lock.txt`, image digest, resolved `pyver`, full log. Recipes 1–3 become retry logic. Preserve the failure taxonomy: it *is* the feasibility survey.

### 1.2 Static extractor — the hardest engineering piece, and the paper's main threat

**The threat:** if the static baseline is weak, "static misses 30%" only means "my extractor is bad." A reviewer will go straight here.

**Mitigation — two independent static baselines, both reported:**
- **PyCG** (Grouzis et al., ICSE 2021) — the standard published Python call-graph tool. Reporting against PyCG makes the claim about *the state of the art*, not about our code. This is non-negotiable for credibility.
- **Pyright-assisted extractor** — tree-sitter parse + Pyright type information for attribute-call resolution. Stronger where types exist; our own contribution to the comparison.

Report both. If they disagree materially, that disagreement is itself a finding worth a paragraph.

### 1.3 Annotators: ins2 capture begins on green repos as they land

**Gate at end of Week 4:** ≥40 repos with green build + ≥3 replayable workloads + pinned lockfile/digest. If under 40, Phase 0's over-recruitment absorbs it; if badly under, cut the LOW bin to its floor of 10 and hold MED/HIGH.

---

## Phase 2 — Weeks 3–6 (overlaps Phase 1): tracer + normalization

### 2.1 Instrumentation
- **Primary: `sys.monitoring`** (PEP 669, Python 3.12+) — `PY_START`, `CALL`, `PY_RETURN`.
- **Fallback: `sys.setprofile`** for repos rescued onto <3.12 by ins1's Recipes 1–2. Note this interaction explicitly: `sys.monitoring` does not exist before 3.12, so every Recipe-rescued repo needs the fallback and carries higher overhead. `setprofile` (not `settrace`) is correct here — it gets call/return without line events.
- **`importlib` meta-path hook** for dynamic imports.
- **`sys.addaudithook`** for `exec`/`eval`, `subprocess`, `socket.connect`, `open`.
- **`os.environ` read wrapper** for `EnvNode`s.

### 2.2 Normalization and hygiene
- Events → Parquet as `(source_loc, symbol, target, workload_id, tid, ts)`. **Aggregate on write** — never one row per call occurrence in the graph. A 10-minute trace emits millions of events; this is the graph-explosion failure mode and it is fatal to both storage and context budgets.
- **Run every workload 2×, diff the edge sets.** Nondeterministic edges (thread scheduling, time-dependent branches) get a `nondeterministic` flag and discounted confidence. Cheap defence against measuring noise as signal.
- **Measure and report tracer overhead** against ins2's precise untraced baseline. Target <5× with `sys.monitoring`. These numbers are the feasibility argument.
- Network-isolated containers throughout. Record-replay only; no live external calls.
- **Log negative results per repo** — which hooks failed, which workloads crashed. Keep `trace-failed` repos *in* DynBench with a status, or the benchmark acquires survivorship bias.

---

## Phase 3 — Weeks 5–8: mapping, fusion, and the H2a measurement

### 3.1 Trace → graph mapping
Join traced events to static node IDs by `(file, qualified_symbol)` with line as tiebreaker. Unmatched targets → `PhantomNode` (eval'd code, generated classes, subprocess boundaries). Env/file/socket targets → `EnvNode`. Statically unresolvable call sites never exercised by any workload → `UnresolvedDispatch` with static candidates attached.

### 3.2 Storage — deliberately boring
**DuckDB over Parquet**, not Neo4j/Kùzu. k-hop backward slices and set-difference queries are exactly what a columnar engine does well, it is days of work rather than weeks, and no reviewer is evaluating our store. Keep static and dynamic layers **separately materialized and fused on read** — static-only / dynamic-only / fused views are needed constantly for ablations, and baking fusion into extraction makes the Phase 4 comparison impossible.

Edge identity: `(caller_id, callee_id, edge_type)`, provenance merged as a **set**, never collapsed into a scalar confidence — H2c-lite and the serialization both need categorical provenance.

### 3.3 The H2a numbers
Recall/precision of PyCG and of the Pyright-assisted extractor against the traced reference set: overall, per stratum (LOW/MED/HIGH), and **per edge type**. Plus the 5% two-annotator manual audit with Cohen's κ.

### 3.4 GO/NO-GO — end of Week 8

- **Large miss rate (say >20%):** proceed to Phase 4 as planned.
- **Small miss rate:** *this is still the paper.* "Static extraction is more complete than the field assumes, except at these specific construct classes" is a publishable, useful negative result — and it reframes Phase 4 toward characterizing exactly where the misses concentrate.
- **Do not hard-commit to "≥25%" anywhere.** If it lands at 14% but concentrates entirely in DI/plugin-registration sites, that is a *better* paper than a diffuse 30%. The conditional claim is the stronger one.

---

## Phase 4 — Weeks 8–11: H2b-lite + H2c-lite (one bounded experiment)

The cheap-and-credible design here exists **only because ins2 already produced replayable workloads** — they are a free execution oracle, so this needs no orchestrator, no build pipeline, and no fine-tuning.

### 4.1 Design
- **Task:** behavior-preserving repo-wide edits (signature change / rename / move) on a selected symbol. Ground truth is computed from *our* fused graph on *our* pinned repo state — so **contamination is largely a non-issue**, a real simplification we get from dropping the translation framing.
- **Conditions:** identical slicer, identical token budget, identical prompts. The *only* variable is which edges exist (static-only vs fused). This discipline is what makes the claim causal.
- **Slicer:** k=2 backward over the fused graph, personalized-PageRank pruning, hard 6k-token budget, dropped items logged *in the prompt* ("N low-relevance deps omitted").
- **Validation:** replay ins2's recorded workloads → same exit code + canonical contract diff (edge multiset modulo renaming, env-key set). Compare canonicalized aggregates, never raw traces — timestamps and addresses diff spuriously.
- **Models:** one API frontier model + one mid-size open-weight model. No fine-tuning.
- **Baseline:** static-slice + strong retrieval (RepoGraph-style). Do **not** use "dump the whole graph into long context" as a strawman.

### 4.2 The placebo control — the single most important element
Pre-register, timestamped in-repo, **before running**: primary metric, strata, and the prediction of **no improvement on LOW-bin / no-dynamic-edge cones**. A confirmed placebo null is what converts "we added data and got better" into a representation claim. Report the conditional result; never average across strata into one abstract number.

### 4.3 H2c-lite (cheap, worth including)
Add `UnresolvedDispatch` markers to the prompt plus an `abstain`/`confidence` field in the output schema. Measure honest-abstention rate and **silent behavior changes** (contract diff fires, all tests pass). Roughly a prompt change plus a schema field — high value per hour.

**No LLM-as-judge anywhere in validation or headline metrics.** LLM judgment is permitted only in failure *analysis*, clearly marked as such.

---

## Phase 5 — Weeks 10–12: artifact + writing

- **DynBench-Core release:** repo list with pinned SHAs, lockfiles, image digests, resolved Python versions; ins2 workload YAMLs; reference edge sets with workload provenance; extraction + tracing harness; `interventions.yaml` per repo recording every manual intervention.
- **Paper structure:** H2a-led empirical study + benchmark; tracing-feasibility survey; Phase 4 as downstream evidence that the missing edges matter.
- **Banned from the paper:** CodeBLEU/ChrF anywhere but an appendix; unstratified means presented alone; any claim that the traced set is "complete dynamic behavior."

### Bonus finding, already being generated for free
ins3 Part 3 collects env vars *mentioned in documentation*. The tracer collects env vars *actually read*. The diff is a measurable documentation-completeness gap — a nice secondary result at zero marginal cost, and it justifies keeping Part 3.

---

## Critical files to create

```
MANIFEST.md                      # pinned everything, day one
docs/metric_spec_h2a.md          # pre-registration, frozen
docs/prereg_h2b_lite.md          # pre-registration incl. placebo prediction
docs/sop_v1.1_changelog.md       # the five amendments + reallocation
scripts/discover_candidates.py
scripts/density_score.py         # LOW/MED/HIGH stratification, gates Sheet 1
scripts/github_meta.py           # replaces ins3 Part 1
triage/runner.py                 # wraps ins1 triage.sh logic, parallel
triage/triage.sh                 # amended: lock.txt + image digest + pyver
static/pycg_adapter.py           # baseline 1
static/pyright_extractor.py      # baseline 2
tracer/monitor.py                # sys.monitoring
tracer/profile_fallback.py       # sys.setprofile for <3.12
tracer/hooks.py                  # importlib + audit + os.environ
pipeline/normalize.py            # events -> aggregated Parquet
pipeline/map_to_nodes.py         # + PhantomNode / EnvNode / UnresolvedDispatch
graph/store.py                   # DuckDB; static & dynamic separate, fused on read
graph/slice.py                   # k-hop backward + PageRank + token budget
eval/h2a_recall.py
eval/tasks.py                    # Phase 4 task generator
eval/replay_contract.py          # canonical contract diff
```

---

## Verification

**Per phase, end-to-end:**
1. **Phase 0:** density scorer run on 20 known repos; hand-check that a Django/plugin-heavy repo lands HIGH and a pure-algorithmic library lands LOW. Confirm amended `triage.sh` emits a non-empty `lock.txt` and a `sha256:`-prefixed digest.
2. **Phase 1:** automated triage vs the 10% human sample — report agreement. Both static extractors run on 3 repos and produce non-empty, differing edge sets.
3. **Phase 2:** trace `requests` and `click` (the SOPs' own practice repos, so results are comparable to annotator output). Confirm 2× runs produce stable edge sets, overhead <5× on 3.12, and that a known dynamic import appears in the trace and *not* in the static graph. This single check is the whole thesis in miniature — do it in Week 3, not Week 6.
4. **Phase 3:** reference-edge-set audit κ ≥ 0.7 between two annotators; H2a table reproducible from a clean checkout of the artifact.
5. **Phase 4:** the placebo arm must be run and reported *whatever it shows*. Confirm identical slicer/prompt/budget across conditions by diffing the two prompt logs — only edge-list sections may differ.
6. **Phase 5:** clean-clone the released artifact into a fresh container and regenerate one repo's reference edge set from scratch.

**Continuous:** every repo carries `interventions.yaml`; every dynamic edge points to a replayable workload ID; no cell in any sheet is blank.

---

## Risks

| Risk | Mitigation |
|---|---|
| **Static baseline looks weak → claim reads as "bad extractor"** | Two independent baselines, PyCG among them. Highest-priority risk. |
| ins2 workload capture undersupplies the corpus | It is the bottleneck by design — all annotators on it from Week 2; AMBER repos included (amendment 2); 1.5× over-recruitment. |
| Thin HIGH stratum | Density-stratified interleaved queue (amendment 3); over-recruit; report the feasibility survey regardless. |
| Tracer overhead too high on <3.12 repos | `setprofile` fallback; report overhead per Python version; if prohibitive, restrict HIGH-bin tracing to 3.12-capable repos and say so. |
| Phase 4 does not finish | H2a + DynBench + feasibility survey is already a complete paper. Phase 4 is additive by construction — the seam at Week 8 is deliberate. |
| 12 weeks slips | Cut order, decided now: Phase 4's H2c-lite → Phase 4 entirely → the LOW-bin beyond its floor of 10. Never cut the placebo arm while keeping Phase 4, and never cut pinning. |
