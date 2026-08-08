# INSTRUCTIONS 1 — Repository Build Triage

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.0** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 1]] |
| **Your input list** | Tab named `candidates` in the same sheet |

---

## 0. What you are doing

We are building a research dataset out of open-source software projects. Before a project can go into the dataset, we have to check one thing: **does it still install and run today?**

Most of them will not. That is completely expected. **A "fail" answer is worth exactly as much to us as a "pass" answer, as long as it is recorded correctly and in the right category.** We are not trying to make broken projects work. We are trying to find out which ones are already working.

Your job for each project:

1. Run one command.
2. Read the last line it prints.
3. Look that line up in a table.
4. Do what the table says.
5. Fill in one row of the spreadsheet.

**You will never read the projects' code. You will never fix the projects' code.** If you find yourself reading code, you have gone off track — stop and go back to the table.

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Finish setup (Section 2) and complete the 3 practice repos |
| Day 2 | 4 repositories |
| Day 3 | 7 repositories |
| Day 4 onward | **10 repositories per day** |
| Per week (from week 2) | **50 repositories** |

A repository counts as "done" when its spreadsheet row has **every column filled in** — including the ones for failures. A half-filled row counts as zero.

---

## 2. One-time setup (do this once, on Day 1)

You need a Linux machine or a Mac. Follow these in order. If any step prints an error, copy the whole error and message [[YOUR NAME]] — do not continue past a failed step.

### 2.1 Install Docker

On Ubuntu/Debian Linux:

```bash
sudo apt-get update
sudo apt-get install -y docker.io git
sudo usermod -aG docker $USER
```

**Now log out and log back in.** (This is required — the permission change does not apply until you do.)

### 2.2 Check that Docker works

```bash
docker run --rm hello-world
```

You should see a message containing the words `Hello from Docker!`.

If you instead see `permission denied while trying to connect to the Docker daemon`, you did not log out and back in. Do that now and try again.

### 2.3 Create your working folders

```bash
mkdir -p ~/triage/work ~/triage/logs
cd ~/triage
```

### 2.4 Create the script

Run this to open a new empty file:

```bash
nano ~/triage/triage.sh
```

Copy **everything** between the two lines below into that file. Then press `Ctrl+O`, then `Enter`, then `Ctrl+X` to save and exit.

--- COPY FROM HERE ---

