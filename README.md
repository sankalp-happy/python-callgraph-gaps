# What Python Call Graphs Miss: Implicit Calls and Shared Names, Not Reflection

**Adarsha S P, Sankalp Shankar, Surabhi Singh, Pravith S Upadhyaya, Abhishek Kumar**
Dept. of AI & ML, Acharya Institute of Technology, Bangalore, India

This repository holds the paper, its data, and the pipelines that produced the data. Every number
in the paper is computed from files in this repository by [`paper/make_numbers.py`](paper/make_numbers.py).

## Summary

Python call-graph generators are mostly evaluated on micro-benchmarks. We ran PyCG and a
Pyright-based extractor on 105 pip-installable GitHub repositories. PyCG failed on 22% of the 100
it was run on, and across ten hash seeds its call graph changed on 21 of 77 repositories. Where the
test suites could be traced (39 repositories), we scored both analysers against the calls the tests
actually made between a project's own functions. The union of the two analysers finds a median of
0.69 of those calls. Of the calls it misses, 57% reach functions the caller never names (special
methods, library callbacks) and 30% go through method names shared by several classes; reflection
accounts for only 2%. Three open-weight LLMs, choosing among the names on a caller's executed lines,
raise recall from 0.65 to 0.79–0.87 but lower precision from 0.83 to 0.60–0.70. Combining static and
LLM answers lifts F1 on unseen repositories only from 0.73 to 0.76.

## Citation

```bibtex
@inproceedings{sp2026callgraphs,
  title     = {What Python Call Graphs Miss: Implicit Calls and Shared Names, Not Reflection},
  author    = {S P, Adarsha and Shankar, Sankalp and Singh, Surabhi and Upadhyaya, Pravith S and Kumar, Abhishek},
  booktitle = {TBD},
  year      = {2026},
  note      = {Code and data: https://github.com/sankalp-happy/python-callgraph-gaps}
}
```

## Rebuild the paper

Everything below runs from a fresh clone on a laptop: no Docker, no network, no harness checkout.

```bash
python3 paper/make_numbers.py > /tmp/numbers.tex && cmp /tmp/numbers.tex paper/numbers.tex
```

`make_numbers.py` uses only the Python standard library (3.10+). It reads `phase1-results/`,
`study1-results/`, `candidates/`, `traceweave/config/`, `traceweave/study1/repos.tsv` and
`paper/harness-inputs/`, and prints one `\newcommand` per number the paper quotes. `cmp` printing
nothing means the committed `numbers.tex` is exactly what the data gives.

