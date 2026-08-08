# Migrating TraceWeave-Core to another machine

**Short answer: migrate two things, regenerate one.**

| What | Where | Size | Action |
|---|---|---|---|
| **The project repo** | `~/Project/major/` | **1.5 MB** | ✅ **migrate** |
| **The triage provenance** | `~/traceweave-data/out/` | **72 KB** | ✅ **migrate — cannot be regenerated** |
| Reference clones | `~/traceweave-data/refrepos/` | 250 MB | ♻️ regenerate (one command) |
| Working copies | `~/traceweave-data/work/` | 11 MB | ♻️ regenerate (triage re-clones) |
| Empty dirs | `candidates/`, `logs/`, `traces/` | 0 | ♻️ recreated automatically |
| Docker images | local daemon | ~150 MB | ♻️ re-pulled **byte-identically** by digest |

Total to move: **~1.6 MB.** You do not need to move the 260 MB data root.

---

## 1. Why `out/` cannot be regenerated

This is the one thing that would silently break if you re-ran triage on the new machine instead of
copying it.

`~/traceweave-data/out/<name>/py<ver>/lock.txt` records **what PyPI resolved on 2026-07-27**:

```
click @ file:///repo
iniconfig==2.3.0
packaging==26.2
pluggy==1.6.0
Pygments==2.20.0
pytest==9.1.1
pytest-timeout==2.4.0
setuptools==83.0.0
wheel==0.47.0
```

Re-run `triage.sh` next month and pip resolves `pytest==9.1.2`, a newer `setuptools`, and so on. That
changes `lock_sha256`, which changes the repo's identity 5-tuple
`(repo_url, sha, pyver, base_image_digest, lockfile_sha256)` — and **resolution drift is exactly what
amendment 1 exists to prevent.** `sha_resolved` would also move if the upstream repo's HEAD advanced.

`attempt.log` is likewise evidence, not output: it is what the two classifiers (`error_class_v10` /
`error_class_v11`) were computed from, so it backs the classifier-disagreement number that goes in
the paper.

Logs are 0.5–11 KB each, so at 450 candidates the whole `out/` tree is only ~4 MB. **It belongs in
version control** — see §5.

---

## 2. On the old machine

```bash
cd ~/Project
tar czf traceweave-migrate.tar.gz \
    major/ \
    -C "$HOME" traceweave-data/out
ls -lh traceweave-migrate.tar.gz     # ~1.6 MB
```

That captures:
- `traceweave/` — all code, specs, fixtures, pins
- `ins1.md`, `ins2.md`, `ins3.md` — the annotator SOPs the whole design references
- `research_plans.md`, `final_paper.pdf` — the parent research docs (`README.md` links to both by relative path, so keep them together)
- `given-the-convo-history-cheerful-pizza.md` — the approved 12-week plan
- `traceweave-data/out/` — the irreplaceable provenance

## 3. On the new machine

```bash
# 1. unpack
mkdir -p ~/Project && cd ~/Project
tar xzf /path/to/traceweave-migrate.tar.gz
mv traceweave-data ~/                     # if the tar placed it here
mkdir -p ~/traceweave-data/{work,logs,traces,candidates,refrepos}

# 2. verify the code is intact (no docker, no network needed for checks 1-4)
cd ~/Project/major/traceweave
./tests/run_checks.sh

# 3. regenerate the reference clones (~250 MB, a few minutes)
cd ~/traceweave-data/refrepos
xargs -P7 -I{} sh -c 'git clone --quiet --depth 1 {} "$(basename {})"' \
    < ~/Project/major/traceweave/config/reference_repos.txt

# 4. confirm the frozen calibration still reproduces
cd ~/Project/major/traceweave
./tests/run_checks.sh --full        # expects HIGH=6 LOW=3 MED=4 TOO_SMALL=1
```

If step 4 reports a drifted distribution, **stop** — either the scorer changed or the upstream repos
moved (the clones are `--depth 1` of *current* HEAD, not the shas recorded in `out/`). Investigate
before admitting anything to the corpus.

**You do not need to move Docker images.** `config/base_images.json` pins by `sha256:` digest, so
`docker run python@sha256:cab2dbf5…` on the new machine pulls the byte-identical image. That is the
whole payoff of pinning by digest instead of tag.

---

## 4. Platform: Apple Silicon — already handled ✅

**Target machine is an Apple Silicon Mac (arm64). The work is done; no hand-editing required.**

`manifest_version` is now `1.1` and `config/base_images.json` carries digests for **both**
platforms, all resolved 2026-07-27 (arm64 variant `v8`):

