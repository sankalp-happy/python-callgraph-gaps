# Handoff — the 558 queued repos, split per operator

Generated 2026-08-09 by `traceweave/scripts/make_operator_sheets.py` from
`candidates/03_queue.csv`. Regenerating is idempotent; nothing here is hand-edited.

ins1 §1, ins2 §1 and ins3 §1 all say the same thing — *"A longer list (400–600
projects) is being generated and will be added to your sheet later. Work the 14
first."* This is that list.

| File | For | Rows | What is pre-filled |
|---|---|---|---|
| `ins1_triage_558.csv` | triage operator | 558 | `row_id`, `repo_url`, `sha`, `sheet_version` |
| `ins2_targets_558.csv` | ins2 (prework) | 558 | target list + `stratum`, `stars`, build/test flags |
| `ins3_main_558.csv` | ins3 (main tab) | 558 | `licence`, `stars`, `last_commit_date`, `port_exists=NA_V11` |
| `ins3_part1R_licence_review_91.csv` | ins3 (Part 1-R) | **91** | script's licence guess + the SPDX string it saw |

Column sets are lifted from ins1 §6, ins2 §4 and ins3 §6 — not invented here.

---

## Queue order is load-bearing. Do not sort these files.

`queue_position` is not arbitrary and it is not by stars. Amendment 3 interleaves
the three strata in MANIFEST §4's target ratio (LOW 15 : MED 20 : HIGH 25), so
**any prefix of the queue carries all three strata**. That is what makes a partial
run interpretable: stopping at row 139 still yields 58 HIGH / 46 MED / 35 LOW
rather than 139 rows of whatever the pool happened to have most of.

Sorting by name, stars or stratum destroys that property silently.

---

## Two things that differ from what the instructions predict

**1. Part 1-R is 16.3%, not "about 1 project in 10".**
ins3 §4 predicts roughly one project in ten will need a human to read the licence
file. The real figure is **91 of 558 = 16.3%** (60 `OTHER` + 31 `NONE_FOUND`).
At §4's own estimate of 30 seconds per row that is **~46 minutes**, not ~28.
Nothing is wrong — the prediction was just made before the pool existed.

**2. 22 of the 558 repos are archived, and that is deliberate.**
Per ins3 §9 they are processed normally. `scripts/github_meta.py` tags them rather
than dropping them, because a repo being archived says nothing about whether its
call graph is interesting.

---

## Licence spread across all 558

Advisory only — **nothing in the pipeline currently gates on
`redistribution_class`.** `github_meta.py`'s `REDISTRIBUTION` map exists to make
the release decision deliberate rather than accidental (ins3 §4), not to filter
the corpus.

| class | n |
|---|---|
| `PERMISSIVE` | 399 |
| `REVIEW_NEEDED` | 91 |
| `COPYLEFT` | 55 |
| `WEAK_COPYLEFT` | 13 |

**Worth knowing before it becomes a surprise:** HIGH is the *least* permissive
stratum (64% permissive, against 75% and 73% for LOW and MED). If the release
later restricts to permissive **and** non-archived, only **82 usable HIGH** remain
— so MANIFEST §4's HIGH floor of 15 needs 18.3% survival through triage and ins2,
and the 1.5× over-recruitment target needs 27.4%. Those are materially harder
numbers than the same floors against all 135 HIGH. This is a decision waiting to
be made, not a defect.

---

## Before the triage sheet goes out — two open items

**1. The returned 14-row spot-check needs two rows re-run.**
Row 3 triaged `ClickHouse/ClickHouse` — a multi-GB C++ project — instead of
`pallets/click`, which is both ins1 §3's qualification repo and a member of the
frozen 14-repo density-scorer calibration set. The `RED`/`CLONE` result on that
row is an artefact of the substitution, not a finding. Row 10's `repo_url` is a
GitHub *search URL* rather than `django/django`.

`click` has since been triaged on this host: `BUILD_OK TESTS_OK`, 1965 tests
collected, `lock_sha256=10dc90ae…` — which reproduces the committed
`corpus.amd64-baseline` record byte for byte across architectures.

**2. `triage.sh` v1.2 and the ins1 §6 amendment ship together or not at all.**
See `traceweave/triage/triage.sh` (now at v1.2), `traceweave/docs/sop_v1.2_changelog.md`
and `docs/sop/ins1_v1.1_amendment_draft.md`.
v1.1 records a repo with one unimportable optional-extra test module as
`COLLECT_FAIL` with an empty `n_collected` and never runs its suite; `psf/black`
is 442-passing and was being filed that way. Sending the 558 out under v1.1 would
reproduce that across the whole corpus.

`03_qc_sample.csv` is also missing `result_line_seen`, which ins1 §6 calls *"new
in v1.1 and the most useful column on the sheet"* — it is the column that decides
whether a human/classifier disagreement was different output or a differently-read
table, which is the QC sample's entire purpose. Fixed in
`discover_candidates.py`; run `make_operator_sheets.py --qc-fix` to add it to the
existing file without re-drawing the seeded sample.
