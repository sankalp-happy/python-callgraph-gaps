# Superseded operator sheets (v1.0)

**Do not hand these to anyone.** The current sheets are one level up, at `v1.1`.

They are kept, not deleted, for three reasons:

1. Rows already recorded under `v1.0` **stay valid** — `ins3_v1.1.md` and `ins1_v1.1_spotcheck.md`
   both say so explicitly. Reading an old row means reading the vocabulary it was written against.
2. `traceweave/triage/triage.sh` carries the **ins1 v1.0 classifier verbatim** (as
   `error_class_v10`) so the human-vs-classifier disagreement rate is comparable across versions.
   That code is only auditable against this text.
3. `traceweave/docs/sop_v1.1_changelog.md` and `sop_v1.2_changelog.md` are written as diffs *against*
   these documents and cite their section numbers.

| File | Superseded by |
|---|---|
| `ins1.md` | `../ins1_v1.1_spotcheck.md` — triage is automated; what remains is checking the script |
| `ins2.md` | `../ins2_v1.1_prework.md` — Part A only; the container half is still pending |
| `ins3.md` | `../ins3_v1.1.md` — Part 1 automated by `github_meta.py`, Part 2 dropped |
