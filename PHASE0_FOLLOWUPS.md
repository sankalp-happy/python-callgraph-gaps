# Phase 0 follow-ups — proposed edits to the frozen documents

**Written:** 2026-08-09. **Not applied.** Every change below touches a document
that is deliberately hard to change, so each is written out as a paste-ready diff
with the evidence that motivates it.

`MANIFEST.md` says of itself: *"It is written on day one and only ever appended
to. If a pin changes, bump `manifest_version`, add a dated row, and keep the old
row."* Filling in a pin that was left blank is still a pin change, so §2, §6 and
§7 move together or not at all.

---

## 1. §2 — pin Pyright at `1.1.411`

MANIFEST §7 item 1 and §2's Pyright row (*"Version query pending; pin before
Phase 1 §1.2 starts"*).

**Version:** `1.1.411`, published **2026-06-25**, latest of 495 releases.
Read straight from the npm registry:

```bash
curl -s https://registry.npmjs.org/pyright | python3 -c "import sys,json;print(json.load(sys.stdin)['dist-tags']['latest'])"
```

> **On the broken host npm.** `npm` on this Mac is unusable — node 25.8.2 wants
> `libllhttp.9.3.dylib` and Homebrew has only `9.4.3`. That turned out **not** to
> block this pin, and the earlier claim that it did was wrong. MANIFEST §1 is
> explicit that the host never traces and every tool runs containerised, so
> Pyright is installed by `npm` *inside* an image, not on the host. The registry
> is queryable over plain HTTPS. Repairing host npm (`brew reinstall node`) is
> worth doing, but it is not on the critical path for anything.

### Diff

```diff
-| **Pyright** | *to pin* (npm `pyright`) | Type info for attribute-call resolution in **static baseline 2**. | Version query pending; pin before Phase 1 §1.2 starts. |
+| **Pyright** | `1.1.411` (npm `pyright`, published 2026-06-25) | Type info for attribute-call resolution in **static baseline 2**. | Installed inside the image, never on the host. Pin the exact version in the image build; `npm i -g pyright` without a version resolves to whatever is current that day. |
```

---

## 2. §2 — record that the PyCG `0.0.8` pin needs a shim

This one is not a version change. The pin stays at `0.0.8`. What changes is that
**`0.0.8` as published on PyPI cannot be imported on Linux at all**, which is a
material fact about the project's static baseline 1 and belongs next to the pin.

### Evidence

Verified in `python@sha256:72b24f91…` (3.10.20, `linux/arm64`), 2026-08-09. The
sdist installs its package directory as `PyCG/` while every internal import reads
`from pycg import …`. On a case-insensitive filesystem (macOS) that works by
accident. On Linux — every container in this project — all four routes fail:

| Invocation | Result |
|---|---|
| `import pycg` | `ModuleNotFoundError: No module named 'pycg'` |
| `import PyCG.pycg` | `ModuleNotFoundError` — raised by *its own* internal import |
| `python -m PyCG` | `ModuleNotFoundError` (`__main__.py` line 4) |
| `pycg --help` | `command not found` — 0.0.8 ships no console script |

Workarounds tested:

| Approach | Result |
|---|---|
| `ln -sfn $SP/PyCG $SP/pycg` in site-packages | ✅ imports, and `python -m pycg --help` works |
| PyPI `0.0.7` | ✅ packages correctly as lowercase `pycg/` — the fault is specific to the 0.0.8 release |
| `pip install git+https://github.com/vitsalis/PyCG@v0.0.8` | ❌ fails |

**Recommendation: keep `0.0.8` and carry the symlink.** §2's reason for pinning
PyCG at all is that *"reporting against it makes H2a a claim about the state of
the art"* — that argument wants the latest published release, not the last one
that happened to package correctly. But the deviation has to be written down,
because a reviewer reproducing our baseline will otherwise conclude the pin is
simply wrong.

### 2.1 The bigger constraint: PyCG 0.0.8 does not run on Python 3.12 at all

