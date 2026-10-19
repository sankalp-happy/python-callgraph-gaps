# ins1 v1.1 — proposed amendment (DRAFT, not yet handed to operators)

**Status:** draft for review. Nothing here is in the operators' copy yet.
**Raised:** 2026-08-09, from the returned 14-row spot-check plus a reproduction on this host.
**Touches:** §6 (columns and allowed values) and §9 (when something goes wrong).

The spot-check came back with two states the sheet has no vocabulary for, so the
operator had to guess. Both are now reproduced and understood, and both need a
rule before the 558-row list goes out — otherwise 558 rows get guessed at too.

---

## 1. Why this is needed

### 1.1 `TESTS_RC=137` has no rule

`celery` returned `TESTS_RC=137`. 137 is 128+9 — SIGKILL. On a memory-capped
Docker VM that is the OOM killer: **the suite was killed, not failed.**

§6 offers `status` ∈ {`GREEN` `GREEN_AFTER_FIX` `AMBER` `RED` `UNCLEAR`} and
`error_class` ∈ {`NONE` `PYTHON_VERSION` `DEP_RESOLUTION` `MISSING_SYSTEM_LIB`
`NETWORK` `CLONE` `TIMEBOX` `OTHER`}. None of them describes "killed". An
annotator following §6 to the letter records `AMBER` / `NONE`, which is the same
thing they would record for a repo whose tests genuinely fail — and `AMBER` is
corpus-admissible under amendment 2. A repo whose suite never finished would
enter the corpus indistinguishable from one that ran and reported failures.

### 1.2 A partial collect is recorded as a total failure

Four of the fourteen rows came back `BUILD_OK COLLECT_FAIL` — `black`, `scrapy`,
`django`, `pytest`, 29% of the sample. That rate is not credible as four
independent repo defects, and it is not: it is one harness behaviour.

Reproduced on `psf/black` on this host, 2026-08-09:

```
444 tests collected, 1 error in 0.28s
ERROR tests/test_blackd.py - ModuleNotFoundError: No module named 'aiohttp'
```

`pytest --collect-only` exits non-zero if **any** module fails to import. One
optional-extra test module (`black[d]`, which the harness never installs) made
the exit status non-zero, so v1.1 recorded the whole repo as `COLLECT_FAIL` with
an **empty** `n_collected`, and stopped before running the suite at all.

`black` is in fact a healthy repo: **442 passed, 3 skipped, 1 error in 29.7 s**
once the suite is allowed to run. It is excellent ins2 workload material and it
was being filed as a metadata-less failure.

`triage.sh` v1.2 fixes the harness (see `traceweave/triage/triage_v1.2.patch`).
This amendment fixes the sheet so a human reading a v1.2 RESULT line knows what
to write.

---

## 2. Proposed change to §6

### 2.1 `error_class` — three additions

| Column | Currently | Proposed |
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

| Column | Currently | Proposed |
|---|---|---|
| `n_failing` | a number, or `0`, or `collect_fail`, or `na` | …the same, **plus** `collect_partial` |

- **`collect_fail`** now means strictly **zero** tests collected.
- **`collect_partial`** means some tests collected and some modules failed to
  import. Write the number of failing tests in `n_failing` as normal; put
  `collect_partial` there **only** when the suite could not be run at all.

### 2.3 Cross-field rules — replacing the current four

Current rules, unchanged:

- `status = GREEN` → `error_class` must be `NONE` and `fix_applied` must be `none`.
- `status = AMBER` → `error_class` must be `NONE`.
- `status = RED` → `error_class` must **not** be `NONE`.

Added:

- `error_class ∈ {OOM, TIMEOUT, KILLED}` → `status` must be **`RED`**, and
  `n_failing` must be `na`.
  **A killed run is not an AMBER run.** Its pass counts and its timings are both
  meaningless, and MANIFEST §1.1 forbids publishing timing from an invalid run.

### 2.4 What to write for each v1.2 RESULT line

`triage.sh` v1.2 emits these. Copy the line verbatim into `result_line_seen`
either way — §6 already calls that the most useful column on the sheet, and it is
what lets us tell "you saw different output" from "you read the table
differently".

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

---

## 3. Proposed addition to §9 (when something goes wrong)

> **If the RESULT line says `KILLED`, `OOM` or `TIMEOUT`, do not re-run it hoping
> for a better answer, and do not mark it `UNCLEAR`.** Record it as `RED` with the
> matching `error_class` and move on. These are machine-capacity outcomes, not
> properties of the project, and they are read separately: a repo that was killed
> on a small machine may be perfectly fine on a large one, and we need to know
> which rows to retry rather than which rows to argue about.
>
> Put the machine's memory in `notes` if you know it.

---

## 4. One consequence to note before this ships

§6's `error_class` list is also the vocabulary `triage.sh`'s two automatic
classifiers emit, and their disagreement rate is a reported number. Adding
`OOM` / `TIMEOUT` / `KILLED` changes what the classifiers can say, so the 10%
human-vs-classifier audit must be run **entirely under v1.2** — v1.1 rows and
v1.2 rows are not comparable on these three classes, because under v1.1 the
machine could not emit them at all.

The 14 returned rows are v1.1 rows. They stay v1.1 evidence; they should not be
pooled with the 558.
