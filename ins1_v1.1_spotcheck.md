# INSTRUCTIONS 1 (v1.1) — Build Triage Spot-Check

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.1** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 1-SC]] |
| **Your input list** | The `spotcheck` tab. §1.1 explains where it comes from. |

> **This replaces `ins1.md` (v1.0), and it is a much smaller job than that document described.**
> Triage is now automated and runs unattended overnight. What is left is the part a script cannot do
> for itself: checking whether the script is right. That is this document.

---

## 0. What you are doing

We check whether thousands of open-source Python projects still install and run today. A script now
does that — it runs one project after another, unattended, and writes down what happened.

**Nobody has verified that the script's answers are correct.** That is your job.

You will run the **same check by hand**, on a small sample of projects, and record what *you*
conclude. Afterwards the coordinator compares your answer with the script's.

### The single most important thing about this job

**We are hoping you disagree with the script sometimes.**

Where you and the script agree, we learn that the automation is sound. Where you disagree, we learn
something much more valuable — and that number goes in our paper as a measured result.

So:

- **Never try to work out what the script probably said.** You will not be shown it.
- **Never adjust your answer to look more like what you expect the script to say.**
- **A disagreement you found is worth more than an agreement you produced.**

If you record honestly and the numbers disagree 15% of the time, you have done the job perfectly.
If you quietly nudge your answers toward the script's, the entire exercise produces nothing and we
would be better off not doing it.

### What you will never do

- **You will never read the projects' code.** If you are reading code, you have gone off track.
- **You will never fix a project.** Not one character. A project that would work "with one small
  change" is a `RED` — that is a correct and useful answer.
- **You will never install a project on your own computer.** Everything happens inside a container.

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Setup (§2) and the qualification run (§3) |
| Day 2 | 4 projects |
| Day 3 | 7 projects |
| Day 4 onward | **10 projects per day** |
| Once the script is running nightly | **3–5 projects each morning**, about 20 minutes, before your other work |

A project counts as done when its row has **every column filled** — including for failures. A
half-filled row counts as zero.

### 1.1 Your input list

**Right now, the script has not run yet.** So for your first batch you work from a fixed list of 14
projects — and this is deliberate. You will triage them **before the script ever sees them**, which
means there is no possible way for you to be influenced by its answer.

```
ansible      celery       scrapy       pytest
flask        sqlalchemy   django       requests
click        records      toolz        chardet
black        TheAlgorithms/Python
```

All are at `https://github.com/<owner>/<name>`.

After that, you get 3–5 rows each morning drawn at random from the main list. You will not be told
what the script concluded about them.

---

## 2. One-time setup (do this once, on Day 1)

You need a Mac or a Linux machine. If any step prints an error, copy the **whole** error and message
[[YOUR NAME]] — do not continue past a failed step.

### 2.1 Docker

**On a Mac:** install Docker Desktop from docker.com, then **open it**. It must be running — you
should see a whale icon in your menu bar. Then:

```bash
brew install coreutils
```

That second command is required on Macs. The triage script needs a standard tool called `timeout`
that macOS does not ship. **Without it every project will appear to fail** in a way that looks like
the project's fault but is not.

**On Ubuntu/Debian Linux:**

```bash
sudo apt-get update && sudo apt-get install -y docker.io git
```

```bash
sudo usermod -aG docker $USER
```

**Now log out and log back in.** This is required — the permission change does not apply until you do.

### 2.2 Check Docker works

```bash
docker run --rm hello-world
```

You should see a message containing `Hello from Docker!`.

If you instead see `permission denied while trying to connect to the Docker daemon`, you did not log
out and back in (Linux), or Docker Desktop is not open (Mac).

### 2.3 Unpack the project

You will be sent a file called `traceweave-handoff.tar.gz`.

```bash
mkdir -p ~/Projects && cd ~/Projects && tar xzf /path/to/traceweave-handoff.tar.gz
```