MANIFEST §1 makes **3.12 the default** — *"All triage starts here."* Static
baseline 1 cannot run there. Verified twice, once across the whole reference set
and once in isolation on a five-line module:

```python
def a():
    return 1

def b():
    return a()
```

| interpreter | result on that file |
|---|---|
| `python@sha256:72b24f91…` (3.10.20) | **OK, 3 nodes** |
| `python@sha256:55842c72…` (3.12.13) | **`ImportManagerError: Can't add edge to a non existing node`** |

Across the reference set the pattern is total, not marginal:

| interpreter | files analysed | failed | rate |
|---|---|---|---|
| **3.10** | 1311 | 32 | **2.4%** |
| **3.12** | 1311 | 1311 | **100.0%** |

Every 3.12 failure is the same `ImportManagerError`. Note it is *not* a
`SyntaxError` — the failure is in PyCG's import-resolution machinery under 3.12's
`ast`, not in parsing. §2 anticipated the parse risk; this is a different and
larger one.

**Consequence for the design, and it needs recording somewhere:** a repo's
triaged `pyver` and the interpreter PyCG runs under are now **independent**. A
repo triaged on 3.12 must still have its static baseline extracted on ≤3.11.
That is defensible — PyCG reads source, it does not execute the repo — but it
must be deliberate, because it means the static and runtime sides of an H2a
comparison run under different interpreters, and nobody should discover that from
a stack trace in Phase 1.

### 2.2 Measured answer to §7 item 2

`python3 scripts/pycg_parse_rate.py measure --pyver 3.10 --max-files 120`,
14 reference repos at recorded shas, 1311 files, seeded sample (seed 20260727),
7342 files skipped by the 120-file cap and recorded as skipped.

| slice | failed / analysed | rate |
|---|---|---|
| all files | 32 / 1311 | **2.4%** |
| library code only | 9 / 558 | **1.6%** |
| test & fixture paths | 23 / 753 | **3.1%** |

By outcome: 17 `SyntaxError`, 8 timeout (>20 s on one file), 7 other exceptions.

**Report the slices, not just the 2.4%.** The failure rate is concentrated in
deliberately-exotic files: `black` alone accounts for 11 of 32, and its failures
are its own syntax-edge-case corpus — `tests/data/cases/pep_654.py`,
`type_params.py`, `type_param_defaults.py`. Those are *valid modern Python* that a
3.10 interpreter cannot parse, so they measure the interpreter's age rather than
PyCG's quality. That distinction is the whole reason the script keeps results per
interpreter and refuses to pool them.

The honest headline for the feasibility survey is two numbers, not one:
**PyCG 0.0.8 fails on 1.6% of library files under 3.10, and on 100% of all files
under 3.12.** Tracebacks for every failure are in
`$TW_DATA/pycg/py<ver>/pycg_failures.jsonl`, as §2 requires.

### Diff

```diff
-| **PyCG** | `0.0.8` | **Static baseline 1** — … | ⚠️ Latest release is `0.0.8` and it is years old. It parses with the *host* `ast`, so modern syntax (`match`, newer generics, PEP 695 type params) may crash it. **Do not treat a PyCG crash as a bug to hide** — the rate at which the field's standard baseline cannot parse contemporary Python is a reportable result. Log every failure with its traceback into the feasibility survey. |
+| **PyCG** | `0.0.8` (+ `pycg`→`PyCG` symlink shim, see below) | **Static baseline 1** — … | ⚠️ Latest release is `0.0.8` and it is years old. It parses with the *host* `ast`, so modern syntax (`match`, newer generics, PEP 695 type params) may crash it. **Do not treat a PyCG crash as a bug to hide** — the rate at which the field's standard baseline cannot parse contemporary Python is a reportable result. Log every failure with its traceback into the feasibility survey. ⚠️ **The 0.0.8 sdist is unimportable on Linux**: it ships `PyCG/` but imports `pycg`. Every image using it MUST create the symlink (`scripts/pycg_parse_rate.py` does). 0.0.7 packages correctly; 0.0.8 does not. |
```

