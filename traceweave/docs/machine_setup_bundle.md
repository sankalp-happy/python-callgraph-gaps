# INIT — set up TraceWeave-Core on this machine

**You are Claude. The user has just unzipped this bundle and pointed you at this file. Set the
project up by following the steps below, in order, then report the state.**

This file is self-contained; you do not need any prior conversation. Everything you need to know is
here or in the docs it points at.

---

## 0. What this project is (30-second version)

TraceWeave-Core is a **12-week empirical software-engineering research project** with a hard
deadline of roughly **2026-10-26**. It measures **how many real runtime call edges static
call-graph analysis misses on Python repositories** (hypothesis "H2a"), and releases a benchmark
("DynBench-Core") so others can re-measure it.

It is at the end of **Phase 0** (specs frozen, tooling built and validated). **Phase 1 has not
started.**

The single most important property of this project is **reproducibility discipline**: every base
image is pinned by `sha256` digest, every repo's dependency set is frozen with `pip freeze`, and
three specification documents were deliberately frozen *before* the code that consumes them. Do not
relax any of this to make something work. If something conflicts with a pin, stop and tell the user.

Read these two files early — they are the real orientation:

- `major/traceweave/README.md` — full guide: architecture, every tool, glossary, troubleshooting.
- `major/traceweave/MANIFEST.md` — the pins. §7 lists exactly what blocks Phase 1.

---

## 1. Bundle contents and where things go

```
this-bundle/
├── init.md                  ← you are here
├── major/                   ← the project repo
└── traceweave-data/out/     ← irreplaceable triage provenance (see §4)
```

**Target layout on this machine:**

| From bundle | Goes to |
|---|---|
| `major/` | `~/Project/major/` |
| `traceweave-data/out/` | `~/traceweave-data/out/` |

`~/traceweave-data` is the mutable data root and lives **outside** the repo. It must be under
`$HOME` — Docker Desktop cannot bind-mount `/tmp`, and the whole pipeline depends on bind-mounting
repo working copies into containers. Do not relocate it to `/tmp`.

---

## 2. Check prerequisites first

Run these and report anything missing. **Do not proceed past a missing Docker.**

```bash
docker version --format 'docker server: {{.Server.Version}} arch={{.Server.Arch}}'
git --version
python3 --version
df -h "$HOME" | tail -1
```

Requirements:

- **Docker must be installed and the daemon running.** On macOS that means Docker Desktop is open.
  If `docker version` errors, tell the user to start Docker Desktop and stop here.
- **git** — any recent version.
- **python3** — 3.9+ is fine for the host. The host Python only *drives* containers; all analysis
  runs inside pinned containers. (Notably `sys.monitoring`, needed by the Phase 2 tracer, requires
  3.12 and is only ever used inside the container.)
- **~15 GB free disk** to start. The corpus will want much more later.

> **Expected platform: Apple Silicon Mac (`arch=arm64`).** The project is pinned for both
> `linux/amd64` and `linux/arm64`, and selects automatically. If `arch` reports something else,
> that is fine — just note it in your report, since it changes §6.

---

## 3. Install

```bash
# from inside the unzipped bundle directory
mkdir -p ~/Project
cp -a major ~/Project/

mkdir -p ~/traceweave-data/{work,logs,traces,candidates,refrepos}
cp -a traceweave-data/out ~/traceweave-data/

# zip does not reliably preserve the executable bit
chmod +x ~/Project/major/traceweave/triage/triage.sh
chmod +x ~/Project/major/traceweave/scripts/*.sh
chmod +x ~/Project/major/traceweave/scripts/*.py
chmod +x ~/Project/major/traceweave/tests/run_checks.sh
```

Then confirm the provenance survived the trip:

```bash
ls ~/traceweave-data/out/*/py*/
wc -l ~/traceweave-data/out/click/py3.12/lock.txt        # expect 9
grep lock_sha256 ~/traceweave-data/out/click/py3.12/result.env
```

The last command must print exactly:

```
lock_sha256=10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
```

If it does not, the bundle is corrupt — stop and tell the user.

---

## 4. Why `out/` was shipped rather than regenerated (do not "refresh" it)

`~/traceweave-data/out/<repo>/py<ver>/lock.txt` records **what PyPI resolved on 2026-07-27** —
`pytest==9.1.1`, `packaging==26.2`, `setuptools==83.0.0`, and so on. Re-running triage resolves
*newer* versions, which changes `lock_sha256`, which changes the repo's identity 5-tuple:

```
(repo_url, sha, pyver, base_image_digest, lockfile_sha256)
```

Guarding against exactly that drift is the reason the lockfile exists. `attempt.log` is likewise
evidence, not output: it is what the two triage classifiers were computed from.

**So: never delete or regenerate `out/` to "clean up".** The one sanctioned re-run is §6, and that
is a deliberate cross-platform comparison whose result gets recorded.

---

## 5. Verify the install

```bash
cd ~/Project/major/traceweave
./tests/run_checks.sh
```

**Expect `passed: 6   failed: 0`.** The six checks are:

| # | Checks |
|---|---|
| 1 | Density scorer produces **zero** features for `re.compile`, `@t.overload`, `@v.setter`, bare `sys.modules` read. These were four real false-positive bugs found during calibration; this guards the fixes. |
| 2 | All 9 dynamic features still detected on the positive fixture. |
| 3 | Tiny input → `TOO_SMALL`, and the per-KLOC denominator floor holds (without it a 29-line file scored 701). |
| 4 | All 5 images × 2 platforms pinned by `sha256:` digest. |
| 5 | Licence mapping reproduces the qualification answers in `major/ins3.md` §2 — requests→`Apache`, click→`BSD`, django→`BSD`. Needs network; auto-skips without. |
| 6 | The resolved image platform **matches the host**, i.e. no silent emulation. |

