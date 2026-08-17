# Live demo: watch a call graph miss a real call

The page opens in **presentation mode**: one plain-language screen with the
click call graph replaying itself, a running tally, and three sentences. That
is what a non-technical jury should see, and nothing on it runs any analysis —
it reads JSON already committed under `explainer/public/live/`, so there is
nothing that can be slow or run out of memory while people are watching.

### Driving the graph on stage

| Control | What it does |
|---|---|
| Replay execution / Pause | Replays the trace; the whole thing plays in ~20s regardless of length |
| slider | Scrub to any moment, or freeze on one worth talking about |
| Fit | Re-frames the whole graph. Use it if you have panned somewhere odd |
| Full screen | Fills the display. Wheel zoom is enabled only here |

The graph deliberately does **not** capture the scroll wheel on the page — it
is 520px of a ~720px viewport, so if it zoomed on wheel there would be no way
to scroll past it. Drag pans; wheel scrolls the page; zoom lives in full
screen. Clicking a module opens it into the functions that have run so far and
pauses the replay, because a drilled-in module re-lays-out as new functions
arrive and would otherwise shuffle while being read.

**Show the detail** reveals everything below, for a technical follow-up:

Four things are then on the page, in increasing order of how much they prove:

| | What it shows | Script |
|---|---|---|
| Live run | One 20-line fixture, traced live on stage | `run_demo.sh` |
| Real repository | click's 16 analysable modules under its own 1,939-test suite | `run_real.sh` |
| Construct taxonomy | 10 fixtures, one per construct class, each with a stated prediction | `build_constructs.py` |
| Tool behaviour | PyCG's own scaling curve and run-to-run reproducibility | `../scripts/pycg_scaling.py`, `../scripts/pycg_determinism.py` |

One-time setup:

```bash
./build_image.sh
```

## 1. The live run (what you drive on stage)

```bash
./reset_demo.sh   # clear any stale prior run
./run_demo.sh      # generates RUN_ID, writes static.json + runtime.json
```

The page's **Start new run** button does not start anything — it records the
current `run_id` as a floor and waits for a higher one. You still have to run
`run_demo.sh` in a terminal.

`fixture.py` is the toy plugin registry PyCG 0.0.8 cannot resolve: it sees
`dispatch()` call `getattr(...)`, but not the `handle_email()` the getattr
call actually returns. Confirmed by running PyCG directly against this file —
see `tests/fixtures/fixture_static_golden.json` for its real output.

**Measured timing** (this machine, 2026-08-15, image already pulled/built):
warm end-to-end runs took **0.35s–2.7s**; a full image *rebuild* after
deleting the tagged image took **~1.5s**. A **15s fallback threshold** gives
5–40x headroom over every observed warm run — use `./restore_fallback.sh` if
nothing has landed by then. This does not cover a genuinely cold `docker pull`
on a machine that skipped the pre-warm step.

Re-measure on the actual presentation machine during the full rehearsal
rather than trusting this number blind.

## 2. The real repository

```bash
./run_real.sh      # ~30s: PyCG in Docker, then click's test suite under the tracer
```

Writes `real_static.json`, `real_runtime.json` and `real_summary.json`. Needs
a click clone at `~/traceweave-data/refrepos/click` (override with
`CLICK_REPO`); the pinned SHA is `00e592c`, the one triage certified.

What the pipeline does, and the three places it deliberately gives PyCG the
benefit of the doubt:

1. **Entry edges are held out.** A call entering click from outside the
   analysed set has no possible counterpart in a static graph of click, so
   counting it as missed would be free credit. 153 edges, excluded.
2. **PyCG's duplicate names are merged.** PyCG emits click's own submodules
   under two namespaces at once — `click.types.convert_type` *and*
   `types.convert_type`, both as definition nodes, with edges split between
   them. 44 functions were affected; unmerged, that alone inflates the miss
   rate by ~11 points.
3. **Two arguable buckets are held out of the headline**, from both numerator
   and denominator: comprehension/lambda scopes (not functions a call-graph
   tool models) and property getters (a real frame, but not a syntactic call
   site).

`tracer.py summarize` refuses to emit a result above a 90% miss rate, on the
grounds that such a number is far more likely to be a qualified-name mismatch
than a real finding.

### The control group

Read `bare-call` first. A plain `foo()` is the easiest edge there is, and PyCG
found 164 of 169 of them. That is what separates "PyCG misses dynamic
dispatch" from "our harness cannot match names" — a broken harness would have
failed the control too.

## 3. Construct fixtures

```bash
./build_constructs.py
```

One directory per construct under `constructs/`, each declaring in its own
`META` the edge it predicts will be missed (or found). The script verifies
every prediction and exits nonzero if any fails.

Two fixtures originally predicted a miss and were **wrong** — PyCG resolves
indirect construction and slot-held callbacks at fixture scale, even through a
dict lookup. Their expectations were corrected rather than the fixtures being
reshaped until they failed. What survives is the more useful finding: those
constructs are resolvable in twenty lines and missed 39/47 and 57/65 times in
click. Scale, not syntax, is what defeats the analysis — so any fixture-only
benchmark understates the problem.

## 4. How PyCG itself behaves

```bash
python3 ../scripts/pycg_scaling.py --repo ~/traceweave-data/refrepos/click \
    --package src/click --src-root src --last testing.py \
    --out ../../explainer/public/live/scaling.json

python3 ../scripts/pycg_determinism.py --repo ~/traceweave-data/refrepos/click \
    --package src/click --src-root src --seeds none,0,1,42 --repeats 3 \
    --out ../../explainer/public/live/determinism.json
```

Both were found while measuring something else:

- **The graph is not monotonic.** Several steps of the cumulative scaling run
  produced *fewer* nodes than the step before. Showing the analyser more of
  the program made its picture of the program smaller, so the graph is not a
  sound over-approximation and a subset of a repo can score better than the
  whole.
- **The graph is not reproducible.** On all 17 modules, identical invocations
  returned 1137, 1160 and 1286 nodes on different runs, and other identical
  invocations exhausted 8GB and were OOM-killed. PyCG's fixpoint iterates over
  sets, so `PYTHONHASHSEED` — random per process by default — changes both
  which fixpoint is reached and whether one is reached at all.

The second point constrains this project's own numbers: the click miss rate
comes from a single PyCG run and is therefore one sample of that spread. A
published figure needs a seed policy and repeated runs.

Do not restate any of this as "PyCG cannot parse `testing.py`". Excluding
`testing.py`, the other 16 modules analyse in ~1.5s at ~36MB every time;
including it is what makes the behaviour unstable.

## Tests

```bash
python3 tracer.py selftest      # 16 checks: naming, diff, threads, entry holdout
cd ../../explainer && npx vitest run
```