---

## 3. §7 — outstanding-before-Phase-1 checklist

```diff
 ## 7. Outstanding before Phase 1

-- [ ] Pin the **Pyright** version (npm query returned only notices; retry). Needed before static baseline 2.
-- [ ] Install **PyCG 0.0.8** in a dedicated container and measure its parse-failure rate on the reference set — expected to be non-trivial and itself reportable.
-- [ ] `triage/runner.py` — parallel queue over the recipe ladder in `config/base_images.json`.
-- [ ] `scripts/discover_candidates.py` — candidate discovery to ~450 repos.
+- [x] Pin the **Pyright** version — `1.1.411` (2026-06-25). See §2.
+- [x] Install **PyCG 0.0.8** in a dedicated container and measure its parse-failure rate on the reference set. `scripts/pycg_parse_rate.py`; see §2 on the packaging shim without which it cannot be imported at all.
+- [x] `triage/runner.py` — parallel queue over the recipe ladder in `config/base_images.json`. Ladder, checkpointing, independent re-verification of every outcome, and corpus-admission accounting.
+- [x] `scripts/discover_candidates.py` — candidate discovery to ~450 repos. Delivered 558 queued (HIGH 135 / MED 177 / LOW 246).
```

---

## 4. §6 — change-log row

```diff
 | **1.1** | 2026-07-27 | **Added `linux/arm64` digests for all 5 images** … |
+| **1.2** | 2026-08-09 | Pinned **Pyright 1.1.411**. Recorded that the **PyCG 0.0.8** PyPI sdist is unimportable on Linux and requires a `pycg`→`PyCG` symlink; pin unchanged. No image digest changed. |
```

---

## 5. `MIGRATION.md` §4 — the Apple Silicon claim is now false

§4 currently reads *"Target machine is an Apple Silicon Mac (arm64). The work is
done; no hand-editing required."* The arm64 digests are indeed in place and that
part stands. The **claim that the Mac is the target machine** does not.

Measured, this host vs the machine discovery actually ran on:

| | this Mac | discovery host (MANIFEST §1) |
|---|---|---|
| arch | arm64 | x86_64 |
| cores | 8 | 16 |
| RAM | 8 GB (Docker VM 3.83 GB) | 38 GB |
| free disk | 18 GB (93% full) | 345 GB |

The 558-repo triage is roughly 100 worker-hours of containers each running a full
test suite. `TESTS_RC=137` — the OOM kill — is already observable on this host at
`--jobs 3`. And MANIFEST is explicit that a corpus must be built on **one**
architecture, because compiled-extension repos resolve different wheels and
therefore a different `lock_sha256`, which is part of repo identity.

**This is a decision, not a defect, and it is yours to make.** §4 should record
whichever way it goes. Suggested wording if the corpus is built on the Linux box:

```diff
-## 4. Platform: Apple Silicon — already handled ✅
-**Target machine is an Apple Silicon Mac (arm64). The work is done; no hand-editing required.**
+## 4. Platform: both architectures pinned; corpus host is the x86_64 box
+**arm64 digests are in place for all five images and `active_platform: auto` resolves them,
+so either machine can run a single repo.** The 558-repo corpus is built on the x86_64 host
+(16 cores / 38 GB / 345 GB), because a corpus must be built on ONE architecture and this
+Mac (8 cores / 8 GB / 18 GB free) OOM-kills large suites at --jobs 3. The Mac stays useful
+for single-repo work, the reference set, and development.
```

---

## 6. Not a document change, but it ships with these

`traceweave/triage/triage_v1.2.patch` — two verified defects in the triage atom.
Applying it changes the classification vocabulary the operators' sheet is
validated against, so it lands together with
`ins1_v1.1_amendment_draft.md` §2, or neither lands.

Both are reproduced from scratch on this host; see the patch header and the
amendment draft §1 for the evidence.