If check 6 fails, stop — it means Docker would run a foreign-architecture image. That still
*works*, which is the danger: results look correct while every timing measurement is meaningless.

Then the heavier sweep, which needs ~250 MB and a few minutes:

```bash
cd ~/traceweave-data/refrepos
xargs -P7 -I{} sh -c 'git clone --quiet --depth 1 {} "$(basename {})"' \
    < ~/Project/major/traceweave/config/reference_repos.txt

cd ~/Project/major/traceweave
./tests/run_checks.sh --full
```

**Expect `HIGH=6 LOW=3 MED=4 TOO_SMALL=1`.**

If the distribution differs, do **not** adjust the scorer thresholds — they are frozen in
`docs/density_scorer_spec.md`. The likely cause is benign: the clones are `--depth 1` of *current*
upstream HEAD, so the repos have moved since calibration on 2026-07-27. Report the actual numbers
and let the user decide.

---

## 6. The one real task: re-triage on this platform

`click` and `records` were triaged on **linux/amd64**. Their lockfiles are amd64 resolutions, and
this machine is (probably) arm64. Re-run them:

```bash
cd ~/Project/major/traceweave/triage
./triage.sh https://github.com/pallets/click
./triage.sh https://github.com/kennethreitz/records
```

Each takes roughly 1.5–3 minutes. Then report:

```bash
grep -E '^(platform|host_arch|emulated|status|lock_sha256|python_full)=' \
    ~/traceweave-data/out/click/py3.12/result.env
```

**This comparison is real data, not busywork.** Both repos have pure-Python dependency trees, so
`lock_sha256` will probably be *unchanged* (`10dc90ae86e4b7…`).

- **If it matches:** good evidence that pure-Python corpora are platform-portable. Worth a sentence
  in the paper's reproducibility section. Tell the user.
- **If it differs:** a compiled-wheel dependency has been found, and the corpus is platform-locked
  from here on. This is more important — flag it clearly.

Either way `platform` should read `linux/arm64` and `emulated` should read `no`.

`nope-xyz` is a deliberate bad-URL test case. Do **not** re-run it and do not treat it as a
failure; it fails at clone, before any container starts.

---

## 7. Put it under version control

The project is **not yet a git repository**, so none of the pinning discipline has history behind
it. Ask the user before committing, then:

```bash
cd ~/Project/major
git init
git add -A
git commit -m "Phase 0 complete: pins, specs, triage, density scorer, SOP v1.1"
```

A `.gitignore` is already present. It deliberately **does not** ignore corpus provenance — see
`major/MIGRATION.md` §5 for the option of moving `out/` in-tree as `corpus/` (~4 MB at full corpus
size), which makes a clone a complete self-verifying record.

---

## 8. Report back, then stop

Summarise for the user:

1. Prerequisite versions found, and the detected architecture.
2. `run_checks.sh` result (expect 6/6) and `--full` distribution.
3. The `lock_sha256` comparison from §6 — **matched or changed**, and what that implies.
4. Anything that failed, quoted verbatim rather than paraphrased.
5. The Phase 1 blockers below.

**Do not start Phase 1 work unless the user asks.** Setup is the job.

### Phase 1 blockers (from `MANIFEST.md` §7)

| # | Task |
|---|---|
| 1 | **Pin the Pyright version.** Needed for static baseline 2. An earlier `npm view pyright version` returned only notices; retry and record it in `MANIFEST.md` §2. |
| 2 | **Install PyCG 0.0.8** in its own container and measure its parse-failure rate on the 14 reference repos. It is the published Python call-graph baseline (ICSE 2021) but years old, so it may not parse modern syntax — **that failure rate is itself a reportable result**, not a defect to work around. |
| 3 | **Build `triage/runner.py`** — parallel queue walking the recipe ladder in `config/base_images.json`. ~6–8 concurrent jobs. |
| 4 | **Build `scripts/discover_candidates.py`** — discovery to ~450 candidates, density-scored and interleaved by stratum. |

---

## 9. Rules that must not be quietly broken

These are not style preferences; each one protects a published claim.

1. **Never reference a base image by tag** (`python:3.12-slim`). Always by digest, via
   `scripts/resolve_image.py`. Tags move.
2. **Never edit a frozen spec to fit a result.** `docs/metric_spec_h2a.md`,
   `docs/density_scorer_spec.md`, and the pins in `MANIFEST.md` are frozen. Changing one requires a
   version bump, a dated changelog entry, and re-running what depended on it.
3. **Never silently drop a repo.** Failures are data — they become the tracing-feasibility survey.
   Excluded repos are listed with a reason. Silent drops create survivorship bias in the released
   benchmark.
4. **`AMBER` repos are usable.** A repo whose tests fail but which *runs* is exactly what this
   project needs, because running code is what gets traced. Only `RED` is unusable.
5. **Never publish absolute timings from this machine.** Docker Desktop runs containers in a VM and
   bind-mount I/O is slow. Report traced÷untraced **ratios**, which cancel the penalty.
6. **No LLM-as-judge** in validation or headline metrics — only in clearly-marked failure analysis.
7. **Never modify a corpus repo's source code** to make it build. That is the annotator SOPs' first
   hard rule and it applies to you too.
