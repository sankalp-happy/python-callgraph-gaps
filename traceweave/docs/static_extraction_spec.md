# Static extraction — the decisions `metric_spec_h2a.md` did not make

| | |
|---|---|
| **status** | Written 2026-08-17, alongside the code in `static/`. Not frozen; `metric_spec_h2a.md` is. |
| **extraction_version** | `1.0` |
| **conforms to** | `docs/metric_spec_h2a.md` spec_version `1.0` |

The metric spec was frozen on 2026-07-27, **before any extraction code existed** —
which is exactly what makes it a pre-registration and exactly why it could not
anticipate every case the code then hit. This document records every place the
implementation had to decide something the spec is silent on, what was decided,
and **which way the decision biases the result.**

That last column is the point. A reader can accept or reject any one of these
choices, but they should never have to guess whether a choice was made to help
the headline number.

> **Nothing here changes a definition in the frozen spec.** Two entries (§2.1,
> §2.2) resolve cases §1 does not cover and therefore touch the `fn_coverage`
> denominator; they are flagged as candidates for a `spec_version` 1.1 bump if
> the coordinator wants them formally in the pre-registration.

---

## 1. Summary table

| # | The case §1/§2.2 does not cover | Decision | Direction of bias |
|---|---|---|---|
| 2.1 | Is a **class body** a node? | Yes, `kind=class_body`, but `callable=false` | none on recall; slightly **raises** `fn_coverage` by keeping non-callables out of its denominator |
| 2.2 | Are **`@typing.overload` stubs** nodes? | Inventoried, `callable=false`, named apart | **raises** `fn_coverage` (40 of click's 580 callables were stubs no run can activate) and prevents 3 real functions being renamed |
| 2.3 | A **property setter** has the same `co_qualname` as its getter | Suffix the role: `C.v` / `C.v.<setter>` | none — makes identity injective, which it was not |
| 2.4 | A **def redefined** under `if`/`else` | Suffix an ordinal: `f#0`, `f#1` | none — Phase 3 disambiguates by line, which §1 sanctions |
| 2.5 | `<locals>` stripping is **not injective** | Strip, detect collisions, fall back to the raw qualname | none |
| 3.1 | What makes a receiver "**statically inferable**" (§2.2 `method_static` vs `method_dynamic`)? | Rule R-INFER, below — deliberately weak | **dilutes H2a**: easy edges land in the bucket we predict is missed, lowering that bucket's measured miss rate |
| 4.1 | PyCG is **not deterministic**; which run is `S`? | Union of the runs that completed, across a fixed seed policy | **favours PyCG** — maximum credit to the published baseline |
| 4.2 | PyCG emits the **same function under two namespaces** | Merged when exactly one package root resolves it, with a count | **favours PyCG** (unmerged, click's miss rate inflates ~11 points) |
| 4.3 | PyCG emits **paths that are not definitions** | Recorded as `unmapped` with a reason, never dropped silently | neutral, and auditable by arithmetic |
| 5.1 | How does Pyright answer "what does this call resolve to"? | `textDocument/definition` per call site | — |
| 5.2 | Accept a definition location on containment, or exact line? | **Exact line only** | **weakens baseline 2** (our own extractor), never PyCG |
| 5.3 | Pyright runs **without the repo's dependencies installed** | Recorded as `deps_available: false`; `--site-packages` strengthens it | **weakens baseline 2**, never PyCG |
| 6.1 | Is **test code** in the universe? | No by default; `--include-tests` widens it, and the choice is in every artifact | shrinks the universe symmetrically; see §6 |

---

## 2. The node set

### 2.1 Class bodies

A class body is a real code object with its own runtime frame
(`co_qualname == "C"`), and it is where registration decorators and metaclass
work happen — the H2a construct classes. It needs to exist so those import-time
calls have an owner.

But §4.3's `fn_coverage` counts "static callable nodes", and a class body is not
callable. So it is inventoried with `callable=false` and stays out of that
denominator. Module nodes get the same treatment for the same reason.

**Candidate for a spec_version bump**, because it touches a denominator.

### 2.2 `@typing.overload` stubs

`@overload def f(x: int) -> int: ...` declares a signature. Its body is `...`,
and CPython throws the object away when the real `def f` rebinds the name. It is
therefore not a callable code unit: **no workload can ever activate it, and no
static tool should emit an edge into it.**

Left in the inventory (it is real source), marked `overload_stub`, kept out of
`CALLABLE_KINDS`, and named `f.<overload#N>` so it cannot collide with the
implementation.

This is not cosmetic. In click:

- **40 of 580** callable nodes were overload stubs. Left in, `fn_coverage`'s
  denominator carries 7% of nodes that can never be covered.
- **3 functions** (`Editor.edit`, and two others) had their implementation
  renamed to `f#2` by collision handling because the stubs shared the name —
  meaning they no longer matched what PyCG and the runtime both call them. A
  silent, permanent miss for every overloaded function in the corpus.

The density scorer hit the same construct from the other side (README finding 2:
`@t.overload` counted as a registry decorator), which is what prompted the check.

**Candidate for a spec_version bump**, because it touches a denominator.

### 2.3–2.5 Making identity injective

§1 gives `node_id = (repo_url, sha, relative_path, qualified_symbol)` and says to
normalize `<locals>` away "but keep it injective". Three cases break injectivity:

| Case | Why the obvious fix fails | What is done |
|---|---|---|
| `def f(): def g()` vs `class f: def g()` | both strip to `f.g` | fall back to the raw qualname for the colliding group |
| a property setter | byte-identical `co_qualname` to the getter (`C.v`), so raw qualnames do not separate them either | suffix the accessor role: `C.v.<setter>`, `C.v.<deleter>` |
| `if WIN: def f() else: def f()` | one name, two definitions; CPython itself only distinguishes them by `co_firstlineno` | suffix a source-order ordinal: `f#0`, `f#1` |

Phase 3 maps a runtime frame onto the right member using its line number, which
§1 explicitly sanctions as a "disambiguation hint". Both collision kinds are
**counted** in every artifact (`locals_collision_groups`, `redefinition_groups`)
— a repo where they fire has names our scheme handles by falling back, and the
reader should know how often rather than assume never. click: 0 and 7.

---

## 3. Edge-type classification

§2.2's rule is what keeps H2a non-circular:

> "Edge type is assigned by deterministic syntactic classification of the call
> site (from the caller's AST), *not* by whether the static tool happened to
> find it."

`static/callsites.py` therefore never sees PyCG's output and never asks Pyright
anything. Ordered rules, first match wins, so every call site lands in exactly
one bucket and the buckets sum to the total (asserted in `tests/test_static.py`,
on click as well as on fixtures).

`decorator_wrapper` is **never assigned** here. §2.3 identifies a wrapper by its
having received the wrapped function as an argument at `decorator_apply` time —
a runtime fact. Assigning it from syntax would be a guess dressed as a
classification.

### 3.1 R-INFER: what "statically inferable" means

§2.2 splits `method_static` ("`obj`'s type is statically inferable") from
`method_dynamic` ("not"). Inferability is not a syntactic property, so something
has to decide it — and it **cannot be Pyright**, because Pyright is baseline 2
and the classification would then be circular.

So a receiver is inferable if and only if it is one of:

1. `self` / `cls` inside a method → the enclosing class
2. a name assigned from a constructor call `C(...)` where `C` resolves to an
   in-repo class
3. a name (or parameter) with a class annotation resolving to an in-repo class
4. an in-repo module (`mod.f()` — which is a def lookup, so it is `direct`, not a
   method call at all)

Nothing else. Binding is **flow-insensitive**: the last binding of a name in a
scope wins. That is a known limitation rather than a solved problem, and
deliberately so — flow-sensitive binding *is* a static analysis, and static
analyses are the things under measurement.

**Direction of the bias, stated because it matters:** the rule is weak, so
genuinely easy receivers get labelled `method_dynamic`. That moves easy edges
INTO the bucket we predict static tools miss, which makes that bucket's measured
miss rate **lower**. It dilutes H2a rather than inflating it. A rule biased the
other way would have been unpublishable.

### 3.2 Bookkeeping that is not an edge type

Two attributes are recorded per call site instead of inventing taxonomy:

- `construct: true` for `C()`, whose runtime callee is `C.__init__`. Kept as
  `direct` per §2.2's wording, breakable out later without a spec change.
- `target_scope ∈ {in_repo, external, unknown}`, so §2.1's excluded categories
  (C/builtins, third-party) have a number — "the external surface" — rather than
  vanishing.

---

## 4. Baseline 1: PyCG

### 4.1 The seed policy is part of the metric

`scripts/pycg_determinism.py` established that identical invocations over click's
17 modules return **1137, 1160 and 1286 nodes** on different runs, and that some
identical invocations exhaust 8 GB instead of returning at all — because PyCG's
fixpoint iterates over sets and `PYTHONHASHSEED` is random per process.

"PyCG's call graph for repo R" is therefore ill-defined, so:

- every run pins `PYTHONHASHSEED` explicitly (default policy `0,1,42`),
- **`S` is the union of the runs that completed**, and
- per-seed node/edge counts, OOMs and timeouts are recorded beside it, with
  `deterministic_across_seeds` as a reported boolean.

Union is deliberate: it gives the published baseline the maximum credit its own
tool can produce, so a high miss rate cannot be answered with "you picked its
worst run".

Reproduced by the harness itself while validating it: on **click**, seed 0 was
OOM-killed and seed 42 completed; on **chardet**, the two seeds returned
different graphs. Both are recorded in `~/traceweave-data/static/*/pycg.json`.

### 4.2–4.3 Mapping its names onto our nodes

PyCG names things `<module.dotted.path>.<qualified_symbol>` — nearly our scheme,
and "nearly" is where fabricated headline numbers live. Every name it emits lands
in exactly one of four outcomes, and **the four sum to its node count**, so the
mapping is auditable by arithmetic rather than by trust
(`name_outcomes_sum_matches` in every artifact):

| Outcome | What it is | click |
|---|---|---|
| `mapped` | resolved directly | 519 |
| `namespace_merged` | the same function seen through a shorter root (`types.convert_type` for `click.types.convert_type`) — PyCG emits both as definition nodes with edges split between them | 69 |
| `external` | `<builtin>.getattr`, `re.compile` — out of universe by §2.1 | 573 |
| `unmapped` | a path PyCG invented that is not a definition in the source (`core.Command._stream.read`) | 26 |

The merge is accepted **only when exactly one package root resolves the short
name**, so an ambiguous shortening is never guessed at. Unmerged, this one
behaviour inflated click's miss rate by ~11 points.

---

## 5. Baseline 2: the Pyright-assisted extractor

### 5.1 How a call site becomes an edge

Pyright has no batch mode that answers "what does this call resolve to" —
`--outputjson` returns diagnostics, `--verifytypes` returns coverage. The
language server does, via `textDocument/definition`. So every call site with a
callee identifier is put to `pyright-langserver` at that identifier, the answer's
location is mapped back to a node, and the pair becomes an edge. Where Pyright
answers nothing, our own AST binding resolution answers if it can.

Both resolvers are recorded per edge, which yields a number worth reporting on
its own: **how much does a type checker add over plain name binding?** On click,
669 edges came from Pyright and 19 from the AST fallback.

The session runs **inside the container**, driven by `static/pyright_probe.py`,
not from the host over `docker run -i`. That was not a preference. Driving it
from the host died reproducibly after a few hundred requests with container
`ExitCode 1`, `OOMKilled: false`, empty stderr and nothing in `docker logs`; 400
requests at the same position were fine, node heap size made no difference
(died at 241 with 384 MB, at 209 with 2048 MB), pipelining depth made no
difference, and the individual request that died in a batch answered correctly in
isolation. The failure is in docker's attach path. Inside the container it is a
plain local subprocess, which also means a death is *handleable*: the probe
restarts the server, reopens the file and carries on, and `server_restarts` is
reported.

### 5.2 Exact-line matching only

A definition location is accepted only on an exact line match against an
inventoried node. Pyright resolves plenty of things that are not callables —
`handlers = {}` resolves to its assignment line — and a containment match would
attribute that to whatever function encloses the assignment, **manufacturing an
edge no tool claimed and no run will confirm.**

Every rejection is recorded with a reason (`locate_*` in the artifact):
`class_to_init` (52 on click — a class definition maps to its `__init__`, the
real runtime callee), `class_without_init` (14 — the callee is `object.__init__`,
a C builtin, so out of universe rather than a miss), `overload_redirected` (73),
`no_node_at_definition_line` (49), `definition_not_callable`.

Strictness costs baseline 2 some real edges. Inventing them would cost the paper
its credibility.

### 5.3 Two limits stated in the artifact, not in a footnote

- **`deps_available: false`.** Pyright analyses the repo's own source with no
  installed third-party packages, so a receiver whose type comes from a
  dependency is unresolvable. This weakens **our** extractor and never PyCG, so
  it cannot flatter the H2a headline. `--site-packages` points at a triaged
  environment when one is available.
- **Readiness.** A `definition` request answered before Pyright has analysed the
  file returns empty, which is indistinguishable from "unresolvable" and would
  silently become a static miss. Each file is opened and its first
  `publishDiagnostics` awaited as the readiness signal; a file that never becomes
  ready is recorded as `unready` rather than counted as all-unresolved.

A call site Pyright resolved **into typeshed or a dependency** is *resolved*, and
is counted as external — not as an `UnresolvedDispatch`. §4.4's census is
"statically unresolvable call sites", and `len()` is not one of them; counting
them would swamp the honest-unknowns figure with every builtin call in the
corpus.

---

## 6. The universe: package code, not test code

By default only the repo's own package code is analysed. A test function that
calls into the library is a real caller, but it is a caller the static graph *of
the library* cannot contain, so counting those edges as missed would be free
credit. The demo hit exactly this and held out 153 entry edges for the same
reason.

Phase 2 must trace the same node set. An edge whose caller is not in the
inventory is out-of-universe by §2.1's first condition (both endpoints in-repo),
so it is excluded from the denominator rather than scored as a miss.

`--include-tests` widens it. The choice is recorded as `include_tests` in every
artifact because it moves the denominator.

---

## 7. What is asserted, and where

`tests/test_static.py` — 39 checks, no docker, no network, wired into
`tests/run_checks.sh` as check 7. The invariants are asserted on **click as well
as on fixtures**, because each of them, when it broke during development,
silently deleted data rather than raising:

| Invariant | What it caught |
|---|---|
| node keys injective per module | the property getter/setter collision (§2.3) |
| every call-site owner is an inventoried node | calls inside conditionally-redefined functions attributed to a key that does not exist — 4 owners on click, and every call inside them lost from `S` |
| `site_id`s injective | `a.b().c()` gives the outer and inner Call the same (line, col), collapsing **151 of click's 2129 call sites** — dropped from the request batch and from the unresolved census |
| edge_type buckets sum to the total | — |
| UTF-16 vs UTF-8 columns | LSP requests aimed at the wrong token on any line with a non-ASCII character before the callee |

`tests/fixtures/callsite_taxonomy.py` declares the expected §2.2 classification
of every call site **in its own source**, in `# expect:` comments, and the test
only compares — the same posture as `demo/constructs/`, where each fixture states
its prediction and the script fails if a prediction is wrong.

---

## 8. Change log

| extraction_version | date | change |
|---|---|---|
| 1.0 | 2026-08-17 | Initial, alongside `static/`. Conforms to metric spec 1.0. §2.1 and §2.2 flagged as candidates for a spec 1.1 bump. |
