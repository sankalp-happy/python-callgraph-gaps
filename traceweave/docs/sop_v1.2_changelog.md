# SOP v1.2 — Three new outcomes, and one that was being filed wrongly

| | |
|---|---|
| **Amends** | `ins1.md` §5 (columns and allowed values) and §8 (when something goes wrong) |
| **Sheet version to write from now on** | **`v1.2`** |
| **Affects** | anyone doing the daily 10% spot-check. ins2 and ins3 are unchanged. |
| **Date** | 2026-08-17 |
| **Supersedes** | the draft at `../../docs/sop/ins1_v1.1_amendment_draft.md`, now shipped |

Everything in `ins1.md` and in `sop_v1.1_changelog.md` still applies. Only what is
below changes, and only for the ins1 triage sheet.

**Nothing already recorded is wasted.** Rows marked `v1.1` stay valid as v1.1
evidence. You start writing `v1.2` today. The two vintages are **not pooled** for
the three new error classes — §4 explains why, and `scripts/validate_sheet.py`
now enforces it per row.

---

## 1. Why this is needed

### 1.1 `TESTS_RC=137` had no rule

`celery` came back `TESTS_RC=137`. 137 is 128+9 — SIGKILL. On a memory-capped
Docker VM that is the OOM killer: **the suite was killed, not failed.**

The old §5 offered `status` ∈ {`GREEN` `GREEN_AFTER_FIX` `AMBER` `RED` `UNCLEAR`}
and `error_class` ∈ {`NONE` `PYTHON_VERSION` `DEP_RESOLUTION`
`MISSING_SYSTEM_LIB` `NETWORK` `CLONE` `TIMEBOX` `OTHER`}. None of them describes
"killed". Following §5 to the letter you would write `AMBER` / `NONE` — the same
thing you would write for a repo whose tests genuinely fail. And `AMBER` is
corpus-admissible, so a repo whose suite never finished would enter the corpus
indistinguishable from one that ran and reported failures.

### 1.2 A partial collect was recorded as a total failure

Four of the fourteen returned spot-check rows came back `BUILD_OK COLLECT_FAIL` —
`black`, `scrapy`, `django`, `pytest`, 29% of the sample. That rate is not
credible as four independent repo defects, and it was not: it was one harness
behaviour.

Reproduced on `psf/black`:

```
444 tests collected, 1 error in 0.28s
ERROR tests/test_blackd.py - ModuleNotFoundError: No module named 'aiohttp'
```

`pytest --collect-only` exits non-zero if **any** module fails to import. One
optional-extra test module (`black[d]`, which the harness never installs) made
the exit status non-zero, so the whole repo was recorded `COLLECT_FAIL` with an
**empty** `n_collected`, and its suite was never run — though it is in fact
**442 passed, 3 skipped, in 29.7 s**. Excellent ins2 workload material, filed as
a metadata-less failure.

`triage.sh` v1.2 fixes the harness. This document fixes the sheet, so a human
reading a v1.2 RESULT line knows what to write.

---

## 2. What changes in §5

### 2.1 `error_class` — three additions

| Column | Was | Now |
|---|---|---|
| `error_class` | `NONE` `PYTHON_VERSION` `DEP_RESOLUTION` `MISSING_SYSTEM_LIB` `NETWORK` `CLONE` `TIMEBOX` `OTHER` | …the same, **plus** `OOM` `TIMEOUT` `KILLED` |

- **`OOM`** — the run was killed for memory. You will see `TESTS_RC=137`, or a
  RESULT line containing `KILLED OOM`.
- **`TIMEOUT`** — the run hit a time limit rather than finishing. `TESTS_RC=124`,
  or a RESULT line containing `KILLED TIMEOUT`.
  *Not the same as `TIMEBOX`*, which means **you** stopped working on the row.
  `TIMEOUT` means the **machine** stopped the run.
- **`KILLED`** — the container died and the log does not say why.

### 2.2 `n_failing` — one addition

| Column | Was | Now |
|---|---|---|
| `n_failing` | a number, or `0`, or `collect_fail`, or `na` | …the same, **plus** `collect_partial` |

- **`collect_fail`** now means strictly **zero** tests collected.
- **`collect_partial`** means some tests collected and some modules failed to
  import. Write the number of failing tests in `n_failing` as normal; put
  `collect_partial` there **only** when the suite could not be run at all.

