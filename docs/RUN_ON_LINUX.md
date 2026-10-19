# Run this on the x86_64 Linux box

Two long jobs, in this order. The second consumes the first's output.

**Both save their progress continuously.** If the machine reboots, the SSH session
drops, or you press Ctrl-C, run the same command again — it picks up where it
stopped and never redoes finished work.

**Run both on the same machine.** `MANIFEST.md` §1: one corpus, one architecture.
Package versions can resolve differently on a different machine, and the version
list is part of each repo's identity. Do not do half here and half on the Mac.

---

## 0. Prerequisites (once)

```bash
docker info          # must succeed
python3 --version    # 3.8+ is enough for the runner; 3.10+ preferred
git --version
```

If the Docker daemon looks missing on Docker Desktop for Linux, it ships as a
*disabled user unit*, not a broken install:

```bash
systemctl --user start docker-desktop
```

Unpack next to wherever you keep the project:

```bash
tar xzf traceweave-phase1-linux.tar.gz
cd major          # traceweave/ and candidates/ are inside
```

You need **~30 GB free** for clones and images while triage runs (it deletes each
working copy as soon as that repo's result is safely written).

---

## 1. Triage — about 4–5 hours

Decides which candidate repos actually install and run.

```bash
cd traceweave/triage
nohup python3 runner.py run \
    --queue ../../candidates/03_queue.csv \
    --jobs 8 --limit 200 > ~/triage_run.log 2>&1 &

tail -f ~/triage_run.log
```

**Why 200 and not 558.** The queue is deliberately over-recruited and shuffled by
category, so stopping early keeps the categories balanced. 200 gives 83 HIGH /
67 MED / 50 LOW, which clears every floor even if only a third survive. The
other 358 stay in reserve.

**Why 8 jobs.** The box has 16 cores and 38 GB. Do not push this much higher: if
containers get killed for memory, those repos are recorded as failures
(`error_class=OOM`) and a healthy repo gets wrongly excluded. They can be re-run,
but it wastes time.

### When it finishes

```bash
python3 runner.py report
```

Read three things:

- **the per-stratum table** against the MANIFEST §4 floors (LOW 10 / MED 12 /
  HIGH 15). If a floor is short, raise `--limit` and re-run — it continues.
- **`OOM` rows.** A handful is normal. Many means `--jobs 8` was too many for
  this machine; drop to 6 and re-run just those.
- **the redistribution line.** `pending` repos are waiting on the licence review,
  not rejected. They are still extracted in step 2.

---

## 2. Static extraction — about 1–6 hours

Builds the call graph each static tool *predicts*, for both baselines.

```bash
cd ../static
./build_image.sh                 # once per machine, a few minutes

nohup ./run_corpus.sh > ~/static_run.log 2>&1 &
tail -f ~/static_run.log
```

`run_corpus.sh` checks everything before it commits hours: docker reachable,
architecture is x86_64, the image contains the right pycg / pyright / node, and
45 correctness guards pass. It refuses to start otherwise.

### When it finishes

```bash
python3 extract.py report
```

- Rows marked **`PARTIAL`** had one baseline fail — usually PyCG running out of
  memory. Re-running the script retries exactly those.
- **`no_python_package_found`** means the layout guess failed. Tell me the repo
  name; it is a two-line fix.
- **`jacc`** is how much the two baselines agree. Expect roughly 0.5–0.8. That
  disagreement is a finding, not a bug.

---

## 3. Send the results back

Everything the analysis needs lives in one directory:

```bash
tar czf ~/phase1-results.tar.gz -C ~/traceweave-data triage/ledger.jsonl static
```

That is a few MB of JSON. The repo clones and Docker images stay on the box.

---

## What is NOT in these two jobs

Three things need a person, and none of them is blocked on the machine:

1. **ins2 workload capture** — annotators recording ≥3 replayable ways to run
   each green repo. This is the real bottleneck for the whole result.
2. **The 10% spot-check, re-run under SOP v1.2** — `docs/sop_v1.2_changelog.md`.
   The old rows are kept but cannot be pooled with the new ones.
3. **The ins3 Part 1-R licence review** — 567 repos whose licence the script
   could not read, mostly a missing file rather than a restrictive licence.
   Resolving them before the corpus freezes keeps far more HIGH repos.

---

## 4. DyPyBench week-1 gate — about 6–10 hours

Added 2026-08-24, after `docs/plan/plan_pivot_nov2026.md` replaced the recruited
corpus with DyPyBench's 50 projects. Sections 1 and 2 above are complete and
their results are in `phase1-results.tar.gz`; this is the next unattended job.

**The question.** `demo/tracer.py` reads `frame.f_code.co_qualname`, which needs
Python 3.11. DyPyBench builds `FROM ubuntu:latest` and installs the distro
`python3`, which is 3.10. Either the corpus runs on 3.11 or the tracer needs a
qualname backfill, and every week after this one depends on the answer.

```bash
cd traceweave/dypybench
for v in 3.10 3.11 3.12; do
    docker build --build-arg PYVER=$v -t tw-dypybench:$v .
done
```

Three images, roughly 15 minutes. Then the probe itself:

```bash
nohup python3 probe.py run --jobs 4 > ~/dypybench_probe.log 2>&1 &
tail -f ~/dypybench_probe.log
```

**Why 3.10 is in the list.** It is the control arm, not a third data point. A
fresh install in 2026 does not reproduce DyPyBench's 2023 environments: several
projects have unpinned dev requirements that now resolve three years forward.
`dbader/schedule` asks for a bare `pytest` alongside a 2023-era `pytest-flake8`,
and today that combination fails on every Python version alike. Without the
control, that failure reads as "does not work on 3.11" and the gate is wrong.

**Read the answer:**

```bash
python3 probe.py report --verbose
```

`report` prints, per version, how many projects are usable, how many broke
*because of* the version (they pass on 3.10), and how many broke anyway. Only the
first two numbers bear on the gate. The rule is pre-committed by the plan: 25 or
more usable on 3.11 means run that subset unchanged; fewer means write the 3.10
qualname backfill.

**Then trace one project end to end**, which is week 1's other deliverable:

```bash
python3 probe.py trace --project 10 --pyver 3.11     # project 10 is pallets/click
```

click is the right first choice because `tests/fixtures/` already holds golden
files for it, so a wrong answer is visible immediately rather than plausible.
The trace lands in `~/dypybench-data/trace-project10-3.11.json`.

**Resumable and non-destructive**, like the other two jobs. Every verdict is
appended to `~/dypybench-data/probe.jsonl` as it completes, re-running skips
finished pairs, and nothing ever touches an installed `/Project` tree. Budget
roughly 60 GB of disk: 150 container runs each clone a repo and build a wheel.

Send back the same way as section 3:

```bash
tar czf ~/dypybench-probe.tar.gz -C ~/dypybench-data probe.jsonl trace.jsonl \
    trace-project10-3.11.json
```

---

## 5. Study 1 at corpus scale — about 4–8 hours

Added 2026-10-17. Takes the harness's Study 1 (call resolution: PyCG, Pyright,
LLMs, learned combiner) from click and toolz to the 20 repos in
`traceweave/study1/repos.tsv` (8 HIGH / 7 MED / 5 LOW, why each was picked is
at the top of that file). It needs sections 1 and 2 done on this box: it reads
triage's `~/traceweave-data/out/<repo>/py3.12/lock.txt` and the static output in
`~/traceweave-data/static/`.