```bash
chmod +x ~/Projects/major/traceweave/triage/triage.sh ~/Projects/major/traceweave/scripts/*.py ~/Projects/major/traceweave/scripts/*.sh
```

### 2.4 ⚠️ Set your own workspace — this step is not optional

**Copy this line into your terminal every time you open a new terminal window:**

```bash
export TW_DATA=$HOME/traceweave-spotcheck
```

Then create it once:

```bash
mkdir -p ~/traceweave-spotcheck/{work,logs,out}
```

**Why this matters more than anything else in this document.** There is a shared folder called
`~/traceweave-data` that holds records which **cannot be recreated**. They are evidence, not output.
The triage script writes into whatever folder it is pointed at, and it **overwrites without warning.**

The line above points it at your own private folder instead. Your results are throwaway — only your
spreadsheet row matters. If you forget this line, you may destroy records the project cannot get back.

To check it is set before you start work:

```bash
echo "$TW_DATA"
```

It must print a path ending in `traceweave-spotcheck`. If it prints nothing, run the `export` line again.

### 2.5 Check the tools are sound

```bash
cd ~/Projects/major/traceweave && ./tests/run_checks.sh
```

**Expect `passed: 6   failed: 0`.** If any check fails, send the output to [[YOUR NAME]] and stop.

---

## 3. Qualification run (required before real work)

Run these three, one at a time. Each may take 2–15 minutes.

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh https://github.com/pallets/click
```

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh https://github.com/kennethreitz/records
```

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh https://github.com/traceweave-nonexistent/nope-xyz
```

Each finishes by printing a block like this:

```
----------------------------------------
RESULT: BUILD_OK TESTS_OK
LOG:    /Users/you/traceweave-spotcheck/out/click/py3.12/attempt.log
----------------------------------------
```

**Two things to confirm:**

1. The `LOG:` path contains **`traceweave-spotcheck`**. If it says `traceweave-data` instead, stop
   immediately — §2.4 did not take effect. Tell [[YOUR NAME]].
2. The third one is a deliberately fake project. It **should** fail, at the very first step, with
   `RESULT: BUILD_FAIL CLONE`. That is the correct answer, not a problem with your setup.

Expected: the first two `BUILD_OK TESTS_OK`, the third `BUILD_FAIL CLONE`. If either of the first two
comes back differently, that is still fine and worth reporting — projects change upstream. Send
[[YOUR NAME]] all three RESULT lines and wait for a reply before starting real work.

---

## 4. The main loop — do this for every project

Work down your tab from top to bottom. Never skip a row.

### Step 1 — Take the next row

Copy the `repo_url` and the `sha` from the next unprocessed row.

### Step 2 — Start a timer

**You have 12 minutes for this project.** Use your phone. This limit is real — see Step 6.

### Step 3 — Run the script

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh <repo_url> <sha>
```