```bash
#!/usr/bin/env bash
# triage.sh - v1.0
# Usage: ./triage.sh <github-url> [commit-sha] [python-version]
set -uo pipefail

URL="${1:-}"
SHA="${2:-none}"
PYVER="${3:-3.12}"

if [ -z "$URL" ]; then
  echo "USAGE: ./triage.sh <github-url> [commit-sha] [python-version]"
  exit 2
fi

NAME="$(basename "${URL%.git}")"
ROOT="$HOME/triage"
WORK="$ROOT/work/$NAME"
LOG="$ROOT/logs/${NAME}__py${PYVER}.log"
mkdir -p "$ROOT/work" "$ROOT/logs"
rm -rf "$WORK"
: > "$LOG"

finish () {
  echo ""
  echo "----------------------------------------"
  echo "RESULT: $1"
  echo "LOG:    $LOG"
  echo "----------------------------------------"
  echo "RESULT: $1" >> "$LOG"
  exit 0
}

classify () {
  if grep -qiE "requires python|requires-python|python_requires" "$LOG"; then echo "PYTHON_VERSION"; return; fi
  if grep -qiE "ResolutionImpossible|conflicting dependencies|No matching distribution|Could not find a version|version solving failed" "$LOG"; then echo "DEP_RESOLUTION"; return; fi
  if grep -qiE "fatal error: .*\.h: No such file|gcc. failed|error: command .* failed with exit|unable to execute" "$LOG"; then echo "MISSING_SYSTEM_LIB"; return; fi
  if grep -qiE "Temporary failure in name resolution|Could not resolve host|Network is unreachable|Read timed out|Connection refused" "$LOG"; then echo "NETWORK"; return; fi
  echo "OTHER"
}

echo "=== TRIAGE $URL  sha=$SHA  python=$PYVER ===" >> "$LOG"

echo "[1/3] cloning ..."
if ! git clone --quiet "$URL" "$WORK" >> "$LOG" 2>&1; then
  finish "BUILD_FAIL CLONE"
fi
if [ "$SHA" != "none" ]; then
  git -C "$WORK" checkout --quiet "$SHA" >> "$LOG" 2>&1 || echo "WARN: checkout of $SHA failed" >> "$LOG"
fi

echo "[2/3] installing + testing inside python:${PYVER}-slim (can take several minutes) ..."
timeout 1800 docker run --rm -v "$WORK":/repo -w /repo "python:${PYVER}-slim" bash -c '
  set -x
  apt-get update -qq  >/dev/null 2>&1
  apt-get install -y -qq git build-essential >/dev/null 2>&1
  python -m pip install -q --upgrade pip setuptools wheel || { echo "###INSTALL_FAIL###"; exit 1; }

  ok=1
  if   [ -f pyproject.toml ]; then
        python -m pip install ".[test]" || python -m pip install ".[dev]" || python -m pip install "." || ok=0
  elif [ -f setup.py ]; then
        python -m pip install "." || ok=0
  fi
  for r in requirements.txt requirements-dev.txt dev-requirements.txt test-requirements.txt requirements/dev.txt requirements/test.txt; do
    if [ -f "$r" ]; then python -m pip install -r "$r" || ok=0; fi
  done
  if [ "$ok" != "1" ]; then echo "###INSTALL_FAIL###"; exit 1; fi
  echo "###INSTALL_OK###"

  python -m pip install -q pytest pytest-timeout
  if python -m pytest --collect-only -q > /tmp/c.txt 2>&1; then
     echo "###COLLECT_OK###"; tail -5 /tmp/c.txt
  else
     echo "###COLLECT_FAIL###"; tail -40 /tmp/c.txt; exit 1
  fi

  python -m pytest -q --timeout=300 > /tmp/t.txt 2>&1
  rc=$?
  tail -30 /tmp/t.txt
  echo "###TESTS_RC=$rc###"
  grep -oE "[0-9]+ (passed|failed|error|errors)" /tmp/t.txt | tail -6 | sed "s/^/###COUNT /; s/$/###/"
' >> "$LOG" 2>&1

echo "[3/3] classifying ..."
if grep -q "###COLLECT_OK###" "$LOG"; then
  if grep -q "###TESTS_RC=0###" "$LOG"; then
    finish "BUILD_OK TESTS_OK"
  else
    NF="$(grep -oE '###COUNT [0-9]+ (failed|error|errors)###' "$LOG" | grep -oE '[0-9]+' | head -1)"
    finish "BUILD_OK TESTS_FAIL failing=${NF:-unknown}"
  fi
elif grep -q "###COLLECT_FAIL###" "$LOG"; then
  finish "BUILD_OK COLLECT_FAIL"
elif grep -q "###INSTALL_OK###" "$LOG"; then
  finish "BUILD_OK COLLECT_FAIL"
else
  finish "BUILD_FAIL $(classify)"
fi
```

--- COPY TO HERE ---

### 2.5 Make the script runnable

```bash
chmod +x ~/triage/triage.sh
```

### 2.6 Practice run (required before real work)

Run these three, one at a time. Each may take 5–15 minutes.

```bash
cd ~/triage
./triage.sh https://github.com/psf/requests
./triage.sh https://github.com/pallets/click
./triage.sh https://github.com/kennethreitz/records
```

You may get different answers than anyone else — **that is fine.** The purpose of the practice run is only to confirm that your setup works end to end. What you need to see is that each run finishes and prints a block that looks like:

```
----------------------------------------
RESULT: BUILD_OK TESTS_OK
LOG:    /home/you/triage/logs/requests__py3.12.log
----------------------------------------
```

Message [[YOUR NAME]] with the three RESULT lines you got. Wait for a reply before starting real work.

---

## 3. The main loop — do this for every repository

Work down the `candidates` tab from top to bottom. Never skip a row.

### Step 1 — Take the next row
Copy the `repo_url` and the `sha` from the next unprocessed row.

### Step 2 — Start a timer
**You have 12 minutes for this repository.** Use your phone. This limit is real and it is not negotiable — see Step 6.

### Step 3 — Run the script

```bash
cd ~/triage
./triage.sh <repo_url> <sha>
```

If the `sha` column is empty, just leave it out:

```bash
./triage.sh <repo_url>
```

### Step 4 — Read the RESULT line and use this table

