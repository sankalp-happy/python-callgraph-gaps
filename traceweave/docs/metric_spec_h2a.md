# H2a Metric Specification — PRE-REGISTRATION

| | |
|---|---|
| **status** | **FROZEN on 2026-07-27, before any extraction code was written.** |
| **spec_version** | `1.0` |
| **hypothesis** | H2a — static call-graph extraction misses a substantial fraction of true runtime call edges on Python repositories, and the misses concentrate in identifiable construct classes. |

> **Why this exists and why it is frozen.** Every definitional choice below can be tuned after
> the fact to move the headline number. Freezing them in advance is what makes the number a
> measurement rather than a search. Changes require a `spec_version` bump, a dated entry in §9,
> and re-running everything — never a silent edit.
>
> **The number is not pre-committed.** `research_plans.md` phrases H2a as "≥25%". We
> deliberately do **not** commit to a threshold. A 14% miss rate concentrated entirely in
> dependency-injection and plugin-registration sites is a *better and stronger* result than a
> diffuse 30%, because it names a mechanism. The conditional claim is the publishable one.

---

## 1. What is a node

A node is a **callable code unit** or a module. Identity is exactly:

```
node_id = (repo_url, sha, relative_path, qualified_symbol)
```

`qualified_symbol` is the dotted path from module root, e.g. `pkg.mod.Class.method`.

**Line numbers are NOT part of identity.** They move under reformatting and they differ between
the static parse and the runtime frame. Lines are a *disambiguation hint* during mapping only.

### Node normalization rules (all mandatory)

| Construct | Rule | Why |
|---|---|---|
| **Module top-level code** | One node per module, `qualified_symbol = "<module>"`. | Import-time execution is real behavior and a major source of registration side effects. |
| **Comprehensions / genexprs** | **Normalize into the enclosing function.** Never their own node. | ⚠️ **Version-critical.** PEP 709 inlined list/set/dict comprehensions in CPython 3.12, but generator expressions remain separate code objects. Without normalization the node set would differ between a 3.12 repo and a 3.10 repo, making cross-version comparison invalid. |
| **Lambdas** | Own node, `qualified_symbol = "<enclosing.qualname>.<lambda#N>"`, where `N` is the 0-based ordinal of the lambda in source order **within its immediately enclosing scope**. | Needs a stable name without using line numbers. |
| **Nested functions / closures** | Own node via normal `__qualname__` (`outer.<locals>.inner`). Normalize `<locals>` away to `.` for readability but keep it injective. | |
| **Bound vs unbound methods** | Resolve to the **defining class in the MRO**, not the runtime instance's class. `B().m()` where `m` is defined only on `A` yields callee `A.m`. | Makes static and dynamic directly comparable; the instance class is recorded as an attribute, not identity. |
| **`super().m()`** | Callee is the **MRO-resolved** definition observed at runtime. | This is one of the construct classes we expect static tools to over-approximate. Recorded as its own edge type so the divergence is measurable rather than hidden. |
| **Properties / descriptors** | The getter/setter function is the callee node. | |
| **Generators & coroutines** | The call edge is attributed at **first activation only** (`PY_START`), never at resumption (`PY_RESUME`). | Otherwise whoever resumes a generator gets spurious caller edges. `sys.monitoring` distinguishes these; the `setprofile` fallback does not cleanly, so the fallback applies a first-activation dedup keyed on `(frame_id, code_id)`. |
| **Async** | Same as generators. `await` resumption is not a call edge. | |

---

## 2. What is a call edge

```
edge = (caller_node_id, callee_node_id, edge_type)
```

Aggregated, **never one row per occurrence** — the graph stores an edge once with a `count`.
Per-occurrence records live only in Parquet, referenced by `workload_id`.

### 2.1 The comparable universe (defines the denominator)

An edge is **in-universe** iff *all* of:

1. Caller and callee are both **in-repo** nodes (both `relative_path`s inside the repo tree).
2. Callee is a **Python-level** callable (has a Python code object).
3. Both nodes are **statically representable** — i.e. they exist in the parsed source. Runtime-only
   entities (`eval`'d code, dynamically synthesized classes) are **out-of-universe** and become
   `PhantomNode`s, counted and reported separately.

**Everything below is excluded from the primary H2a denominator and reported as its own line:**

| Excluded | Why exclusion is required for honesty |
|---|---|
| Calls into **C/builtin** callables (`len`, `numpy.*`, `re.match`) | Static call-graph tools do not model these at all. Including them would let us report an enormous "static miss rate" that is purely an artifact of comparing against something no tool claims to do. This is the single easiest way to accidentally fabricate a headline number, so it is excluded by construction. |
| Calls to **third-party / stdlib** functions outside the repo tree | Same reason; also unbounded in size. Reported separately as the "external surface". |
| Edges into `PhantomNode`s | Not statically representable even in principle. Reported separately — it is a *different* claim ("N% of runtime callees have no static counterpart at all"), and a strong one. |

### 2.2 Edge-type taxonomy

Edge type is assigned by **deterministic syntactic classification of the call site** (from the
caller's AST), *not* by whether the static tool happened to find it. This ordering matters: it
keeps "static misses X% of edges of type T" well-defined and non-circular.

| `edge_type` | Call-site form | Expectation |
|---|---|---|
| `direct` | `f()` where `f` resolves to a module/local def | Static should get ~all of these. Our sanity floor. |
| `method_static` | `obj.m()` where `obj`'s type is statically inferable | Static should mostly get these. |
| `method_dynamic` | `obj.m()` where `obj`'s type is **not** statically inferable | Expected miss zone. |
| `super_dispatch` | `super().m()` | Expected over-approximation zone. |
| `reflective` | `getattr(o, name)()`, `operator.attrgetter`, `__getattribute__` interception | Core H2a target. |
| `dynamic_import` | callee reached via `importlib.import_module`, `__import__`, `imp` | Core H2a target. |
| `eval_exec` | callee inside `eval`/`exec`/`compile` output | Always → `PhantomNode`. |
| `callback_dispatch` | callee is a value retrieved from a container/registry/attribute then called (`handlers[k]()`, `self._cb()`) | Core H2a target — the plugin/DI mechanism. |
| `decorator_apply` | module-init-time call of a decorator on a def | See §2.3 — special handling. |
| `decorator_wrapper` | call to a decorated name that lands in the wrapper | See §2.3 — **must not be counted as a miss.** |
| `subprocess_ipc` | `subprocess`, `multiprocessing`, socket boundary | Out-of-universe; recorded as `EnvNode` edge. |

### 2.3 Decorators — a systematic divergence that is NOT a miss

⚠️ **This is the most likely way to accidentally inflate H2a, so it is specified up front.**

For `@dec def f(): ...` then a call `f()`:

- Runtime observes `caller → dec.<locals>.wrapper`, and then `wrapper → f`.
- Most static tools model `caller → f` directly.

Naively differencing these yields *two* fabricated "misses" (`caller→wrapper`, `wrapper→f`) plus
one fabricated static false positive (`caller→f`). That is an artifact of representation, not a
real blind spot.

**Rule:** during fusion, apply **wrapper transparency** — when a traced path is
`caller → W → f` and `W` is identified as a decorator wrapper (its code object is defined inside
a function that received `f` as an argument and was invoked at `decorator_apply` time), collapse
it to `caller → f` for the primary metric. Report the un-collapsed view as a secondary table.

`decorator_apply` edges (module-init calling `dec`) remain as genuine edges, since they are real
and static tools do generally miss import-time side effects.

---

## 3. The reference edge set (ground truth)

For repo `r` with workload set `W`:

```
R(r) = ⋃_{w ∈ W}  { in-universe edges observed while executing w }
```

**R is a lower bound, conditional on W.** This wording is mandatory in every metric definition,
every table caption, and every figure — not only in threats-to-validity. We never write "all
dynamic behavior".

### Hygiene requirements
- Every workload runs **2×**; edges seen in only one run get `nondeterministic = true`, confidence discounted, and are reported both included and excluded.
- Every edge carries `workloads: [ids]` and `count`. Edges observed under ≥2 distinct workloads score higher confidence.
- A **5% stratified sample** of R is manually audited by **two annotators** with **Cohen's κ**. Target κ ≥ 0.7. The audit checks: is this edge real, is its `edge_type` right, is the callee correctly resolved.

---

## 4. The primary metric

Let `S(r)` = static edge set (in-universe), `R(r)` = reference set.

### 4.1 Static recall — THE headline

```
recall(r)     = |S ∩ R| / |R|
miss_rate(r)  = 1 − recall(r)
```

Reported: overall, **per stratum** (LOW/MED/HIGH), **per `edge_type`**, and per static tool
(PyCG, Pyright-assisted). Per-repo values are reported alongside any aggregate; a mean is never
shown alone.

### 4.2 What we must NOT call precision

```
workload_confirmed_fraction(r) = |S ∩ R| / |S|
```

An edge in `S \ R` is **not** necessarily a false positive. It may be:
- a genuine edge in code no workload exercised (**unexercised**), or
- a real static over-approximation (**spurious**, e.g. CHA-style fan-out).

These are not separable from traces alone. **Therefore we never report `|S∩R|/|S|` as
"precision".** It is labelled *workload-confirmed fraction* everywhere. Where we want a genuine
precision signal, it comes from the §3 manual audit on a sample of `S \ R`, reported with its
sample size and CI — never extrapolated to a headline.

### 4.3 Mandatory conditioning: execution coverage

Recall is meaningless without knowing how much of the repo ran. Report per repo:

```
fn_coverage(r) = |{nodes activated ≥1×}| / |{static callable nodes}|
```

Every recall figure is plotted **against** `fn_coverage`. A high miss rate on a repo with 8%
coverage means something very different from the same rate at 70%.

### 4.4 Secondary metrics

- **Phantom rate** — `|{runtime callees with no static counterpart}| / |R|`. A separate, strong claim.
- **PyCG parse-failure rate** — fraction of repos/files the published baseline cannot parse at all (see `MANIFEST.md` §2). A completeness result about the state of the art in its own right.
- **`UnresolvedDispatch` census** — statically unresolvable call sites that *no* workload exercised. These are the honest unknowns and they seed H2c-lite.
- **Env-contract gap** — env vars read at runtime vs. env vars documented (from ins3 Part 3). Free secondary finding.

---

## 5. Stratification

Bins are assigned by `scripts/density_score.py` **before triage** (amendment 3), from
dynamic-feature call sites per KLOC. The scorer is frozen alongside this spec; its exact feature
list and thresholds live in `docs/density_scorer_spec.md` and are versioned with it.

Strata: `LOW` / `MED` / `HIGH`. LOW has a **hard floor of 10 repos** — it is the placebo arm for
H2b-lite and the honesty check for the paper.

---

## 6. Analysis discipline

- **No threshold or definition in this document may be tuned after seeing H2a results.**
- Aggregates are always accompanied by per-stratum and per-edge-type breakdowns.
- Any repo excluded from analysis is listed with a reason in the feasibility survey. Silent drops are forbidden — they create survivorship bias in DynBench.
- `trace-failed` repos stay in the released benchmark with a status.

---

## 7. Threats this spec deliberately pre-empts

| Threat | How this spec answers it |
|---|---|
| "Your static baseline is just bad." | Two independent baselines, one of them the published PyCG. §4.1 reports per-tool. |
| "You inflated the miss rate with C calls / stdlib." | Excluded from the universe by construction, §2.1. |
| "Decorators fake your misses." | Wrapper transparency, §2.3, specified before extraction. |
| "Traces aren't ground truth." | Workload-conditional lower-bound wording is mandatory everywhere, §3. |
| "Your `S\R` precision claim is wrong." | We refuse to make it; §4.2. |
| "Comprehension handling differs across Python versions." | Normalized into enclosing function, §1, citing PEP 709. |
| "Low coverage explains everything." | Recall always conditioned on `fn_coverage`, §4.3. |

---

## 8. Out of scope for this spec

Data-flow edges, control-dependence edges, type-inference quality, and any migration-task
outcome. Those belong to H2b-lite (`docs/prereg_h2b_lite.md`, written before Phase 4).

---

## 9. Change log

| spec_version | date | change |
|---|---|---|
| 1.0 | 2026-07-27 | Initial freeze, before any extraction code existed. |
