# Research Plans: Two Publishable Directions Building on "Graph-Aware Neuro-Symbolic Approaches for Legacy Modernization: A Systematic Review"

Both directions are engineered as direct answers to the open problems named in Section VIII of the review:

- **VIII.A** — verification is expensive; the open problem is *spending the validation budget only where it changes outcomes*.
- **VIII.B** — static graph quality is uneven; *dynamic and low-resource languages* break graph extraction.
- **VIII.C** — the trajectory is *selective autonomy*: graph-guided retrieval + planner-generated edit obligations + targeted validation loops.

Direction 1 attacks VIII.A + VIII.C from the compute side (small models + selective validation). Direction 2 attacks VIII.B (incomplete static graphs) from the representation side (hybrid static–dynamic graphs). They share evaluation infrastructure, so they can be run as a two-paper program.

---

# DIRECTION 1 — GRAFT: Graph-Rationed Fine-Tuning and Topological Orchestration for Small-Model Repository Migration

**Working title:** *"Structure Substitutes for Scale: Compute-Efficient Repository-Level Code Migration with 7–14B Open-Weight Models"*

**Target venues:** ICSE / FSE / ASE (research track) for the systems framing; ICLR / NeurIPS for the distillation framing. Aim ICSE 2028 cycle (submission ~Aug 2027) or FSE 2028.

## 1. Hypothesis & Novelty Statement

**Central hypothesis (H1):** Small open-weight code models (7–14B) fail at repository-level migration not because they cannot translate fragments — RepoTransBench baselines and AlphaTrans's 99.1% syntactic correctness show fragment translation is largely solved — but because three capabilities are missing: (a) repository-scale *context selection*, (b) long-horizon *edit scheduling*, and (c) *diagnostic-driven repair*. All three can be externalized into deterministic machinery or distilled from a verifier, leaving the small model responsible only for bounded, graph-sliced fragment transduction.

**Testable sub-hypotheses:**