If the `sha` column is empty, leave it out:

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh <repo_url>
```

### Step 4 — Read the RESULT line and use this table

| RESULT line says | What you do |
|---|---|
| `BUILD_OK TESTS_OK` | status = **`GREEN`**. Go to Step 7. |
| `BUILD_OK TESTS_FAIL failing=N` | status = **`AMBER`**, `n_failing` = N. Go to Step 7. |
| `BUILD_OK COLLECT_FAIL` | status = **`AMBER`**, `n_failing` = `collect_fail`. Go to Step 7. |
| `BUILD_FAIL PYTHON_VERSION` | Go to **Recipe 1** (§5). |
| `BUILD_FAIL DEP_RESOLUTION` | Go to **Recipe 2** (§5). |
| `BUILD_FAIL MISSING_SYSTEM_LIB` | Go to **Recipe 3** (§5). |
| `BUILD_FAIL NETWORK` | Run the exact same command **once** more. If `NETWORK` again → status = **`RED`**, error_class = **`NETWORK`**. Go to Step 7. |
| `BUILD_FAIL CLONE` | status = **`RED`**, error_class = **`CLONE`**. Go to Step 7. |
| `BUILD_FAIL OTHER` | status = **`RED`**, error_class = **`OTHER`**. Go to Step 5. |
| Anything not in this table | status = **`UNCLEAR`**. Go to Step 5. |

> **`AMBER` is a good outcome, not a failure.** A project that installs and runs but has some failing
> tests is exactly what our research needs, because running code is what we watch. Do not try to turn
> an `AMBER` into a `GREEN`.

### Step 5 — Only for `OTHER` and `UNCLEAR`: copy the log tail

```bash
tail -25 "$TW_DATA/out/<name>/py3.12/attempt.log"
```

The exact path was printed in the RESULT block — copy it from there. Paste those 25 lines into the
`notes` column. **Do not try to interpret them.** Then go to Step 7.

### Step 6 — The 12-minute rule

The moment your timer hits 12 minutes, whatever you are in the middle of:

- status = **`RED`**, error_class = **`TIMEBOX`**
- `notes` = the last RESULT line you saw, or `no result yet`

Then move to the next project.

**This is a correct and useful outcome.** A project that needs more than 12 minutes of manual effort
is, by our definition, not usable — which is exactly what we need to know.

### Step 7 — ⚠️ Fill in the row, and do not look at the script's answer

Fill in **every** column. See §6.

**Do not open `result.env`.** The folder your run created contains a file called `result.env` which
has a `status=` line in it. That is the *script's* conclusion, worked out by the same logic we are
trying to test. Reading it before you write your own answer destroys the entire point of this job.

Record what **the table in Step 4** told you, from the RESULT line you saw. Nothing else.

### Step 8 — Clean up and move on

```bash
rm -rf "$TW_DATA/work"/*
```

Then go back to Step 1.

---

## 5. The three recipes

Each recipe is a fixed list of attempts. Try them **in order.** Stop at the first that works.
**Never invent a fourth attempt.**

### Recipe 1 — PYTHON_VERSION

Try 3.11, then 3.10, then 3.9 — stopping as soon as one prints `BUILD_OK`:

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh <repo_url> <sha> 3.11
```

`BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.11`**. Done.

If not, repeat the command with `3.10` → fix_applied = **`py3.10`**. Then `3.9` → **`py3.9`**.

All three failed → status = **`RED`**, error_class = **`PYTHON_VERSION`**,
fix_applied = **`tried_3.11_3.10_3.9`**.

### Recipe 2 — DEP_RESOLUTION

Older Python often has older, compatible packages. Try `3.10`, then `3.8`:

```bash
cd ~/Projects/major/traceweave/triage && ./triage.sh <repo_url> <sha> 3.10
```

`BUILD_OK`? → **`GREEN_AFTER_FIX`**, fix_applied = **`py3.10`**. Then `3.8` → **`py3.8`**.

Both failed → status = **`RED`**, error_class = **`DEP_RESOLUTION`**,
fix_applied = **`tried_3.10_3.8`**.

### Recipe 3 — MISSING_SYSTEM_LIB

No retry. It means the project needs software we are not going to install.

status = **`RED`**, error_class = **`MISSING_SYSTEM_LIB`**, fix_applied = **`none`**.

Additionally, run this and paste the output into `notes`:

```bash
grep -iE "fatal error|No such file" "$TW_DATA/out/<name>/py3.12/attempt.log" | head -3
```

> **Record the *first* failure the script reported**, even if a later attempt reported something
> different. Always the first one.

---

## 6. Your spreadsheet — exact columns and allowed values

| Column | What goes in it |
|---|---|
| `row_id` | Already filled in. Do not change. |
| `repo_url` | Already filled in. Do not change. |
| `sha` | Already filled in. Do not change. |
| `status` | **Exactly one of:** `GREEN` `GREEN_AFTER_FIX` `AMBER` `RED` `UNCLEAR` |
| `error_class` | **Exactly one of:** `NONE` `PYTHON_VERSION` `DEP_RESOLUTION` `MISSING_SYSTEM_LIB` `NETWORK` `CLONE` `TIMEBOX` `OTHER` |
| `fix_applied` | **Exactly one of:** `none` `py3.11` `py3.10` `py3.9` `py3.8` `tried_3.11_3.10_3.9` `tried_3.10_3.8` |
| `n_failing` | A number, or `0`, or `collect_fail`, or `na` |
| `minutes_spent` | A whole number of minutes |
| `log_file` | The full `LOG:` path from the RESULT block |
| `result_line_seen` | **New in v1.1.** The RESULT line, copied exactly. e.g. `BUILD_OK TESTS_FAIL failing=3` |
| `notes` | Only required for `OTHER`, `UNCLEAR`, `MISSING_SYSTEM_LIB`. Otherwise `-` |
| `your_name` | Your name |
| `date` | `YYYY-MM-DD` |
| `sheet_version` | `v1.1` |

**Rules about values:**

- `status = GREEN` → `error_class` must be `NONE` and `fix_applied` must be `none`.
- `status = AMBER` → `error_class` must be `NONE`.
- `status = RED` → `error_class` must **not** be `NONE`.
- Spelling must be exact. `Green`, `green`, and `GREEN ` (trailing space) are all wrong. A script
  reads this file and does not forgive typos.

> **On `result_line_seen`:** this is new and it is the most useful column on the sheet. When your
> answer and the script's disagree, this tells us *why* — whether you saw different output, or saw
> the same output and read the table differently. Those are very different problems. Copy it exactly,
> do not retype from memory.

---

## 7. Two fully worked examples

### Example A — a project that works

```
$ cd ~/Projects/major/traceweave/triage
$ ./triage.sh https://github.com/pallets/click
[1/4] cloning ...
[2/4] installing + testing inside python@sha256:55842c72... (can take several minutes) ...
[3/4] recording pins ...
[4/4] classifying ...

----------------------------------------
RESULT: BUILD_OK TESTS_OK
LOG:    /Users/anu/traceweave-spotcheck/out/click/py3.12/attempt.log
----------------------------------------
```

Timer read 6 minutes. The row:

| column | value |
|---|---|
| status | `GREEN` |
| error_class | `NONE` |
| fix_applied | `none` |
| n_failing | `0` |
| minutes_spent | `6` |
| log_file | `/Users/anu/traceweave-spotcheck/out/click/py3.12/attempt.log` |
| result_line_seen | `BUILD_OK TESTS_OK` |
| notes | `-` |

Note the log path contains `traceweave-spotcheck` — §2.4 is working.

### Example B — a recipe was needed, and it still failed

```
$ ./triage.sh https://github.com/someone/oldproject 99ffee1
RESULT: BUILD_FAIL PYTHON_VERSION
```

Table says → Recipe 1.

```
$ ./triage.sh https://github.com/someone/oldproject 99ffee1 3.11
RESULT: BUILD_FAIL DEP_RESOLUTION

$ ./triage.sh https://github.com/someone/oldproject 99ffee1 3.10
RESULT: BUILD_FAIL DEP_RESOLUTION

$ ./triage.sh https://github.com/someone/oldproject 99ffee1 3.9
RESULT: BUILD_FAIL DEP_RESOLUTION
```

All three attempts failed. Timer read 11 minutes. The row:

| column | value |
|---|---|
| status | `RED` |
| error_class | `PYTHON_VERSION` |
| fix_applied | `tried_3.11_3.10_3.9` |
| n_failing | `na` |
| minutes_spent | `11` |
| result_line_seen | `BUILD_FAIL PYTHON_VERSION` |
| notes | `-` |

`error_class` stays as the **first** failure reported, and `result_line_seen` records that first
line — even though the three later attempts said `DEP_RESOLUTION`.

---

## 8. Hard rules

1. **Always set `TW_DATA` (§2.4) before you run anything.** This is the one mistake with
   consequences beyond your own row.
2. **Never open `result.env` before recording your answer.** It contains the script's conclusion.
3. **Never try to guess or match what the script said.** Your honest disagreement is the deliverable.
4. **Never edit the code inside your `work/` folder.** Not a single character. If a project seems
   like it would work with "just one small change", that change is not yours to make — `RED`, move on.
5. **Never install anything on your own machine to make a project work.** Everything happens inside
   the container. (The one exception is `coreutils` in §2.1, which is part of setup, not a fix.)
6. **Never invent an attempt that is not in a recipe.**
7. **Never leave a cell blank.** If you do not know, the answer is `UNCLEAR` — not empty.
8. **Never skip a row** to come back later. Process in order.
9. **Never run two `triage.sh` at the same time.** They will fight over Docker and give wrong answers.

---

## 9. When something goes wrong

| Situation | What to do |
|---|---|
| `timeout: command not found` | Mac only. `brew install coreutils`, then redo that project. §2.1. |
| The `LOG:` path says `traceweave-data` not `traceweave-spotcheck` | **Stop.** Run §2.4's `export` line, then tell [[YOUR NAME]]. Do not run anything else first. |
| `mounts denied: ... not shared from the host` | Your folder is outside your home directory. Keep everything under `~`. |
| The script seems frozen with no output for a long time | Probably still downloading. Wait until your 12 minutes are up, then `Ctrl+C` and mark `RED / TIMEBOX`. |
| `permission denied ... docker daemon` | Linux: you did not log out and back in. Mac: Docker Desktop is not open. |
| `No space left on device` | `docker system prune -af` and `rm -rf "$TW_DATA/work"/*`, then redo the current project. Do this every Friday regardless. |
| Terminal closed / laptop restarted mid-project | Redo that project from Step 1. |
| The RESULT line is not in the Step 4 table | status = `UNCLEAR`, paste the RESULT line into `notes` and `result_line_seen`, move on. |
| Not sure which recipe applies | status = `UNCLEAR`, write which two you were choosing between in `notes`, move on. |
| A loud banner about emulation appears | Copy it and tell [[YOUR NAME]]. Your results are still valid but we need to know. |

### The only three reasons to stop and message [[YOUR NAME]] immediately

1. Docker itself stops working (not a project failing — **Docker** failing).
2. Your machine runs out of disk and `docker system prune -af` does not fix it.
3. More than **8 projects in a row** come out `UNCLEAR`.

**Everything else waits for the daily review.** Mark it `UNCLEAR`, write a one-line note, keep going.
Do not sit and wait for an answer — that is the single most expensive thing that can happen here.

---

## 10. End of every day

1. Confirm every row you touched has all columns filled, including `result_line_seen`.
2. Post one message in the group with exactly this format:

```
DAY <n> — <your name>  (ins1 v1.1 spot-check)
Processed: <number>
GREEN: <n>   GREEN_AFTER_FIX: <n>   AMBER: <n>   RED: <n>   UNCLEAR: <n>
Blocked on: <nothing / one line>
```

3. Once a week, run `docker system prune -af`.

---

## 11. How your work is measured

1. **Completeness** — every column filled, every value spelled exactly as listed. Target: **100%.**
   This matters more than speed.
2. **Independence** — that you recorded what you actually saw. We can detect nudging, because your
   `result_line_seen` has to be consistent with your `status`. This is the one thing that would make
   your work worthless, and it is the easiest to avoid: just write down what you saw.
3. **Throughput** — 10/day in the first batch, then 3–5 each morning.

You are explicitly **not** measured on:

- **How many projects come out `GREEN`.** A day where all 10 are `RED` with correctly filled rows is
  a perfect day. Please do not try to make projects work in order to get more greens — it would
  actively damage the dataset.
- **How often you agree with the script.** We are measuring the script, not you. If your honest
  answers disagree with it often, you have found something real and valuable.