Copy the harness over from the Mac once, without its `work/` checkouts:

```bash
rsync -a --exclude work/ <mac>:Projects/traceweave-harness/ ~/traceweave-harness/
```

Then:

```bash
cd traceweave/study1
nohup python3 batch.py run > ~/study1_run.log 2>&1 &
tail -f ~/study1_run.log
```

Per repo it clones the pinned sha, rebuilds triage's environment from the lock
(in the same pinned `python:3.12` image), traces the repo's own test suite,
builds the bundle, and runs `tw.py truth` and `tw.py bench`. Each step is
skipped once its output exists, so Ctrl-C and re-running resumes.

**A failed repo is not retried on the next run.** It is written to
`~/traceweave-data/study1/ledger.jsonl` and skipped from then on, because the
same failure usually happens again. Read its log, fix the cause, then name it:

```bash
python3 batch.py status                       # done / failed at which step / pending
less ~/traceweave-data/study1/logs/<repo>.log
python3 batch.py run --retry <repo>
```

Expect a few failures at `truth`: it refuses a repo whose suite gives a
different result under the tracer (flaky tests), and that is a correct
exclusion, not something to force. Budget ~15 GB of disk for the 20 venvs.

### Send back

```bash
tar czf ~/study1-results.tar.gz -C ~ traceweave-harness/bundles \
    traceweave-harness/results/resolve traceweave-data/study1/ledger.jsonl \
    traceweave-data/study1/bench traceweave-data/study1/logs
```

### Not in this job: the LLM runs

`tw.py bench` freezes each repo's LLM sample (`results/resolve/<repo>.sample.json`)
at **25 functions per repo** (`SAMPLE_DEFAULT` in the harness's `resolve.py`;
change it before this job, not after). One `tw.py resolve` call is one function.
Groq's free tier allows about 200K tokens a day per model, and each model has
its own cap, so the three models run side by side:

| tokens per call | per model, 20 × 25 calls | days at 200K/day |
|---|---|---|
| 2.1K (planning figure) | 1.05M | 5.3 |
| 1.0–1.1K (measured mean on click, all three models) | 0.5–0.55M | 2.5–2.8 |

So the whole sample fits in a week even at the planning figure, with about
1.5 days spare for parse retries. `resolve` stops by itself when a model's daily
cap runs out and resumes where it stopped, so run this once a day until every
repo is complete (needs `GROQ_API_KEY` in `~/traceweave-harness/.env`):

```bash
cd ~/traceweave-harness
for m in groq:openai/gpt-oss-20b groq:openai/gpt-oss-120b groq:qwen/qwen3.8-27b; do
  ( for r in $(cut -f1 <core>/traceweave/study1/repos.tsv | grep -v -e '^#' -e '^repo$'); do
      python3 tw.py resolve "$r" --model "$m" || break
    done ) > ~/resolve_${m//\//_}.log 2>&1 &
done
```