- **H1a (Structure-for-scale substitution):** A 14B model given a deterministic *k-hop backward CPG slice with type-signature abstraction* (interface skeletons of dependencies, not bodies) and scheduled in AlphaTrans-style reverse call order will close ≥70% of the build-success gap to a frontier model given naive retrieval, at <10% of the inference cost.
- **H1b (Verifier-certified distillation):** Fine-tuning the small model on (fragment, graph slice, compiler/test diagnostics → repaired code) trajectories that are *certified by deterministic validators* — never by frontier-model judgment — yields larger gains on functional-equivalence metrics than fine-tuning on the same volume of frontier-model outputs filtered only by frontier self-review.
- **H1c (Selective validation budget):** A cheap learned risk model over *graph features alone* (fan-in, betweenness centrality on the call graph, type complexity of the interface, presence of reflection/IO flags, historical failure rate of the fragment's dependency cone) can allocate expensive validation (test execution, in-isolation mock validation à la TRAM) to <30% of fragments while retaining ≥95% of the failures that uniform validation would catch.

**Novelty relative to the reviewed literature:**

1. AlphaTrans, TRAM, MatchFixAgent all assume a strong generator; nobody has published a systematic study of *how far the generator can be shrunk when the scaffold is deterministic*. The paper's headline artifact is a **cost–quality Pareto frontier**: {model size} × {scaffold depth} × {validation budget} → {build success, functional equivalence, $/repo}.
2. **Verifier-certified distillation** is a new label-generation regime for code migration: the oracle is *frontier model + compiler + test harness in a repair loop*, and only loop-exit-successful trajectories become training data. This makes the training signal neuro-symbolic, not just neural.
3. The **risk-rationed validation scheduler** is the first concrete instantiation of the review's VIII.A open problem ("how to spend the verification budget only where it changes outcomes") as a learned, feature-based policy with a measurable recall/cost trade-off.

## 2. Step-by-Step Methodology

### Milestone M0 — Scoping & Task Definition (Weeks 1–4)

Fix the migration task precisely before building anything.

- **Task:** repository-level Java→Python translation (the AlphaTrans setting, so results are directly comparable) plus one refactoring track from SWE-Refactor (behavior-preserving, multi-file). Two tasks, not five.
- **Model pool:** Qwen2.5-Coder (7B, 14B), DeepSeek-Coder-V2-Lite-Instruct (16B MoE, ~2.4B active), StarCoder2-15B, plus one frontier reference (whatever is the current API frontier at execution time) as ceiling and as distillation oracle.
- **Corpus:** the 10 AlphaTrans repositories + a stratified 200-repo sample from RepoTransBench's Java→Python slice, split into train/dev/test **by repository, with license and contamination screening** (check model training cutoffs; exclude repos whose translated versions exist publicly — search PyPI/GitHub for known ports).

**✅ What to Do:**
- Freeze the exact model checkpoints (HF revision hashes) and the exact benchmark commit in a `MANIFEST.md` on day one. Reviewer-proof reproducibility starts here.
- Run the *whole* evaluation harness end-to-end on 3 repositories with the untuned 7B model in week 2. The point is to fail early on infrastructure, not to get numbers.
- Define "build success" operationally now: `docker build` from a clean clone + dependency resolution + `pytest --collect-only` succeeding, in a network-isolated container. Write it down; never redefine it mid-project.

**❌ What NOT to Do:**
- Do not add language pairs "for generality" before the first paper. Each language pair costs a full toolchain (parser, type recovery, test harness). Depth on one pair beats shallow breadth — RepoTransBench already shows the cross-pair fragility story; you don't need to re-show it.
- Do not pick a model pool by leaderboard rank on HumanEval. Function-level scores do not predict repository-level behavior (the review's core finding); pick by context length, tokenizer quality on both languages, and license permitting fine-tuning.
- Do not skip contamination screening. A single well-known repo with a public Python port in the test set can inflate results enough to invalidate the paper under scrutiny.

### Milestone M1 — Framework Design (Weeks 4–8)

Architecture: four decoupled components communicating through typed artifacts on disk (JSON + SQLite), so every stage is independently replayable.

1. **Graph service:** builds and incrementally maintains a CPG per repository. Concretely: Joern for CPG extraction on the Java side; tree-sitter + Pyright-derived type info on the Python side; call graph via Soot (Java, CHA + RTA precision levels) — all tools already validated by the literature the review covers.
2. **Orchestrator (RLM controller):** a deterministic scheduler, *not* an agentic loop. It computes reverse-call-order (topological order on the condensation of the call graph; SCCs handled as atomic units), emits per-fragment work items, and manages the edit transaction log.
3. **Generator:** the small model behind a thin prompt contract: `(target fragment source, k-hop dependency skeletons, already-translated interface signatures, style exemplars) → candidate translation`.
4. **Validator stack:** tiered (see M4).

**✅ What to Do:**
- Make the orchestrator deterministic and the generator stateless. All randomness confined to sampling temperature with a logged seed. This is what makes the ablation matrix (H1a/b/c) actually runnable — you can swap one component while bit-freezing the rest.
- Represent dependency context as **type-signature skeletons** (signatures + docstrings + already-migrated counterparts' signatures), not full bodies. This is the concrete mechanism by which a 32k-context 14B model handles a 500-file repo: the context per fragment is O(local slice), never O(repo).
- Treat SCCs (mutual recursion, cyclic imports) as first-class: translate the whole SCC as one unit with a shared interface contract, or break the cycle with an explicitly generated forward-declaration stub. Log SCC size distribution — it is a paper-worthy characterization of where reverse-call-order breaks down.

**❌ What NOT to Do:**
- Do not build a free-form ReAct agent where the small model decides what to read. The review's Table IV names the failure mode ("tooling complexity, orchestration overhead, reproducibility issues"), and small models are precisely the ones that make bad exploration decisions. Externalized *deterministic* orchestration is the whole bet; letting the 7B model drive tools reintroduces the capability you claimed to remove.
- Do not fuse graph structure into model attention (CGM/GOFA-style) in this project. That requires architecture surgery and pretraining compute that contradicts the compute-efficiency thesis; textual serialization of graph slices is the compute-appropriate design. (Graph-fused attention is Direction 2's arm B.)
- Do not let context assembly "fall back to whole-file inclusion" when the slice is small. Silent fallbacks destroy the ablation: you'll be unable to attribute wins to slicing vs long context. Fail loudly, log the slice size histogram.

### Milestone M2 — Data Pipeline & Verifier-Certified Distillation Corpus (Weeks 8–18)

The distillation corpus is the paper's most novel asset.

1. Run the *frontier* model inside the full GRAFT scaffold on the **training-split** repositories, with the validator stack in a repair loop (max 4 repair rounds per fragment).
2. Log every trajectory: `(fragment, slice, attempt_1, diagnostics_1, attempt_2, …, final)`.
3. Keep only trajectories whose final state passes tier-2 validation (compile + fragment tests + interface conformance). This is the **certification filter**.
4. Materialize two training mixtures: (a) *direct translation* pairs `(fragment+slice → certified final)`, and (b) *repair* triples `(fragment+slice+failed attempt+verbatim compiler/pytest diagnostic → certified fix)`. Target ratio ~60/40; the repair data is what H1b claims matters.
5. Fine-tune with QLoRA (rank 64, all linear layers) first; full-parameter SFT on the 7B only if LoRA saturates. Hold out 5% of *repositories* (not fragments) for early stopping.

**✅ What to Do:**
- Include the *verbatim* tool diagnostics (javac/pyright/pytest output, truncated to the relevant frames with a deterministic truncation rule) in repair training examples. Teaching the model to read real diagnostics is the transferable skill; paraphrased diagnostics train the wrong distribution.
- Deduplicate near-identical fragments across repos (MinHash over token 5-grams, Jaccard > 0.8) *before* the train/test split audit, and report the dedup rate in the paper.
- Cap oracle spend with a per-fragment token budget and report total oracle cost. "Distillation cost vs inference savings break-even after N repositories" is a table reviewers at systems venues love and nobody in this literature has published.
- Version the corpus (DVC or git-LFS + manifest hashes). You will regenerate it at least twice.

**❌ What NOT to Do:**
- Do not train on frontier outputs that merely *look* correct or that the frontier model self-rated as correct. The review's sharpest datum — AlphaTrans's 99.1% syntactic vs 25.8% functional success — is exactly the gap between plausible and certified. Uncertified data re-imports that gap into your weights.
- Do not train on failed trajectories as negatives via naive DPO on (certified, uncertified) pairs without checking that uncertified samples are actually *wrong* rather than *unvalidatable* (missing tests, flaky environment). Mislabeling unvalidatable as negative teaches the model to avoid perfectly good constructs that happen to live in poorly tested repos. If you want preference data, restrict rejected samples to those with a *deterministic* failure witness (compile error, failed assertion).
- Do not exceed ~3 epochs or crank LoRA rank when dev-set functional metrics plateau — small models overfit to repo idioms fast, and the failure shows up as style-copying that breaks on the test split's unseen build systems.
- Do not fine-tune on the evaluation benchmarks' repositories under any framing ("just the train split of the same repo"). Repository-level leakage is subtler than fragment leakage: shared utility modules leak interface conventions.

### Milestone M3 — Inference & Orchestration (Weeks 16–24, overlaps M2)

The runtime loop per repository: build graph → topological schedule → for each fragment: assemble slice → generate k=3 candidates (temp 0.6) → tier-0 filter → best candidate to tiered validation per risk policy → commit or repair-loop (max 3 rounds, then escalate).

**Caching design (critical for the cost claims):**
- **KV-prefix caching:** structure prompts as `[static preamble | repo-level header | fragment-specific slice]` so the first two segments hit the prefix cache across the thousands of fragment calls per repo. With vLLM prefix caching this is a 30–50% latency/cost lever — measure and report it.
- **Slice memoization:** hash `(fragment ID, graph version)` → slice; invalidate via the incremental graph maintenance log (the review's Table III mechanisms), never by full re-extraction.
- **Translation memory:** exact and near-duplicate fragments (same MinHash bucket) reuse prior certified translations with a signature-consistency check instead of a fresh generation.

**Cascading-failure handling (systemic reality #3):**
- Every commit is a git commit on a work branch; the orchestrator maintains a **dependency-frontier ledger**: for each committed fragment, the set of downstream fragments whose slices included its interface.
- **Interface freeze contract:** once a fragment's translation is committed and ≥1 downstream fragment has consumed its signature, the signature is frozen. A repair that must change a frozen signature triggers a *transactional rollback*: revert the fragment and its consumer set (computed from the ledger, not by re-analysis), re-enqueue in topological order.
- **Reverse-call-order compilation checks:** after each commit, incrementally type-check only the consumer frontier (pyright in watch mode scoped to affected files), not the whole repo. Full-repo checks only at SCC boundaries and end-of-repo.

**✅ What to Do:**
- Bound repair loops hard (3 rounds) and make round 3's action *escalation with a structured failure record*, not another blind retry. Small models loop on the same wrong fix; the escalation record (fragment, diagnostics history, slice) is both a fallback hook (route to frontier model — measure how often) and a goldmine failure-analysis dataset for the paper.
- Meter everything per fragment: input/output tokens, wall-clock, validator CPU-seconds, cache hit rates. The Pareto-frontier figure is only as credible as this telemetry.
- Run the whole pipeline in per-repo Docker sandboxes with pinned dependency lockfiles; snapshot the container image hash into the results record.

**❌ What NOT to Do:**
- Do not "fix forward" after an interface-breaking repair by asking the model to patch consumers ad hoc. That is exactly the cascading-failure mode the review describes for planning-driven editing ("derived edits amplify early mistakes"); deterministic rollback via the ledger is cheaper and analyzable.
- Do not let context grow monotonically across repair rounds (appending every prior attempt). Two rounds of full-attempt history overflow a small model's effective context and demonstrably degrade repair quality; include only the last attempt + last diagnostics + the original slice.
- Do not cache across graph versions "because the fragment text didn't change" — its *slice* may have (an upstream signature changed). Cache keys must include the graph version of every slice member.
- Do not evaluate with the escalation-to-frontier path silently enabled. Report small-model-only and small-model+escalation as separate rows, with escalation rate as a first-class metric.

### Milestone M4 — Validation Stack & the Selective Budget (Weeks 20–28)

Tiered validators, ordered by cost:

- **Tier 0 (always, ~ms):** parse (tree-sitter), import resolution, pyright type check of the fragment against frozen upstream signatures.
- **Tier 1 (risk-gated, ~seconds):** TRAM-style in-isolation validation — execute the fragment against auto-generated mocks of its dependencies + translated unit tests where the source repo has them; differential I/O check against the Java original via a JSON-serialized argument/return harness on the fragment boundary.
- **Tier 2 (risk-gated, expensive):** integration build + source test suite transplanted/translated + property-based fuzzing (Hypothesis) on public interfaces with cross-language differential oracle.

**Risk model (H1c):** gradient-boosted trees (LightGBM) predicting P(tier-0-pass but tier-2-fail) from static features: call-graph fan-in/fan-out, interface type complexity (count of generic/collection/nullable params), fragment LOC, cyclomatic complexity, IO/reflection/concurrency flags from the CPG, dependency-cone historical failure rate, SCC membership. Train on M2 trajectory logs (they contain exactly this label). Policy: validate at tier 2 the top-q% by risk; sweep q ∈ {10, 20, 30, 50, 100} for the budget–recall curve.

**✅ What to Do:**
- Train the risk model on the *frontier* oracle's failure patterns but **recalibrate on a small dev sample of the small model's own outputs** (Platt scaling is enough) — failure distributions differ by generator, and uncalibrated transfer is the most likely silent killer of H1c.
- Always report the q=100 (uniform full validation) column. The selective-budget claim is only meaningful against the exhaustive baseline, and reviewers will (correctly) demand it.
- Include *validator flakiness* handling: run tier-2 tests twice on failure, quarantine tests that flip, and report the quarantine rate. RepoMod-Bench's "hidden runtime variability" point cuts both ways — flaky validators corrupt both training labels and evaluation.

**❌ What NOT to Do:**
- Do not use an LLM-as-judge anywhere in the validation stack that produces training labels or headline metrics. The review's IBM WCA4Z discussion permits LLM-judging for *quality reporting*; for correctness claims it launders the exact uncertainty you're trying to eliminate. LLM judgment is allowed only in failure *analysis* (categorizing why things failed), clearly marked.
- Do not gate tier-0 checks by risk. Parsing and type-checking are ~free; rationing them saves nothing and creates the embarrassing failure class "shipped code that doesn't parse."
- Do not tune the risk threshold q on the test split. Choose q on dev, freeze, run test once. Sweeps on test = dead paper.

### Milestone M5 — Evaluation, Ablations & Writing (Weeks 26–36)

**Metrics (systemic reality #1 — beyond text similarity):**

1. **Container Build Success (CBS):** clean-clone → docker build → dependency install → import of every module, network-isolated. Binary, per repo.
2. **Test-Transplant Pass Rate (TTPR):** fraction of source-repo test assertions that pass after translation, using the benchmark's harness (RepoTransBench) and RepoMod-Bench's *hidden, implementation-agnostic* suites where available — hidden tests are the direct answer to benchmark fragility.
3. **Differential Execution Equivalence (DEE):** on public API boundary functions, run source and target on shared inputs (source-repo test inputs + Hypothesis-generated), compare canonicalized outputs. Report per-function equivalence rate and repo-level "all-boundaries-equivalent."
4. **Interface Preservation Score:** fraction of cross-module call sites whose (callee, arity, type-compatible) triple survives migration — computed by graph diff, feeds Direction 2's metrics too.
5. **Cost axes:** $/repo (API-priced) and GPU-hours/repo (self-hosted), tokens/repo, validator CPU/repo, wall-clock/repo.

**Headline figures:** (a) Pareto plot: functional success vs cost, points = {7B, 14B, frontier} × {no scaffold, retrieval-only, full GRAFT} × {q budget levels}; (b) ablation table isolating H1a (slicing/scheduling, no fine-tune), H1b (fine-tune, naive retrieval), H1c (budget sweep); (c) escalation-rate and failure-taxonomy analysis.

**✅ What to Do:**
- Report per-repository results with repo-size strata (files, LOC, SCC count) — RepoMod-Bench's key finding is the scaling cliff; showing *where* your curve bends is more publishable than a single mean.
- Do a manual failure audit of ≥100 failed fragments with two annotators + Cohen's κ, categorized against the review's failure taxonomy (missing dependency, environment assumption, type recovery, dynamic feature). This connects the paper explicitly to the review and sets up Direction 2.
- Release everything: corpus manifests, LoRA weights, orchestrator, telemetry. In this subfield, artifact evaluation badges materially affect acceptance.

**❌ What NOT to Do:**
- Do not report CodeBLEU/ChrF as anything but an appendix curiosity, and never in the abstract. The entire premise of the review — and this paper — is that text similarity is disconnected from executability.
- Do not average build success across repos of wildly different sizes into one number without also giving the stratified view; a mean dominated by 50-file repos while 500-file repos all fail is technically true and scientifically misleading.
- Do not claim "matches frontier performance" if the escalation path handled the hard 20%. Claim the honest, stronger-under-scrutiny version: the measured Pareto improvement.

## 3. Risks & Mitigations

- **Risk:** small models can't use diagnostics even after fine-tuning (H1b fails). *Mitigation:* the paper survives on H1a + H1c alone; H1b failing is itself a publishable negative result given the current distillation hype.
- **Risk:** test-suite poverty in legacy repos starves tier-1/2 validation. *Mitigation:* differential execution (DEE) needs no tests, only runnable boundaries; report coverage-conditioned results.
- **Risk:** oracle cost explosion in M2. *Mitigation:* hard per-fragment budget; corpus size target of ~50k certified pairs is achievable within a fixed grant-scale API budget — compute the ceiling before starting.

---

# DIRECTION 2 — TraceWeave: Dual-State Static–Dynamic Code Property Graphs for Structurally Grounded Migration

**Working title:** *"Beyond the Static Graph: Fusing Runtime Traces and Environment Telemetry into Code Property Graphs for Repository-Level Modernization"*

**Target venues:** ISSTA / ICSE / FSE; the representation-learning arm alternatively at ICLR. This is the direct successor to the review's SemanticForge discussion and Section VIII.B.

## 1. Hypothesis & Novelty Statement

**Central hypothesis (H2):** A substantial, measurable fraction of repository-migration failures attributed to "model limitations" are actually *representation* failures: the static CPG simply does not contain the edge the model needed (reflective dispatch, config-file wiring, environment-variable branching, dynamically imported modules, cross-process calls). Augmenting the CPG with runtime-observed, provenance-tagged edges converts these from invisible to visible, and the improvement is *localized and predictable*: it appears precisely on fragments whose dependency cone contains dynamic edges.

**Testable sub-hypotheses:**

- **H2a (Coverage):** On dynamic-feature-heavy repositories (Python/Ruby legacy, Java-with-Spring-reflection), static CPG extraction misses ≥25% of true runtime call edges (ground truth: exhaustive tracing under the full test suite + recorded production-like workloads); hybrid extraction recovers ≥80% of the missed edges *that are exercised by available workloads*.
- **H2b (Grounding):** An LLM given hybrid-graph slices resolves migration tasks whose dependency cone crosses ≥1 dynamic edge at a rate ≥1.5× that of the same LLM with static-only slices, while performing identically on cones with no dynamic edges (a built-in placebo control that makes the causal claim clean).
- **H2c (Honest uncertainty):** Explicitly marking *unobserved* regions ("dynamic-unknown" nodes: reflective sites never exercised by any workload) and surfacing them to the model reduces confidently-wrong migrations (silent behavior change without any validation failure) relative to both static-only and hybrid-without-uncertainty conditions.

**Novelty relative to the reviewed literature:**

1. SemanticForge (the only dual static–dynamic system in the review) fuses knowledge at the *generation-constraint* level; nobody has published (a) a **typed edge-provenance taxonomy** — `proven-static | observed-dynamic(confidence, workload-ids) | inferred(method) | unknown-dynamic` — as a first-class graph annotation consumed by the model, or (b) the placebo-controlled evaluation design of H2b that isolates *representation* gains from generator gains.
2. The **trace-to-CPG mapping algorithm**: aligning language-level dynamic events (call, import, getattr/reflection resolution, env read, subprocess/IPC) and system-level telemetry (eBPF/strace: file opens, socket connects, exec) back to CPG node IDs via (source-location, symbol, PID/thread) keys — with an explicit treatment of events that have *no* static node (eval'd code, generated classes), which get synthesized "phantom nodes."
3. **DynBench**: a curated benchmark slice of repositories stratified by dynamic-feature density, with ground-truth dynamic edges — the field has RepoTransBench/RepoMod-Bench for outcomes but no benchmark for *graph completeness*, which the review names as the bottleneck ("the bottleneck is therefore graph construction and the amount of information that can be represented").

## 2. Step-by-Step Methodology

### Milestone M0 — Corpus & Ground-Truth Design (Weeks 1–6)

- **Language targets:** Python (dynamic, superb tracing hooks: `sys.monitoring` in 3.12+, `sys.settrace` fallback) as primary; Java-with-reflection (Spring/DI-heavy repos; JVMTI or a ByteBuddy/ASM agent) as secondary — this pairing covers both "dynamic language" and "dynamic features in a static language," the two halves of VIII.B.
- **Corpus:** 40–60 repositories stratified into three bins by static-detectable dynamic-feature density (count of `getattr`/`importlib`/`eval`/reflection call sites per KLOC, config-driven DI markers): LOW / MED / HIGH. Draw from RepoTransBench + SWE-Refactor where possible so downstream task metrics come free.
- **Ground truth for H2a:** for each repo, run (i) full test suite, (ii) example/demo scripts, (iii) 10 minutes of scripted realistic usage where an entry point exists — under full tracing. Union of observed edges + manual annotation of a 5%-sample audit = reference edge set, *explicitly labeled as workload-conditional*.

**✅ What to Do:**
- Record and version the *workloads* themselves (commands, inputs, env, container image) as first-class artifacts. Every dynamic edge's provenance must point to a replayable workload ID — this is what makes "observed" edges auditable and the benchmark reusable.
- Pick repos where the test suite actually runs today. Budget 2 person-weeks purely for getting builds green; the review's benchmark-fragility point predicts this is where projects silently die.
- Include ≥10 repos in the LOW bin even though they're "boring" — they are the placebo arm of H2b and the honesty check of the whole paper.

**❌ What NOT to Do:**
- Do not claim the traced edge set is "the complete dynamic behavior." It is a lower bound conditional on workloads. State this in the paper's threats section *and* encode it in the graph (that's H2c's `unknown-dynamic` marker); overclaiming completeness is the most likely reviewer kill-shot.
- Do not select repos by "has interesting reflection" via manual eyeballing — use the deterministic density metric, or selection bias contaminates the stratification.
- Do not attempt COBOL/low-resource languages in paper one. The review's VIII.B names them, but tracing tooling for them is a project in itself; scope them as explicit future work with the framework designed so a new language = new (parser adapter, tracer adapter) pair.

### Milestone M1 — Hybrid Graph Formalization (Weeks 4–10)

Define the **Dual-State CPG (DS-CPG)** precisely:

- **Nodes:** standard CPG nodes (Joern schema for Java; a tree-sitter+Pyright-derived equivalent for Python) + `PhantomNode` (runtime-only entities: eval'd code objects, generated classes, subprocess boundaries) + `EnvNode` (environment variables, config keys, files, sockets — the "environment telemetry" layer).
- **Edges:** each edge carries `provenance ∈ {static-proven, static-possible (e.g., CHA over-approximation), dynamic-observed, inferred}`, `confidence ∈ [0,1]`, `workloads: [ids]`, `count`. Static-possible and dynamic-observed edges *coexist*: a CHA edge confirmed by a trace gets upgraded, an unconfirmed one stays flagged.
- **Unknown-dynamic markers:** any call site whose callee cannot be statically resolved *and* which no workload exercised becomes an explicit `UnresolvedDispatch` node with the set of static candidates attached.

**✅ What to Do:**
- Write the formal schema (protobuf or a documented property-graph schema on Kùzu/Neo4j) *and* a validator that rejects malformed graphs, before any extraction code. Graph bugs discovered at model-training time cost 10× more.
- Keep the static and dynamic layers separately materialized and *fused on read*. You will need static-only / dynamic-only / fused views constantly for the ablations; baking fusion into extraction makes the ablation matrix impossible.
- Design edge identity so the same logical edge from different sources deduplicates deterministically: key = (caller node ID, callee node ID, edge type), provenance merged as a set.

**❌ What NOT to Do:**
- Do not store per-event trace records in the graph (one edge per call *occurrence*). A 10-minute Python trace emits millions of events; the graph stores *aggregated* edges with counts. Raw traces live in flat columnar files (Parquet), referenced by workload ID. Violating this is the graph-explosion failure mode, and it's fatal to both storage and model-context budgets.
- Do not collapse `static-possible` and `dynamic-observed` into one confidence float and discard provenance. The model-facing serialization (M3) and the honesty claims (H2c) both need the categorical provenance; a scalar loses the information that makes the taxonomy novel.
- Do not invent a new graph query language. Cypher/openCypher on an embedded store is enough; reviewers should evaluate the representation, not your DSL.

### Milestone M2 — Trace Harness & Data Engineering Pipeline (Weeks 8–20)

Pipeline stages, each idempotent and separately re-runnable:

1. **Instrumentation:** Python: `sys.monitoring` (call, return, import events) + an `importlib` hook for dynamic imports + audit hooks (`sys.addaudithook`) for `exec/eval`, env reads (`os.environ` access via a wrapper), subprocess, socket. Java: a ByteBuddy agent instrumenting `Method.invoke`, `Class.forName`, DI container bind/resolve events, plus JFR for env/file/socket. System layer for both: eBPF (via bpftrace/libbpf) or strace fallback capturing openat/connect/execve, joined to language events by PID+timestamp.
2. **Normalization:** events → (source location, symbol, target, timestamp, workload ID) tuples in Parquet.
3. **Mapping:** join to CPG node IDs by (file, line, symbol); unmatched targets → PhantomNodes; env/file/socket targets → EnvNodes.
4. **Aggregation & fusion:** dedupe, count, confidence assignment (observed = 1.0 scaled by workload diversity: edges seen under ≥2 distinct workloads score higher), upgrade/flag static edges.
5. **Incomplete-code & missing-service handling:** where the repo calls external microservices or unavailable systems, generate **record-replay mocks**: capture request/response pairs at the socket/HTTP layer (VCR.py / WireMock) during any successful run; where nothing was ever captured, insert an `EnvNode(status=unmocked)` — never a fabricated stub pretending to be real.

**✅ What to Do:**
- Measure and report tracer overhead (target <5× slowdown with `sys.monitoring`; if using `settrace`, sample call events rather than dropping the run). Overhead numbers belong in the paper — they are the feasibility argument for "low-resource" adoption.
- Run every workload 2× and diff the edge sets; nondeterministic edges (thread scheduling, time-dependent branches) get `confidence` discounted and a `nondeterministic` flag. This is the cheap defense against training the model on noise.
- Sandbox everything (network-isolated containers, recorded external calls only). A migration research pipeline that lets legacy code hit live services is both a validity problem and an ethics/ops problem.
- Log *negative* results per repo: which instrumentation hooks failed, which workloads crashed. The "tracing feasibility survey" table across 60 repos is independently citable.

**❌ What NOT to Do:**
- Do not mock missing microservices with LLM-generated fake implementations for *trace collection*. Fabricated responses create fabricated dynamic edges — poisoning exactly the layer whose selling point is ground truth. Mocks must be record-replay or explicitly absent.
- Do not join system-layer (eBPF) events to language events by timestamp alone — clock skew and async runtimes will mis-attribute edges; require PID/TID match and use timestamp only as a tiebreaker within a thread.
- Do not silently skip repos where instrumentation fails; that biases the corpus toward easy targets (survivorship bias in the benchmark). Keep them in DynBench with a `trace-failed` status and report the failure taxonomy.
- Do not let the harness depend on repo-specific manual patches without recording them; every manual intervention goes in a per-repo `interventions.yaml`, counted and reported.

### Milestone M3 — Model Integration: Serialization & Graph-Aware Attention (Weeks 18–28)

Two arms, evaluated against each other (this comparison is itself a contribution — the review notes the field has both approaches but no controlled comparison on the *same* graphs):

- **Arm A — Structured serialization (retrieval-side, model-agnostic):** For a migration target fragment, compute the *k-hop backward slice over the fused DS-CPG* (k=2 default), then serialize as a typed adjacency section in the prompt: dependencies grouped by provenance, e.g. `## Proven static deps`, `## Observed at runtime (workloads: test-suite, demo-2) — NOT visible statically`, `## UNRESOLVED dynamic dispatch — candidates: {A, B, C}, never observed`. Env dependencies rendered as an explicit `## Environment contract` block (env vars read, files touched, services called, with example recorded values).
- **Arm B — Graph-conditioned adapter (CGM-style, compute-permitting):** a GNN encoder (2–3 layer relational GAT with edge-type + provenance embeddings) over the slice, cross-attended into a frozen 7–14B code model via lightweight adapter layers; trained on the Direction-1-style certified corpus restricted to this project's repos. Arm B is explicitly *optional/best-effort*: if compute or time binds, Arm A alone still carries the paper (H2b/H2c are stated over Arm A).

**Graph pruning for the context budget (the anti-explosion discipline):**
- Slice = backward k-hop ∩ (nodes with relevance score above threshold), relevance = personalized PageRank from the target node with edge weights = confidence × edge-type prior (call > data-dep > control-dep for migration tasks).
- Bodies included only for 1-hop; ≥2-hop nodes contribute signatures only; EnvNodes always included (they're tiny and they're the point).
- Hard token budget per slice (e.g., 6k tokens) enforced by dropping lowest-PageRank items, with the drop *logged in the prompt* ("N additional low-relevance deps omitted") — honesty propagates to the model.

**✅ What to Do:**
- A/B the serialization format itself on a 200-task dev slice (grouped-by-provenance vs inline-annotated vs edge-list) before freezing; serialization choices swing LLM graph-comprehension results by large margins and reviewers will ask.
- Keep the *same* slicer, budget, and prompts across static-only vs hybrid conditions — the only variable is which edges exist. This is the discipline that makes H2b causal.
- For Arm B, initialize from and compare against a text-only LoRA with identical training data, so the delta attributable to the GNN pathway is isolated from the delta of fine-tuning at all.

**❌ What NOT to Do:**
- Do not dump the whole DS-CPG (even serialized cleverly) into a long-context model as a baseline you intend to beat trivially. It's a strawman reviewers see through; the honest strong baseline is static-slice + best retrieval (RepoGraph-style), which the review identifies as the current standard.
- Do not train the GNN end-to-end with the LLM unfrozen on your small corpus — 14B parameters + 50 repos = memorization; frozen-LLM adapters only.
- Do not blend provenance into the serialization implicitly (e.g., ordering edges by confidence without labels). H2c requires the model to *see* the uncertainty categorically; implicit encodings make the honesty ablation unfalsifiable.

### Milestone M4 — Task Execution & Validation (Weeks 26–34)

Reuse Direction 1's tiered validator and transactional orchestration wholesale (shared infrastructure). Additions specific to this paper:

- **Dynamic-contract regression check (tier 2+):** after migration, re-run the recorded workloads against the migrated repo (with record-replay mocks) and diff the *observed edge multiset* and the *environment contract* (env reads, file/socket touches) against the source-side trace. A migration that passes tests but stops reading `CONFIG_TIMEOUT` or drops a reflective handler registration is caught here and nowhere else — this validator is the paper's teeth.
- **Selective budget (systemic reality #2):** the risk gate is structural and free: fragments whose dependency cone contains ≥1 `dynamic-observed` or `UnresolvedDispatch` element get tier-2 + dynamic-contract validation; pure-static cones get Direction-1-style risk-gated validation. This is a *principled* budget rule (validate where the representation says uncertainty lives), contrasted experimentally against uniform and random budgets of equal cost.
- **Cascading failures (systemic reality #3):** identical ledger/rollback machinery as Direction 1, with one addition — dynamic edges join the dependency-frontier ledger, so a change to a reflectively-invoked handler correctly invalidates its *runtime* callers, which static ledgers miss. (This sentence is, in miniature, the whole paper.)

**✅ What to Do:**
- Pre-register (in the repo, timestamped) the H2b analysis: primary metric, strata, the placebo prediction (no improvement on LOW-bin/static-only cones). A confirmed placebo null is what elevates this from "we added data and got better" to a causal representation claim.
- Count and report **silent behavior changes** (dynamic-contract diff fires, all tests pass) as a headline metric — it is the empirical form of the review's "benchmark scores obscure runtime failures."

**❌ What NOT to Do:**
- Do not let the dynamic-contract check compare raw traces (timestamps, memory addresses, ordering under concurrency will diff spuriously). Compare canonicalized, aggregated contracts: edge multisets modulo renaming map, env-key sets, request/response schemas.
- Do not run migrated-code workloads outside the sandbox or against live recorded-service endpoints; replay only.

### Milestone M5 — Evaluation Metrics & Analysis (Weeks 32–40)

**Structural fidelity:**
- **Graph Recovery Recall/Precision (H2a):** hybrid vs static extraction against the reference edge set, per stratum, per edge type (reflective call, dynamic import, env read, IPC).
- **Post-Migration Structural Fidelity:** typed graph edit distance (approximated: node/edge Jaccard over the canonical renaming map, computed per edge-provenance class) between source DS-CPG and migrated DS-CPG. Report per class — preserving `dynamic-observed` edges is the claim; static-edge preservation is table stakes.

**Interface alignment:**
- **Interface Alignment Score:** fraction of cross-module boundaries (including *runtime* boundaries: reflective registration points, plugin interfaces, RPC schemas) whose signature/schema is type-compatible post-migration. Static-boundary and dynamic-boundary columns separately.

**Edge-case coverage:**
- **Dynamic Contract Preservation Rate:** fraction of recorded workloads whose replay on migrated code produces an equivalent canonical contract.
- **Silent-change rate** (defined above) and **honest-abstention rate** (H2c): how often the model, given `unknown-dynamic` markers, flags the fragment or requests validation instead of guessing — measured via a structured "confidence/abstain" field in the output schema, audited manually on a sample.

**Task outcomes:** CBS / TTPR / DEE exactly as Direction 1 (shared harness), stratified by dynamic-density bin and by "cone contains dynamic edge" — the H2b headline table.

**✅ What to Do:**
- Publish DynBench (repos list, workloads, reference edge sets, harness) as the artifact. Benchmarks outlive methods; this is the citation engine of the paper.
- Include an ablation of *dynamic layer only* (drop dynamic edges below workload-diversity thresholds) to characterize how much tracing effort buys how much accuracy — the practical adoption question for industry readers (the WCA4Z audience).

**❌ What NOT to Do:**
- Do not aggregate H2b across strata into one improvement number for the abstract. The honest claim is conditional ("on dynamic-cone tasks, X→Y; elsewhere, parity") and it is *stronger* stated conditionally, because it demonstrates you know the mechanism.
- Do not use graph-edit-distance libraries with exponential exact algorithms on full repo graphs (GED is NP-hard); use the Jaccard-over-alignment approximation and say so.
- Do not present recall against traced ground truth as recall against *all* dynamic behavior (workload-conditionality, again — it must appear in every metric definition, not just threats-to-validity).

## 3. Risks & Mitigations

- **Risk:** tracing infeasible on too many repos → thin HIGH stratum. *Mitigation:* the feasibility survey is itself reportable; over-recruit the corpus 1.5×.
- **Risk:** H2b effect exists but is small because validators already catch dynamic failures late. *Mitigation:* measure repair-round counts and validator cost — "hybrid graphs prevent failures that static+validation only *repairs* expensively" is a cost claim, not just an accuracy claim, and connects back to VIII.A.
- **Risk:** Arm B (GNN adapter) underperforms serialization. *Mitigation:* that comparison is publishable either way and directly informs the CGM/GOFA line the review discusses.

---

# Shared Program Notes

- **Sequencing:** Direction 1's M1–M4 infrastructure (graph service, orchestrator, tiered validators, telemetry) is ~70% reusable in Direction 2; run D1 first or overlap with a 2–3 month stagger.
- **The three systemic realities, mapped:**
  1. *Benchmark fragility* → both papers make container-clean-clone build, hidden-test suites (RepoMod-Bench), and differential execution the primary metrics; text similarity is banished to appendices. D2 adds dynamic-contract replay, which catches the failures even execution benchmarks miss.
  2. *Verification overhead* → D1 answers with a learned risk-rationed budget (H1c, with the uniform-validation control); D2 answers with a structural budget rule (validate where dynamic uncertainty lives) and benchmarks both against random-equal-cost baselines.
  3. *Cascading failures* → shared transactional orchestration: reverse-call-order scheduling, interface-freeze contracts, dependency-frontier ledger, deterministic rollback of consumer sets; D2 extends the ledger with runtime edges so reflective callers are correctly invalidated.
- **Cross-paper synergy for a third paper:** D1's risk model + D2's provenance-annotated graphs = a selective-autonomy controller (the review's VIII.C), i.e., a policy that routes each fragment to {small model, frontier model, human} × {validation tier} — the natural capstone.