```bash
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

This needs a TeX distribution with `IEEEtran` (TeX Live, MacTeX or BasicTeX). The result is six
pages. `python3 paper/make_fig.py` redraws Fig. 1 (`fig_recall.pdf`) and needs matplotlib.

## Repository map

| Path | What it holds |
|---|---|
| [`paper/`](paper/) | The paper (`main.tex`, `rq34.tex`, `refs.bib`), the committed `main.pdf`, and the two scripts that turn data into `numbers.tex` and Fig. 1. `harness-inputs/` holds the four harness outputs five of the macros read (see below). |
| [`phase1-results/`](phase1-results/) | Phase 1, RQ1–RQ2: triage ledger, static-extraction ledger, and `summary.json` + `pycg.json` for each repository. `RUN_REPORT.md` (with its 2026-10-19 erratum) and `PROVENANCE.md` describe the run. |
| [`study1-results/`](study1-results/) | Study 1, RQ3–RQ4: per-repository ledger, bench outputs, logs and environment locks, plus the pooled JSON each paper section reads. |
| [`traceweave/`](traceweave/) | All pipeline code: discovery and scoring (`scripts/`), triage (`triage/`), static extraction (`static/`), the runtime tracer (`demo/tracer.py`), Study 1 (`study1/`), pins (`config/`), tests. [`traceweave/MANIFEST.md`](traceweave/MANIFEST.md) is the reproducibility anchor: every pin and digest. |
| [`candidates/`](candidates/) | Discovery output: the scored, stratified 558-repository queue drawn from 98,416 matched GitHub repositories. |
| [`corpus/`](corpus/), [`corpus.amd64-baseline/`](corpus.amd64-baseline/) | Early triage provenance (`result.env`, `lock.txt`, `attempt.log`) on arm64 and amd64, kept as a cross-architecture comparison. |
| [`docs/`](docs/) | Working documentation: [`PRIMER.md`](docs/PRIMER.md), [`MIGRATION.md`](docs/MIGRATION.md) (which host runs what), [`RUN_ON_LINUX.md`](docs/RUN_ON_LINUX.md) (the two long runs), plans, annotator SOPs and discovery reports. |
| [`handoff/`](handoff/) | Operator sheets generated for the annotators. |
| [`presentation/`](presentation/) | Phase-II review deck, speaker script and viva questions. |
| [`explainer/`](explainer/) | A Vite + React explainer and live demo; `project-explainer.html` at the root is its published single-file build. |

## How each result was produced

### Corpus (candidates, triage)

`traceweave/scripts/discover_candidates.py` and `density_score.py` built and stratified the 558-repository queue in `candidates/`.
`traceweave/triage/runner.py` then drove `triage.sh` over it. For each repository, triage installs it in a
digest-pinned `python:3.12` image, runs its tests and records an admit/reject decision with the
frozen dependency lock. Result: `phase1-results/triage/ledger.jsonl` (240 triaged, 118 admissible).

### Phase 1: static extraction (RQ1, RQ2)

`traceweave/static/extract.py`, driven by `run_corpus.sh`, extracts both static call graphs onto one
shared node set per repository, inside the pinned `traceweave-static` image (Python 3.10, PyCG 0.0.8,
Pyright 1.1.411; image digest in `phase1-results/PROVENANCE.md`). It runs PyCG under three hash
seeds with a 30-minute budget per seed, and Pyright through its language server. The three patches
the run was made with are in `phase1-results/patches/` and are committed in `traceweave/static/`.

Hardware: one x86-64 Linux host (AMD Ryzen 7 7840HS, 8 cores / 16 threads, 38 GiB RAM, Ubuntu 22.04,
Docker Desktop with a 26 GiB VM ceiling). Output: `phase1-results/` (105 attempted, 100 with
artifacts, 78 where both analysers finished).

**Full Phase 1 output.** Git holds only the files the paper reads. The complete tree, adding each
repository's `inventory.json`, `callsites.json` and `pyright.json` (about 200 MB unpacked), is the
`phase1-results.tar.gz` asset on the
[`v1.0-paper` release](https://github.com/sankalp-happy/python-callgraph-gaps/releases/tag/v1.0-paper).
Unpack it over the clone with `tar xzf phase1-results.tar.gz -C phase1-results`.

### Study 1: runtime traces and LLM resolution (RQ3, RQ4)

The scripts in [`traceweave/study1/`](traceweave/study1/) ran the 40 sampled repositories
(`repos.tsv`, two rounds of 20). They produced `study1-results/` as follows:

| Script | What it does | Output in `study1-results/` |
|---|---|---|
| `batch.py` | Per repository: clone at the pinned SHA, build a venv, trace the test suite with `traceweave/demo/tracer.py`, build the graph bundle, derive the ground-truth calls, and freeze the LLM sample. Resumable. | `ledger.jsonl`, `bench/`, `logs/`, `env/` |
| `resolve_all.sh`, `resolve_loop.sh` | Ask gpt-oss-20b, gpt-oss-120b and qwen3.8-27b (served by Groq) to resolve each sampled caller. | (harness `results/resolve/`, read by the scripts below) |
| `retrace.sh` | Trace every finished suite a second time, to measure how stable the observed calls are. | (harness `bundles/<repo>/truth.run2.json`, read by `collect.py`) |
| `collect.py` | Pool recall, item scores, miss classes and the static+LLM combiner over every traced repository. | `rq34.json` |
| `sweep.py` | Re-run PyCG under ten hash seeds and score each seed against the traced calls; `iterprobe` caps and logs PyCG's fixpoint. | `seeds.json`, `seeds.tar.gz`, `iterprobe/` |
| `review_stats.py` | Recall over all observed calls, an exclusive decomposition of misses, a reflection test, and the serving-model strings. | `review.json` |
| `loro.py` | Leave-one-repository-out combiner predictions per item, for paired bootstraps. | `loro_all.jsonl`, `loro_noref.jsonl` |
| `d1_mapping.py` | Audit how much of PyCG's low recall is our name mapping rather than PyCG. | `d1_mapping.json` |

`unnamed.json` pools the harness's `bench.unnamed` breakdown over the same bundles.

Hardware: an Azure Standard_D4s_v4 VM (4 vCPU, 16 GiB RAM, Ubuntu 24.04, x86-64). `click` and `toolz`
were traced earlier on an arm64 machine during development; both are pure Python. As the paper's
threats section says, Study 1 installs each repository with the triage recipe rather than from its
frozen lock.

### Dependency on the TraceWeave harness

`batch.py`, `collect.py`, `loro.py`, `d1_mapping.py`, `review_stats.py` and `sweep.py` import
modules (`bench`, `resolve`, `ml`, `graph`, `sandbox`) from a separate repository,
`traceweave-harness`, and drive its `tw.py` CLI (`truth`, `bench`, `resolve`). That repository is
**not public**. This means:

- **Rebuilding the paper does not need it.** Every Study 1 number is read from the committed
  `study1-results/`. Five macros (ShivyC's `make_il`/`make_asm` counts, the `click`/`toolz` sample
  sizes, and the pilot's fused failures) are computed from four harness outputs. Those files are
  vendored under [`paper/harness-inputs/`](paper/harness-inputs/) in the harness's own layout. Set
  `TW_HARNESS=/path/to/traceweave-harness` to read a live checkout instead.
- **Re-running Study 1 does need it.** Without the harness, the Study 1 scripts document what was
  run, but they cannot be executed.

## Licence

The code, documentation and derived data in this repository are released under the [MIT licence](LICENSE).

The corpus repositories keep their own licences. This repository does not redistribute their source
trees: it ships only identifiers and pins (URLs, commit SHAs, dependency locks) and data derived from
running tools on them (call edges, qualified names, test outcomes, and the short line edits in LLM
answer logs). Which repositories enter the corpus is gated on licence (`traceweave/MANIFEST.md` §7).