| RESULT line says | What you do |
|---|---|
| `BUILD_OK TESTS_OK` | status = **`GREEN`**. Go to Step 7. |
| `BUILD_OK TESTS_FAIL failing=N` | status = **`AMBER`**, `n_failing` = N. Go to Step 7. |
| `BUILD_OK COLLECT_FAIL` | status = **`AMBER`**, `n_failing` = `collect_fail`. Go to Step 7. |
| `BUILD_FAIL PYTHON_VERSION` | Go to **Recipe 1**. |
| `BUILD_FAIL DEP_RESOLUTION` | Go to **Recipe 2**. |
| `BUILD_FAIL MISSING_SYSTEM_LIB` | Go to **Recipe 3**. |
| `BUILD_FAIL NETWORK` | Run the exact same command **once** more. If it says `NETWORK` again → status = **`RED`**, error_class = **`NETWORK`**. Go to Step 7. |
| `BUILD_FAIL CLONE` | status = **`RED`**, error_class = **`CLONE`**. Go to Step 7. |
| `BUILD_FAIL OTHER` | status = **`RED`**, error_class = **`OTHER`**. Go to Step 5. |
| Anything not in this table | status = **`UNCLEAR`**. Go to Step 5. |

### Step 5 — Only for `OTHER` and `UNCLEAR`: copy the log tail

```bash
tail -25 ~/triage/logs/<name>__py3.12.log
```

(The exact log path was printed in the RESULT block — copy it from there.)

Paste those 25 lines into the `notes` column. **Do not try to interpret them.** Then go to Step 7.

### Step 6 — The 12-minute rule

The moment your timer hits 12 minutes, whatever you are in the middle of:

- status = **`RED`**
- error_class = **`TIMEBOX`**
- `notes` = the last RESULT line you saw, or `no result yet`

Then move to the next repository.

**This is a correct and useful outcome.** It is not giving up and it is not a mistake. A repository that takes more than 12 minutes of manual effort is, by our definition, not usable — which is exactly what we need to know.

### Step 7 — Fill in the row completely

Every column. No blanks. See Section 5 for the allowed values.

### Step 8 — Update the counter

Update the `done / total` counter at the top of the sheet. Then go back to Step 1.

---

## 4. The three recipes

Each recipe is a fixed list of attempts. Try them **in order**. Stop at the first one that works. Never invent a fourth attempt.

### Recipe 1 — PYTHON_VERSION

```bash
./triage.sh <repo_url> <sha> 3.11
```
Did it print `BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.11`**. Done.

If not:
```bash
./triage.sh <repo_url> <sha> 3.10
```
Did it print `BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.10`**. Done.

If not:
```bash
./triage.sh <repo_url> <sha> 3.9
```
Did it print `BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.9`**. Done.

All three failed → status = **`RED`**, error_class = **`PYTHON_VERSION`**, fix_applied = **`tried_3.11_3.10_3.9`**.

### Recipe 2 — DEP_RESOLUTION

Attempt 1 — older Python often has older, compatible packages:
```bash
./triage.sh <repo_url> <sha> 3.10
```
`BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.10`**. Done.

Attempt 2:
```bash
./triage.sh <repo_url> <sha> 3.8
```
`BUILD_OK`? → status = **`GREEN_AFTER_FIX`**, fix_applied = **`py3.8`**. Done.

Both failed → status = **`RED`**, error_class = **`DEP_RESOLUTION`**, fix_applied = **`tried_3.10_3.8`**.

### Recipe 3 — MISSING_SYSTEM_LIB

There is no retry for this one. It means the project needs software we are not going to install.

status = **`RED`**, error_class = **`MISSING_SYSTEM_LIB`**, fix_applied = **`none`**.

Additionally: run `grep -iE "fatal error|No such file" ~/triage/logs/<name>__py3.12.log | head -3` and paste the output into `notes`.

---

## 5. The spreadsheet — exact columns and allowed values

Fill these columns, in this order:

| Column | What goes in it |
|---|---|
| `row_id` | Already filled in for you. Do not change. |
| `repo_url` | Already filled in. Do not change. |
| `sha` | Already filled in. Do not change. |
| `status` | **Exactly one of:** `GREEN` `GREEN_AFTER_FIX` `AMBER` `RED` `UNCLEAR` |
| `error_class` | **Exactly one of:** `NONE` `PYTHON_VERSION` `DEP_RESOLUTION` `MISSING_SYSTEM_LIB` `NETWORK` `CLONE` `TIMEBOX` `OTHER` |
| `fix_applied` | **Exactly one of:** `none` `py3.11` `py3.10` `py3.9` `py3.8` `tried_3.11_3.10_3.9` `tried_3.10_3.8` |
| `n_failing` | A number, or `0`, or `collect_fail`, or `na` |
| `minutes_spent` | A whole number of minutes |
| `log_file` | The full `LOG:` path from the RESULT block |
| `notes` | Only required for `OTHER`, `UNCLEAR`, and `MISSING_SYSTEM_LIB`. Otherwise write `-` |
| `your_name` | Your name |
| `date` | Today's date, `YYYY-MM-DD` |
| `sheet_version` | `v1.0` |