### 2.3 Cross-field rules

The three existing rules are unchanged:

- `status = GREEN` → `error_class` must be `NONE` and `fix_applied` must be `none`.
- `status = AMBER` → `error_class` must be `NONE`.
- `status = RED` → `error_class` must **not** be `NONE`.

One rule is added:

- `error_class ∈ {OOM, TIMEOUT, KILLED}` → `status` must be **`RED`**, and
  `n_failing` must be `na`.
  **A killed run is not an AMBER run.** Its pass counts and its timings are both
  meaningless, and MANIFEST §1.1 forbids publishing timing from an invalid run.

### 2.4 What to write for each v1.2 RESULT line

Copy the RESULT line verbatim into `result_line_seen` either way — §5 already
calls that the most useful column on the sheet, and it is what lets us tell "you
saw different output" from "you read the table differently".

| RESULT line | `status` | `error_class` | `n_failing` |
|---|---|---|---|
| `BUILD_OK TESTS_OK` | `GREEN` | `NONE` | `0` |
| `BUILD_OK TESTS_OK collect_partial` | `GREEN` | `NONE` | `0` |
| `BUILD_OK TESTS_FAIL failing=N` | `AMBER` | `NONE` | `N` |
| `BUILD_OK TESTS_FAIL failing=N collect_partial` | `AMBER` | `NONE` | `N` |
| `BUILD_OK COLLECT_FAIL` | `AMBER` | `NONE` | `collect_fail` |
| `BUILD_OK TESTS_KILLED OOM` | `RED` | `OOM` | `na` |
| `BUILD_OK TESTS_KILLED TIMEOUT` | `RED` | `TIMEOUT` | `na` |
| `BUILD_OK KILLED <class> docker_rc=N` | `RED` | `KILLED` | `na` |
| `BUILD_FAIL <class>` | `RED` | that class | `na` |

### 2.5 `sheet_version`

Write **`v1.2`**. Every column else is as it was.

---

## 3. What changes in §8 (when something goes wrong)

Add this row to the table:

> **If the RESULT line says `KILLED`, `OOM` or `TIMEOUT`, do not re-run it hoping
> for a better answer, and do not mark it `UNCLEAR`.** Record it as `RED` with the
> matching `error_class` and move on. These are machine-capacity outcomes, not
> properties of the project, and they are read separately: a repo that was killed
> on a small machine may be perfectly fine on a large one, and we need to know
> which rows to retry rather than which rows to argue about.
>
> Put the machine's memory in `notes` if you know it.

This does not change the three reasons to stop and message the coordinator
immediately. An `OOM` is not one of them.

---

## 4. The consequence, and why the two vintages stay apart

§5's `error_class` list is also the vocabulary `triage.sh`'s two automatic
classifiers emit, and their disagreement rate is a **reported number**. Adding
`OOM` / `TIMEOUT` / `KILLED` changes what the classifiers can say, so:

> **The 10% human-vs-classifier audit must be run entirely under v1.2.** v1.1 rows
> and v1.2 rows are not comparable on these three classes, because under v1.1 the
> machine could not emit them at all.

The 14 returned rows are v1.1 rows. They stay v1.1 evidence and they are **not**
pooled with the 558.

`scripts/validate_sheet.py` enforces this per row, from the row's own
`sheet_version` column rather than from a command-line flag: a `v1.1` row
carrying `OOM` is reported as a vintage mismatch, and a `v1.2` row carrying `OOM`
with `status=AMBER` is reported as a §2.3 violation. Run it before a sheet comes
back, not after:

```bash
python3 scripts/validate_sheet.py ins1 handoff/ins1_triage_558.csv --filled-only
```

---

## 5. Summary

| # | Change | Action |
|---|---|---|
| B1 | `error_class` gains `OOM` `TIMEOUT` `KILLED` | use them; they always mean `status=RED`, `n_failing=na` |
| B2 | `n_failing` gains `collect_partial` | only when the suite could not run at all |
| B3 | `TIMEOUT` ≠ `TIMEBOX` | machine stopped it vs. you stopped it |
| B4 | Killed runs are never `AMBER` | §2.3 |
| B5 | Write `sheet_version = v1.2` | — |
| B6 | The 10% audit restarts under v1.2 | v1.1 rows are kept, not pooled |
