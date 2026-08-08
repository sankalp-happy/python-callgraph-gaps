# SOP v1.1 — What Changes, and What You Do Now

| | |
|---|---|
| **Replaces** | `ins1.md`, `ins2.md`, `ins3.md` sheet version `v1.0` |
| **Sheet version to write from now on** | **`v1.1`** |
| **Date** | 2026-07-27 |

Read section 1, then read only the section with your name's task in it.

**Nothing you have already recorded is wasted.** Rows marked `v1.0` stay valid. You just start
writing `v1.1` from today, and a few columns change.

---

## 1. The one big change: who does what

We found that **ins1 (build triage) was already a script.** Run `triage.sh`, read the RESULT
line, look it up in a fixed table, apply a fixed recipe — every step of that is something a
computer does without a 12-minute timer and without two people ever disagreeing. So it is now
automated and runs unattended, in parallel, overnight.

**ins2 (recording how each project runs) is the opposite.** Reading a README, deciding whether a
grey box is a runnable command or just an install line, finding the demo script nobody linked —
no script does that. It is also the thing the research actually needs most.

So:

| If you were doing | You now do |
|---|---|
| **ins1** (build triage) | **ins2** (recording workloads). See §3. |
| **ins2** (workloads) | **ins2** — same job, three small changes. See §3. |
| **ins3** (background checks) | **ins3 Part 3 only** (config settings). Parts 1 and 2 are gone. See §4. |

Everyone will also be asked for a **daily 10% spot-check** — §5. It takes about 20 minutes and it
is the one thing the script cannot do for itself.

---

## 2. Why the changes (short version)

Two problems would have cost us the whole dataset if we had found them in six weeks instead of now:

1. **Nothing was pinned.** `python:3.12-slim` is a label that points at a different thing every
   few weeks, and installing from the internet gives different package versions every day. So a
   project that worked on Monday could quietly stop matching itself on Friday — and every
   "I ran it twice and got the same answer" would silently stop being true. **Fixed:** the script
   now records the exact image fingerprint and the exact list of package versions for every project.
2. **We were throwing away projects we needed.** ins2 only accepted projects whose tests *passed*
   (`GREEN`). But we need projects that **run**, not projects that pass. A failing test still
   executes the code, which is exactly what we watch. **Fixed:** `AMBER` projects now count.

---

## 3. If you are doing ins2 (workloads) — three changes

Everything in `ins2.md` still applies. Only these change.

### 3.1 Your input list is bigger

Your input list was the `GREEN` and `GREEN_AFTER_FIX` rows. **It is now `GREEN`,
`GREEN_AFTER_FIX`, *and* `AMBER`.**

An `AMBER` project is one that installed fine but some tests fail. That is completely fine for us.
When you run its test suite and see `12 failed, 340 passed`, that is a **keeper** — exactly as
`ins2.md` §4 already said about exit code `1`. Record the real exit code and move on.

### 3.2 Use one command to open the container

**Do not** type the install block from `ins2.md` Step 3 any more. Instead:

```bash
cd ~/traceweave/scripts
./workload_shell.sh <project-name>
```

That is the whole thing. It works out which Python version the project was certified on, opens the
exact same container, and installs the exact same package versions triage used.

Why this matters: if you install your own versions, then triage, your workload recording, and the
later tracing all run *different* software, and none of the three can be compared. This one
command is what keeps them identical.

It prints a small block at the top like this:

```
 pyver:              3.12
 base_image_digest:  sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
 lock_sha256:        10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
```

**Copy those three values into every workload file you write.** They are three new fields (§3.3).

If it says `no GREEN or AMBER triage attempt found`, skip the project and tell the coordinator —
it means triage has not reached it yet.

### 3.3 Three new fields in the workload file, and one changed

The template gains three lines and changes one. **Never delete a line; write `none` if it does not apply.**

```yaml
repo:
repo_url:
workload_id:
kind:
command:
working_dir:
env_vars:
inputs:
exit_code:
duration_s:                  # CHANGED: exact whole seconds now, do NOT round to 5
second_run_exit_code:
same_both_times:
pyver:                       # NEW: copy from the block workload_shell.sh prints
base_image_digest:           # NEW: copy from the block (starts with sha256:)
lock_sha256:                 # NEW: copy from the block
recorded_by:
date:
sheet_version:   v1.1
notes:
```

**On `duration_s`:** v1.0 said round to the nearest 5 seconds. We now need exact whole seconds,
because this number becomes the baseline we measure tracing slowdown against, and rounding a
3-second command to 5 makes that measurement meaningless. Easiest way — put `time` in front:

