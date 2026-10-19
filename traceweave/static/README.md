# `static/` — Phase 1 §1.2: the static call graph, twice

This directory produces **`S(r)`**: the set of call edges a static tool predicts
for a repo. Phase 2 produces `R(r)`, what actually happened when the code ran.
The H2a finding is the difference. Everything here exists so that the difference
measures the *tools* and not our naming.

Two baselines, because the obvious attack on the paper is "your extractor is
bad":

| Baseline | What it is | Why it is here |
|---|---|---|
| **PyCG 0.0.8** | the published Python call-graph tool (Salis et al., ICSE 2021) | makes the claim about *the state of the art*. §1.2 calls this non-negotiable. |
| **Pyright-assisted** | our extractor; Pyright 1.1.411 resolves the calls a parser cannot | stronger where types exist; our contribution to the comparison |

They **disagree substantially**, which §1.2 anticipated: *"if they disagree
materially, that disagreement is itself a finding worth a paragraph."* The
per-repo Jaccard is computed so the paragraph has something to cite.

Design decisions, and which way each one biases the result:
**`../docs/static_extraction_spec.md`**. Node and edge definitions are frozen in
`../docs/metric_spec_h2a.md` and are not this directory's to change.

---

## Quick start

```bash
# once per machine (and after any Dockerfile edit)
./build_image.sh

# the fast, no-docker guards -- 39 checks
python3 ../tests/test_static.py

# one repo, both baselines, nothing written outside --data
python3 extract.py run --repos-from ../config/reference_repos.txt \
    --clone-dir ~/traceweave-data/refrepos --limit 3

python3 extract.py report
```

The corpus run belongs on the **execution host** — see `run_corpus.sh` and
`../../docs/MIGRATION.md` §4.

---

## The files

| File | Runs where | What it does |
|---|---|---|
| `nodes.py` | host | The node set, per metric spec §1. One shared `ScopeWalker` so nodes and call sites cannot drift apart. |
| `callsites.py` | host | Every call site, with its `edge_type` per §2.2 — from the caller's AST only, never from what a tool found. |
| `edgeset.py` | host | `S(r)`'s container. Shared so both baselines produce the same kind of object. |
| `pycg_baseline.py` | host | Runs PyCG under the seed policy; maps its names onto our nodes. |
| `pycg_graph.py` | **container** | One PyCG analysis, full adjacency map on stdout. |
| `pyright_baseline.py` | host | Builds the request batch, maps definition locations back to nodes. |
| `pyright_probe.py` | **container** | Drives `pyright-langserver` and answers the batch. Restarts the server if it dies. |
| `lsp.py` | both | Minimal LSP client: `Content-Length` framing, pipelined requests, UTF-16 columns. |
| `extract.py` | host | The corpus driver: clone at sha → inventory → both baselines → compare → ledger. |
| `Dockerfile`, `build_image.sh`, `provenance.sh` | — | Both tools in one pinned image, plus a record of what landed in it. |
| `run_corpus.sh` | host | The long, unattended corpus run. |

Everything is **stdlib only**, like the rest of this harness.

---

## What it writes

Under `~/traceweave-data/static/`:

```
ledger.jsonl              one record per repo, appended the moment it is durable
<repo>/inventory.json     every node, with kind / callable / lineno
<repo>/callsites.json     every call site, with edge_type and resolved target
<repo>/pycg.json          S from baseline 1, plus the per-seed spread
<repo>/pyright.json       S from baseline 2, plus the unresolved census
<repo>/summary.json       the ledger record for this repo
```

Re-running **resumes**: a repo whose record says `status: ok` is skipped. A repo
where one baseline failed is recorded `partial` and is **retried** — a PyCG OOM
on a small machine must not be permanently mistaken for a finished repo.

### Reading the artifacts

- `pycg.json → run.per_seed` — what each seed did, including OOMs. If
  `deterministic_across_seeds` is `false`, that repo's PyCG graph is one sample of
  a spread, not a value.
- `pycg.json → diagnostics.name_outcomes` — `mapped` / `namespace_merged` /
  `external` / `unmapped`. These **sum to PyCG's node count**
  (`name_outcomes_sum_matches`), so the mapping can be checked by arithmetic.
- `pyright.json → diagnostics.unresolved_by_edge_type` — the start of §4.4's
  `UnresolvedDispatch` census: call sites *no* resolver could settle.
- `pyright.json → edges.counts.provenance` — `pyright` vs `ast_fallback`, i.e.
  how much the type checker actually added over plain name binding.
- `summary.json → baseline_comparison` — `pycg_only`, `pyright_only`, `agreed`,
  `jaccard`.

---

## Measured on the manager host (arm64 Mac, development output)

Three reference repos, `--seeds 0,42`, `--pycg-memory 3g`:

```
repo         nodes  sites   pycg pyright   jacc  unres
chardet        102    722    141     123 0.8082    128
click          540   2129    448     567 0.5639    162
toolz          457    585    111     122 0.4936     55
```

Pyright's pass over click's 2129 call sites took **~13 s** with 0 server
restarts. PyCG is the slow and fragile half: on click, **seed 0 was OOM-killed
and seed 42 completed**, and chardet's two seeds returned different graphs. Both
are the documented behaviour (`scripts/pycg_determinism.py`), now reproduced by
the extraction harness itself and recorded per repo rather than smoothed over.

These are **not corpus records.** MIGRATION.md §4: the corpus is amd64 and is
built on the Linux box.

---

## Gotchas worth knowing before you debug something

| Symptom | Cause |
|---|---|
| PyCG `exit 137` with `--pycg-memory 8g` | The daemon may not have 8 GB to give. Docker Desktop's VM on the Mac is 3.83 GB, so the container is killed at ~3.8 GB and reports OOM. `extract.py` warns when the request exceeds the daemon's total; on the Linux box (38 GB) the limit is real. |
| `all_runs_failed` on a big repo | Every seed died. Look at `run.per_seed` before concluding anything about PyCG's memory needs. |
| `no_python_package_found` | `detect_layout` found no `__init__.py` and no top-level modules. Check the `layout` field — a wrong import root produces a graph whose names cannot be mapped and a spuriously huge miss rate. |
| A repo analysed 3 modules when it has 400 | Same cause. `inventory.counts.modules` is in every artifact for exactly this reason. |
| `files_unready > 0` | Pyright never finished analysing that file. Its call sites are recorded as unanswered, **not** as unresolvable. |
| `server_restarts > 0` | The language server died and the probe restarted it. Work is retried per chunk; the count is reported. |
| Pyright resolves less than expected | `deps_available: false` — no third-party packages installed. Pass `--site-packages` to strengthen it. |

---

## The one thing not to do

Do not "fix" a low edge count by loosening the mapping rules — not
containment-matching Pyright's definitions, not accepting an ambiguous PyCG
namespace merge, not dropping unmapped names. Every one of those makes `S` bigger
and the miss rate smaller by **inventing edges no tool claimed**. The rules are
strict in the direction that costs us numbers, and each is counted so the cost is
visible. `../docs/static_extraction_spec.md` §1 has the full bias table.