| Python | `linux/arm64` digest |
|---|---|
| 3.12 | `sha256:55842c72c6b3584d06ec84c731fc516b30b8a53ad262ebd085e47ab568b3bfc1` |
| 3.11 | `sha256:4fcdc7a15c936b4ffb35dac253215a8e679ea4d25d5e0ffa025fca0d6a702448` |
| 3.10 | `sha256:72b24f9186eb054b6de110a01e2fbb651932d43aa28b5d7e58b1d69364cef39b` |
| 3.9 | `sha256:9a863b2cd2ae52d53feefd3af55ea9e3cf911d5fb252ed77a2618402d2703d74` |
| 3.8 | `sha256:c37419b5a020178521c2e451f44424a2c0bdf3498ff29dd2c9c9d26feffa517b` |

**No amd64 digest was changed** — the 1.0 pins are preserved intact, so nothing already recorded
becomes invalid.

`active_platform` is `"auto"`: `triage.sh` reads the Docker daemon's architecture and selects the
matching digest. On the Mac it will pick `linux/arm64` by itself. Verified on the x86_64 host: it
correctly selected `linux/amd64`, `emulated=no`.

### What you must still do on the Mac

**Re-triage the two real repos.** `click` and `records` were triaged on amd64. Their `lock.txt`
files are amd64 resolutions, and arm64 may resolve different wheels for any compiled dependency.

```bash
cd ~/Project/major/traceweave/triage
./triage.sh https://github.com/pallets/click
./triage.sh https://github.com/kennethreitz/records
```

Then compare — this is genuinely interesting data, not busywork:

```bash
grep -E '^(platform|lock_sha256)=' ~/traceweave-data/out/click/py3.12/result.env
```

Both repos have pure-Python dependency trees, so **`lock_sha256` will probably be unchanged**
(`10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913` for click). If it matches, that
is useful evidence that pure-Python corpora are platform-portable, and worth a sentence in the
paper's reproducibility section. If it differs, you have found a concrete compiled-wheel dependency
and the corpus is platform-locked from here on.

`nope-xyz` is the synthetic bad-URL test; it needs no re-run (it fails at clone, before any container).

### Emulation is now detected, not silent

If you ever force the wrong platform (`TW_PLATFORM=linux/amd64` on the Mac), `triage.sh` prints a
banner and records `emulated=yes`. Emulated runs are correct but **all timings are invalid** — which
matters because tracer overhead is a reported metric. Never publish overhead numbers from one.

### One more difference to expect

`MANIFEST.md` §1.1's `/tmp`-unmountable constraint is **Docker Desktop** behaviour, and Docker
Desktop for Mac has the same restriction — so keeping the data root under `$HOME` remains correct.
But Desktop on Mac also runs a Linux VM, so §1.1's warning about bind-mount I/O inflating absolute
timings applies at least as strongly. Report ratios.

---

## 5. Recommended: put it under git now

The project is **not currently a git repository**, which means all this pinning discipline has no
history behind it. Migration is the natural moment to fix that — and git then becomes the migration
mechanism.

```bash
cd ~/Project/major
git init
git add -A
git commit -m "Phase 0 complete: pins, specs, triage, scorer, SOP v1.1"
```

A `.gitignore` is already provided. The decision worth making deliberately: **bring `out/` into the
repo** so provenance is versioned rather than living in an unversioned home directory.

```bash
# from ~/Project/major
mkdir -p corpus
cp -a ~/traceweave-data/out/. corpus/
git add corpus && git commit -m "corpus provenance: result.env + lock.txt + attempt.log"
```

At ~4 MB for 450 candidates this is comfortably within git's comfort zone, and it means a clone of
the repo is a complete, self-verifying record. If you do this, point triage at it:

```bash
export TW_DATA=~/traceweave-data          # scratch: work/, refrepos/, traces/
# and copy out/ -> corpus/ at the end of each triage batch
```

A cleaner long-term split (separate `TW_OUT` for provenance from `TW_DATA` for scratch) is a small
change to `triage.sh` worth doing in Phase 1, when `runner.py` is written anyway.

---

## 6. Post-migration checklist

- [ ] `./tests/run_checks.sh` → **5 passed, 0 failed**
- [ ] `./tests/run_checks.sh --full` → `HIGH=6 LOW=3 MED=4 TOO_SMALL=1`
- [ ] arm64 image resolves and runs natively:
      `docker run --rm python@sha256:55842c72c6b3584d06ec84c731fc516b30b8a53ad262ebd085e47ab568b3bfc1 python3 -V` → `Python 3.12.x`
- [ ] `docker version --format '{{.Server.Arch}}'` → `arm64`
- [ ] Pre-migration provenance survived: `~/traceweave-data/out/click/py3.12/lock.txt` present, 9 lines
- [ ] Re-triage `click` and `records` on arm64 (§4), then record whether `lock_sha256` changed
- [ ] `platform=linux/arm64` and `emulated=no` in the new `result.env`
- [ ] `./scripts/workload_shell.sh` with no args lists `click`, `nope-xyz`, `records`
- [ ] `GITHUB_TOKEN` exported on the new machine (optional, 60/hr → 5000/hr)
- [ ] `git init && git add -A && git commit` (§5) — the project is still unversioned

Then resume at `MANIFEST.md` §7 — the four items blocking Phase 1.