```bash
time pytest
```

then read the `real` line and write the whole number of seconds.

### 3.4 Unchanged

Your targets (3 projects/day), the 3-workload minimum, the `test_suite` requirement, the
45-minute limit, the `PARTIAL` blockers, and every hard rule in `ins2.md` §8. All still exactly as
written.

---

## 4. If you were doing ins3 (background checks)

### Part 1 (licence, stars, last commit) — **stop doing this by hand**

These three facts are published by GitHub in a form a script can read exactly, so a script now
reads them. Checked against `ins3.md` §2's own qualification answers: requests → `Apache`,
click → `BSD`, django → `BSD`. All three match.

**But the script cannot do all of it.** For roughly 1 project in 10, GitHub cannot identify the
licence and the script writes `OTHER` or `NONE_FOUND`. Those need a human — for example `celery`
comes back `OTHER` when it is really BSD, because its licence file has an unusual preamble.

**Your new Part 1 job:** you get a short list of only the `OTHER` and `NONE_FOUND` rows. Open the
`LICENSE` file, read the first five lines, apply `ins3.md` §3's table, correct the value. About 30
seconds each.

### Part 2 (searching for a translated copy) — **deleted entirely**

Stop. Do not do this any more, and do not finish rows in progress.

Part 2 asked you to search for "a version of this project rewritten in Python". That question was
left over from an earlier plan where the projects were **Java** and were going to be translated
into Python. Our projects **are already Python**, so searching for a Python version of a Python
project is not a meaningful question, and the answer cannot affect anything.

This was ~6 minutes per project on the largest project list. It is genuinely just deleted.

The `port_exists` column still exists in the sheet so nothing breaks; the script fills it with
`NA_V11`. Leave it alone.

### Part 3 (config settings) — **this is now your main job, and you can start immediately**

`ins3.md` §5 said "do not start Part 3 until told." **You are told: start now.**

Everything in `ins3.md` §5 applies unchanged — same locations to check, same
`CAPITAL_LETTERS_WITH_UNDERSCORES` rule, same 8-minute limit, same "one row saying `NONE_FOUND`
if you found none".

Worth knowing why it matters, because it changed from a nice-to-have to a real result: we are
separately recording every setting each project *actually reads while running*. Your list is what
the documentation *says*. The gap between those two is a finding in the paper — undocumented
settings are invisible to anyone modernising the code. So a project where you find nothing is not
a wasted 8 minutes; it is a data point.

---

## 5. New for everyone: the daily 10% spot-check

`ins1.md` §10 and `ins3.md` §11 said about 1 project in 10 was secretly double-checked by another
person, and your answers should agree.

That still happens, but it is now **you versus the script**, not you versus a colleague.

Each morning you get 3–5 projects the script has already triaged, **without being told its
answer.** Run them by hand exactly as `ins1.md` §3 describes and record your `status` and
`error_class`. Then the coordinator compares.

**Please do not try to guess or match what you think the script said.** Where you disagree with
it, that disagreement is the point — it is the only evidence we have that the automated triage is
trustworthy, and it goes in the paper as a measured number. A disagreement you found is worth more
than an agreement you produced.

Takes about 20 minutes. Do it before your ins2 work, not after.

---

## 6. What has NOT changed

- Every hard rule in all three documents. Especially: **never edit a project's code**, **never
  record a command you did not actually run**, **never leave a cell blank**, **never run projects
  outside a container**.
- All the timeboxes: 12 minutes (ins1 spot-checks), 45 minutes (ins2 project), 8 minutes (ins3 Part 3).
- `PARTIAL` and `RED` with a correct reason are still real results that go in the paper. Nothing
  about "getting more greens" has changed — it is still actively unhelpful.
- The end-of-day group message. Same format, just write `v1.1`.

---

## 7. Summary table

| # | Change | Who it affects | Action |
|---|---|---|---|
| A1 | Exact image + package versions recorded | nobody (automatic) | copy 3 new fields into workload YAMLs |
| A2 | `AMBER` projects now usable | ins2 | your input list grew |
| A3 | Projects pre-sorted by type before triage | nobody (automatic) | work the sheet top to bottom as always |
| A4 | ins3 Part 1 automated, Part 2 deleted, Part 3 starts now | ins3 | see §4 |
| A5 | Exact seconds, not rounded to 5 | ins2 | put `time` in front of the command |
| — | ins1 automated; everyone moves to ins2 | ins1 | see §3 |
| — | 10% spot-check is now human-vs-script | everyone | 20 min each morning, §5 |

Questions to the coordinator. As always: **mark it, note it, move on — do not sit and wait for a
reply.**
