# Density Scorer Spec & Calibration Record

| | |
|---|---|
| **status** | **CALIBRATED AND FROZEN 2026-07-27** |
| **scorer_version** | `1.0` (`scripts/density_score.py`, `SPEC_VERSION = "1.0"`) |
| **companion** | [`metric_spec_h2a.md`](metric_spec_h2a.md) §5 |

Implements amendment 3 of SOP v1.1: candidates are binned LOW/MED/HIGH **before** triage, and
the candidate sheet is interleaved by bin so that stopping early still leaves balanced strata.

---

## 1. Design commitments

| Commitment | Rationale |
|---|---|
| **AST-based, never grep** | `getattr` in a docstring is not a call site. A grep scorer bins repos on their prose. |
| **`getattr(o, "literal")` weighted 0.3 vs `getattr(o, name)` at 2.0** | The literal form is statically resolvable and is *not* a blind spot. Conflating them is the commonest way to overstate dynamic density. |
| **Source and tests scored separately; stratum from source only** | Test suites use `getattr`/`mock`/`monkeypatch` for reasons unrelated to the repo's architecture. Scoring together makes every pytest-using project look HIGH. |
| **Builtin features require an unqualified call** | See §3, bug 1. `re.compile` is not `compile`. |
| **Per-KLOC denominator floored at 1000 SLOC** | Below 1 KLOC, per-KLOC *amplifies* instead of normalising (a 29-SLOC fixture scored 701). The floor biases small repos conservatively toward LOW; intended. |
| **Repos under 500 SLOC → `TOO_SMALL`, excluded with a recorded reason** | Not research subjects. Never silently dropped. |
| **stdlib only** | Runs in a bare `python:3.12-slim` with no pip install. |
| **Run containerised on 3.12, never on the host** | The host is 3.10 and cannot parse 3.11+ syntax; parse failures would silently undercount. |

---

## 2. Observed distribution (14-repo reference set, 2026-07-27)

Scored inside `python@sha256:cab2dbf5…` (see `MANIFEST.md` §1). **Zero parse failures** except
12 files in `TheAlgorithms/Python`.

| score | stratum | repo | source SLOC | a-priori | agrees? |
|---:|---|---|---:|---|---|
| 18.87 | HIGH | celery | 35 083 | HIGH | ✅ |
| 17.39 | HIGH | click | 10 384 | MED | ~ (defensible: `@click.command` *is* a registry) |
| 17.34 | HIGH | pytest | 30 922 | HIGH | ✅ |
| 16.74 | HIGH | flask | 7 385 | HIGH | ✅ |
| 13.59 | HIGH | django | 127 974 | HIGH | ✅ |
| 10.47 | HIGH | sqlalchemy | 179 429 | HIGH | ✅ |
| 9.03 | MED | scrapy | 24 303 | HIGH | ~ |
| 7.91 | MED | requests | 4 893 | LOW | **a-priori was wrong** — see §4 |
| 7.82 | MED | toolz | 3 146 | LOW | **a-priori was wrong** |
| 7.48 | MED | ansible | 102 548 | HIGH | ~ (per-KLOC dilution, §4) |
| 3.10 | TOO_SMALL | records | 495 | — | ✅ |
| 2.10 | LOW | TheAlgorithms/Python | 91 990 | LOW | ✅ |
| 0.90 | LOW | black | 99 747 | LOW | ✅ |
| 0.36 | LOW | chardet | 9 618 | LOW | ✅ |

**Final bins: 6 HIGH / 4 MED / 3 LOW / 1 TOO_SMALL.**

### Frozen thresholds
```
LOW   : score <  4.0
MED   : 4.0 <= score < 10.0
HIGH  : score >= 10.0
```
Chosen at the two natural gaps in the observed distribution: **2.10 → 7.48** and **9.03 → 10.47**.

---

## 3. Bugs found and fixed during calibration

The first calibration run put **10 of 14 repos in HIGH** — no discrimination at all. Four
distinct false-positive sources, all fixed before freezing:

1. **`re.compile` counted as `eval_exec` (weight 3.0).** The rule matched the trailing dotted
   component, so every `re.compile` looked like dynamic code execution. This alone drove
   `requests` to a spurious HIGH. **Fix:** builtin-derived features now require an unqualified
   `ast.Name` call (or explicit `builtins.x`). Codified as `BUILTIN_FEATURES`.