**Rules about values:**

- `status = GREEN` → `error_class` must be `NONE` and `fix_applied` must be `none`.
- `status = AMBER` → `error_class` must be `NONE`.
- `status = RED` → `error_class` must **not** be `NONE`.
- Spelling must be exact. `Green`, `green`, and `GREEN ` (with a space) are all wrong. A script reads this file.

---

## 6. Two fully worked examples

### Example A — a repository that works

```
$ cd ~/triage
$ ./triage.sh https://github.com/pallets/click abc1234
[1/3] cloning ...
[2/3] installing + testing inside python:3.12-slim (can take several minutes) ...
[3/3] classifying ...

----------------------------------------
RESULT: BUILD_OK TESTS_OK
LOG:    /home/anu/triage/logs/click__py3.12.log
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
| log_file | `/home/anu/triage/logs/click__py3.12.log` |
| notes | `-` |

### Example B — a repository that needed a recipe, then still failed

```
$ ./triage.sh https://github.com/someone/oldproject 99ffee1
...
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

All three attempts of Recipe 1 failed. Timer read 11 minutes. The row:

| column | value |
|---|---|
| status | `RED` |
| error_class | `PYTHON_VERSION` |
| fix_applied | `tried_3.11_3.10_3.9` |
| n_failing | `na` |
| minutes_spent | `11` |
| log_file | `/home/anu/triage/logs/oldproject__py3.9.log` |
| notes | `-` |

Note that `error_class` stays as the **first** failure the script reported, even though later attempts reported something different. Always record the first one.

---

## 7. Hard rules

1. **Never edit the code inside `~/triage/work/`.** Not a single character. If a project seems like it would work with "just one small change," that change is not yours to make — mark it `RED` and move on.
2. **Never install anything on your own machine to make a project work.** Everything happens inside the container.
3. **Never invent an attempt that is not in a recipe.**
4. **Never leave a cell blank.** If you don't know, the answer is `UNCLEAR` — not empty.
5. **Never skip a row** to come back to it later. Process in order.
6. **Never run more than one `triage.sh` at the same time.** They will fight over Docker and give wrong answers.

---

## 8. When something goes wrong

| Situation | What to do |
|---|---|
| The script seems frozen with no output for a long time | It is probably still downloading. Wait until your 12 minutes are up, then `Ctrl+C` and mark `RED / TIMEBOX`. |
| `permission denied ... docker daemon` | You did not log out and back in after setup 2.1. Do that. |
| `No space left on device` | Run `docker system prune -af` and `rm -rf ~/triage/work/*`, then redo the current repo. Do this every Friday regardless. |
| The terminal window closed / laptop restarted mid-repo | Just redo that repository from Step 1. |
| The RESULT line is something not in the Step 4 table | status = `UNCLEAR`, paste the RESULT line into `notes`, move on. |
| You are not sure which recipe applies | status = `UNCLEAR`, write which two you were choosing between in `notes`, move on. |

### The only three reasons to stop and message [[YOUR NAME]] immediately

1. Docker itself stops working (not a project failing — Docker failing).
2. Your machine runs out of disk and `docker system prune -af` does not fix it.
3. More than **8 repositories in a row** come out `UNCLEAR`.

**Everything else waits for the daily review.** Mark it `UNCLEAR`, write a one-line note, keep going. Do not sit and wait for an answer — that is the single most expensive thing that can happen on this task.

---

## 9. End of every day

1. Confirm every row you touched today has all columns filled.
2. Update the counter at the top of the sheet.
3. Post one message in the group with exactly this format:

```
DAY <n> — <your name>
Processed: <number>
GREEN: <n>   GREEN_AFTER_FIX: <n>   AMBER: <n>   RED: <n>   UNCLEAR: <n>
Blocked on: <nothing / one line>
```

4. Once a week, run `docker system prune -af`.

---

## 10. How your work is measured

You are measured on **three** things, in this order:

1. **Completeness** — the percentage of your rows with every column filled and every value spelled exactly as listed in Section 5. Target: **100%**. This matters more than speed.
2. **Throughput** — repositories per day. Target: **10/day from Day 4.**
3. **Agreement** — roughly 1 repository in 10 is secretly also processed by someone else. Your `status` should match theirs. Target: **at least 9 out of 10 matching.**

You are explicitly **not** measured on how many repositories come out `GREEN`. A day where all 10 come out `RED` and every row is correctly filled is a perfect day. Please do not try to make projects work in order to get more greens — it would actively damage the dataset.