2. **`registry_decorator` over-fired on typing/protocol decorators.** `click` scored
   16.4 registry-decorators/KLOC composed almost entirely of `@t.overload` and `@v.setter`.
   **Fix:** `NON_REGISTRY_DECORATORS` denylist (property protocol, typing, abc, functools,
   contextlib).
3. **`importlib.metadata` mislabelled as framework "importlib".** A dotted match recorded the
   *top-level* package, so nearly every repo collected a spurious +1.5 framework bonus for
   ordinary version lookup. **Fix:** exact-match first; `importlib.metadata`,
   `importlib_metadata`, and `pkg_resources` removed from `FRAMEWORK_MODULES` entirely. Genuine
   plugin discovery is now caught precisely by the `entry_points` *call* feature.
4. **`sys.modules` counted on bare reads.** `if "os" in sys.modules` is ordinary.
   **Fix:** only mutation counts — subscript assignment, `del`, or a mutator method
   (`pop`/`setdefault`/`update`/`clear`/`popitem`). Weight lowered 2.0 → 1.0.

**Regression guard:** a fixture containing `re.compile` ×2, `@t.overload` ×2, `@v.setter`,
`@property`, and a bare `sys.modules` read must yield **zero** features. Verified.

---

## 4. Two honest caveats to carry into the paper

**The scorer corrected two of my a-priori labels, and it was right.** `requests` was expected
LOW but contains genuine dynamic imports:

```python
# src/requests/packages.py:9
locals()[package] = __import__(package)
# src/requests/compat.py:42
chardet = importlib.import_module(lib)
```

That is precisely the edge class H2a is about. `toolz` similarly uses `globals()` in `curry`.
Where the a-priori label and the scorer disagreed, the scorer was correct — which is mild
evidence the metric tracks something real, and it is reported rather than quietly reconciled.

**Per-KLOC dilutes large repos.** `ansible` has 152 dynamic `getattr` sites but 102 k SLOC, so
its *average* density lands in MED even though its plugin loader is a canonical dynamic-dispatch
case. This is a real property of a per-KLOC metric (which is what `research_plans.md` §D2-M0
specifies), not a bug. Two consequences:

1. **The continuous `density_score` is the primary covariate.** Miss-rate is regressed on the
   continuous score; bins are for sampling balance and readable table strata only. A bin
   boundary is not a claim about a repo.
2. Concentrated-hotspot density (max per-module score) is noted as possible future work; it is
   not needed for stratified sampling.

---

## 5. Feature weights (frozen)

| feature | weight | notes |
|---|---:|---|
| `dynamic_import` | 3.0 | `importlib.import_module`, `__import__` |
| `eval_exec` | 3.0 | unqualified `eval`/`exec`/`compile` only |
| `entry_points` | 3.0 | `iter_entry_points`/`load_entry_point`/`entry_points` |
| `attr_protocol` | 2.5 | `__getattr__`/`__getattribute__`/`__setattr__`/`__delattr__` defs |
| `getattr_dynamic` | 2.0 | non-literal name |
| `setattr_dynamic` | 2.0 | non-literal name |
| `dynamic_class` | 2.0 | 3-arg `type()`, `metaclass=` |
| `subclass_walk` | 2.0 | `__subclasses__()` |
| `subscript_call` | 1.5 | `handlers[key]()` |
| `dispatch` | 1.5 | `singledispatch`, `*register` |
| `registry_decorator` | 1.0 | attribute-style decorator, minus denylist |
| `namespace_access` | 1.0 | `globals()`/`locals()`/`vars()` |
| `sys_modules` | 1.0 | mutation only |
| `getattr_literal` | 0.3 | statically resolvable |
| `setattr_literal` | 0.3 | statically resolvable |
| *framework presence* | +1.5 each | flat, not per-KLOC |

```
score = (Σ weightᵢ · countᵢ) / (max(source_SLOC, 1000) / 1000)  +  1.5 · |frameworks|
```

---

## 6. Change log

| scorer_version | date | change |
|---|---|---|
| 1.0 | 2026-07-27 | Initial calibration on 14 reference repos. Four false-positive classes fixed (§3). Thresholds frozen at 4.0 / 10.0. |
