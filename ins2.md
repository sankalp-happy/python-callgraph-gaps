# INSTRUCTIONS 2 — Recording How Each Project Is Run

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.0** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 2]] |
| **Your input list** | The `GREEN` and `GREEN_AFTER_FIX` rows in [[LINK TO SHEET 1]] |

---

## 0. What you are doing

For our research we need to **run** each software project and watch what it does while it runs. Before we can do that, somebody has to figure out *how* each project is meant to be run, write those instructions down in a fixed format, and prove they actually work.

That is your job. For each project you produce a small file listing 3 or more ways to run it — the exact commands, the exact settings, and proof that each one worked.

These files are a published output of our research. Other researchers will download and use them. So the standard is: **someone who has never seen the project must be able to copy your file and get the same result.**

**You do not need to understand what the project does.** You need to find its instructions, follow them exactly, and record precisely what you did.

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Setup (Section 2) + both practice projects |
| Day 2 | 1 project |
| Day 3 | 2 projects |
| Day 4 onward | **3 projects per day** |
| Per week (from week 2) | **15 projects** |

A project counts as done when it has a folder containing **at least 3 valid workload files**, at least one of which is `kind: test_suite`, and every one of them has been run twice with the same exit code.

**A project with 2 workloads counts as zero.** Three is the minimum.

---

## 2. One-time setup (Day 1)

### 2.1 You need Docker and git

Same as Instructions 1. If it is not installed:

```bash
sudo apt-get update
sudo apt-get install -y docker.io git
sudo usermod -aG docker $USER
```

**Log out and log back in**, then check:

```bash
docker run --rm hello-world
```

You should see `Hello from Docker!`.

### 2.2 Create your folders

```bash
mkdir -p ~/workloads
cd ~/workloads
```

### 2.3 Learn the two commands you will use constantly

**Command A — open a container for a project:**

```bash
cd ~/workloads
git clone <repo_url> ./repo-<name>
docker run -it --rm -v ~/workloads/repo-<name>:/repo -w /repo python:3.12-slim bash
```

After this you are "inside" the container. Your prompt will change to something like `root@a3f9c2:/repo#`. Everything you type now happens inside the container, not on your computer.

**Command B — check whether the last thing you ran succeeded:**

```bash
echo $?
```

This prints a number. **`0` means it worked. Anything else means it failed.** You will type this after every single command you record. This number is one of the most important things you record.

### 2.4 Practice (required)

Do these two projects completely, following Section 3, before touching real work:

- `https://github.com/psf/requests`
- `https://github.com/pallets/click`

Send both finished folders to [[YOUR NAME]] and wait for a reply before starting real projects.

---

## 3. The procedure for one project

### Step 1 — Set up the project

```bash
cd ~/workloads
git clone <repo_url> ./repo-<name>
mkdir -p ~/workloads/out/<name>
```

Replace `<name>` with the last part of the URL. For `https://github.com/psf/requests` the name is `requests`.

### Step 2 — Find the candidate commands (in your browser, not the terminal)

Open the project's GitHub page. Look at the front page (the README) and find any section titled one of:

- Quickstart
- Getting Started
- Usage
- Installation
- Running the tests
- Development / Contributing
- Examples

Inside those sections, every **grey code box that contains a command** is a candidate.

**A command looks like:** `pytest`, `python -m mypackage`, `make test`, `./run.sh`, `python examples/demo.py`, `mytool --help`

**These are NOT commands — skip them:** `pip install requests`, `import requests`, `git clone ...`, `def main():`, anything with `>>>` at the start, anything that is clearly Python code rather than something you type into a terminal.

Write your candidate list on paper or in a scratch file. You want **5 to 8 candidates** before you start. If the README has fewer than 3 candidates, also check inside the `docs/` folder and any file called `CONTRIBUTING.md`.

### Step 3 — Open the container

```bash
docker run -it --rm -v ~/workloads/repo-<name>:/repo -w /repo python:3.12-slim bash
```

Then, inside the container, install the project:

```bash
apt-get update -qq && apt-get install -y -qq git build-essential
pip install -q --upgrade pip setuptools wheel
pip install . || true
[ -f requirements.txt ] && pip install -r requirements.txt
[ -f requirements-dev.txt ] && pip install -r requirements-dev.txt
pip install -q pytest
```

### Step 4 — Try each candidate, one at a time

For each candidate command from Step 2:

1. Type it exactly.
2. Wait for it to finish.
3. Type `echo $?` and write down the number.
4. Write down roughly how many seconds it took.

**Keep the ones where `echo $?` printed `0`.** Discard the rest — you do not need to fix them.

**Special case:** for a test command like `pytest`, an exit code of `1` is acceptable **if** the output shows tests actually ran (you will see a line like `12 failed, 340 passed`). In that case keep it and record the real exit code. What you must discard is a command that printed an error and ran nothing at all — e.g. `command not found`, `No such file or directory`, `ModuleNotFoundError`.

**Stop as soon as you have 3 keepers.** You do not need to try the rest.

If you run out of candidates with fewer than 3 keepers, go to Section 6.

### Step 5 — Run each keeper a second time

Leave the container, make a fresh one, reinstall (Step 3), and run each keeper again. Record whether `echo $?` printed the **same number** as the first time.

This is not optional. Reproducibility is the entire point of the file you are producing.

### Step 6 — Write one file per keeper

For each keeper, create a file at `~/workloads/out/<name>/<name>_w01.yaml`, then `_w02`, `_w03`, and so on. Use the template in Section 4.

### Step 7 — Fill in your spreadsheet row and move on

---

## 4. The file template

Copy this exactly. Fill in everything after the colon. **Never delete a line** — if something does not apply, write `none`.

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
duration_s:      
second_run_exit_code: 
same_both_times: 
recorded_by:     
date:            
sheet_version:   v1.0
notes:           
```

### What goes in each field

| Field | What to write |
|---|---|
| `repo` | The short name, e.g. `requests` |
| `repo_url` | The full GitHub URL |
| `workload_id` | `<name>_w01`, `<name>_w02`, ... — must match the filename |
| `kind` | **Exactly one of:** `test_suite` `demo_script` `cli_usage` (see below) |
| `command` | The command you typed, character for character. Copy-paste it — do not retype from memory. |
| `working_dir` | `/repo` unless you used `cd` to go somewhere else, then write that path |
| `env_vars` | Every `VAR=value` you had to set. If none, write `none` |
| `inputs` | Any file you had to create or download first. If none, write `none` |
| `exit_code` | The number `echo $?` printed the first time |
| `duration_s` | Roughly how many seconds it took. Round to the nearest 5. |
| `second_run_exit_code` | The number from the second run |
| `same_both_times` | `yes` or `no` |
| `recorded_by` | Your name |
| `date` | `YYYY-MM-DD` |
| `notes` | Anything odd, or `-` |

### Choosing `kind` — use exactly these rules

- The command runs the project's tests (contains `pytest`, `unittest`, `nose`, `tox`, or `make test`) → **`test_suite`**
- The command runs a file from an `examples/`, `demo/`, `samples/`, or `scripts/` folder → **`demo_script`**
- Anything else that runs the project itself → **`cli_usage`**

If two rules seem to apply, use the one higher in the list.

---

## 5. A fully worked example

Project: `https://github.com/pallets/click`

**Step 2 — candidates found in the README and CONTRIBUTING.md:**

```
1. pip install click                 -> SKIP (installation, not a command that runs it)
2. pytest                            -> candidate
3. pip install -e .                  -> SKIP (installation)
4. tox                               -> candidate
5. python examples/hello/hello.py    -> candidate
6. python -m pytest --cov            -> candidate
```

**Step 4 — trying them:**

```
root@a3f:/repo# pytest
....................................... [100%]
560 passed in 4.21s
root@a3f:/repo# echo $?
0                                     -> KEEP

root@a3f:/repo# tox
bash: tox: command not found
root@a3f:/repo# echo $?
127                                   -> DISCARD

root@a3f:/repo# python examples/hello/hello.py --name Anu
Hello Anu!
root@a3f:/repo# echo $?
0                                     -> KEEP

root@a3f:/repo# python -m pytest --cov
ERROR: unrecognized arguments: --cov
root@a3f:/repo# echo $?
4                                     -> DISCARD
```

Only 2 keepers, so back to Step 2 to find more. Checked the `examples/` folder directly on GitHub and found `examples/colors/colors.py`:

```
root@a3f:/repo# python examples/colors/colors.py
...
root@a3f:/repo# echo $?
0                                     -> KEEP
```

Now 3 keepers. Step 5 (second run) gave `0`, `0`, `0` again.

**The three files produced:**

`~/workloads/out/click/click_w01.yaml`
```yaml
repo:            click
repo_url:        https://github.com/pallets/click
workload_id:     click_w01
kind:            test_suite
command:         pytest
working_dir:     /repo
env_vars:        none
inputs:          none
exit_code:       0
duration_s:      5
second_run_exit_code: 0
same_both_times: yes
recorded_by:     Anu
date:            2026-08-03
sheet_version:   v1.0
notes:           560 tests passed
```

`~/workloads/out/click/click_w02.yaml`
```yaml
repo:            click
repo_url:        https://github.com/pallets/click
workload_id:     click_w02
kind:            demo_script
command:         python examples/hello/hello.py --name Anu
working_dir:     /repo
env_vars:        none
inputs:          none
exit_code:       0
duration_s:      5
second_run_exit_code: 0
same_both_times: yes
recorded_by:     Anu
date:            2026-08-03
sheet_version:   v1.0
notes:           -
```

`~/workloads/out/click/click_w03.yaml`
```yaml
repo:            click
repo_url:        https://github.com/pallets/click
workload_id:     click_w03
kind:            demo_script
command:         python examples/colors/colors.py
working_dir:     /repo
env_vars:        none
inputs:          none
exit_code:       0
duration_s:      5
second_run_exit_code: 0
same_both_times: yes
recorded_by:     Anu
date:            2026-08-03
sheet_version:   v1.0
notes:           -
```

---

## 6. When you cannot find 3 workloads

Spend at most **45 minutes** on any one project. When that time is up, or when you have exhausted every candidate:

1. Save whatever valid workload files you did produce (1 or 2 is fine to save).
2. In the spreadsheet, set `status` = `PARTIAL` and `n_workloads` = however many you got.
3. In `blocker`, choose **exactly one**:
   - `NO_COMMANDS_IN_DOCS` — the README had no runnable commands at all
   - `ALL_COMMANDS_FAILED` — you found commands but every one exited non-zero and ran nothing
   - `NEEDS_EXTERNAL_SERVICE` — commands complained about a database, server, API key, or network connection
   - `NEEDS_GUI` — it wants a graphical window, a browser, or a display
   - `TOO_SLOW` — a single command was still running after 15 minutes
   - `OTHER` — write one sentence in `notes`
4. Move to the next project.

**A `PARTIAL` project with a correctly chosen blocker is a real result that goes in our paper.** It is not a failure on your part.

---

## 7. The spreadsheet

| Column | Allowed values |
|---|---|
| `repo` | short name |
| `repo_url` | full URL |
| `status` | **Exactly one of:** `DONE` `PARTIAL` `SKIPPED` |
| `n_workloads` | a number, `0` to `8` |
| `has_test_suite` | `yes` or `no` |
| `all_reproduced` | `yes` or `no` — were all second runs the same? |
| `blocker` | `none` or one of the six values from Section 6 |
| `minutes_spent` | whole number |
| `output_folder` | e.g. `~/workloads/out/click` |
| `recorded_by` | your name |
| `date` | `YYYY-MM-DD` |
| `sheet_version` | `v1.0` |
| `notes` | `-` if nothing |

**Rules:**
- `status = DONE` requires `n_workloads` ≥ 3 **and** `has_test_suite = yes` **and** `blocker = none`.
- `status = PARTIAL` requires a `blocker` that is not `none`.
- Spelling must be exact — a script reads this.

---

## 8. Hard rules

1. **Copy-paste every command into the YAML file.** Do not retype it from memory. A single wrong character makes the file useless, and the whole point of the file is that it can be replayed.
2. **Never modify the project's code** to make a command work.
3. **Never record a command you did not actually run.** Every line in every file must be something you personally typed and watched finish.
4. **Never record a command that needs your personal information** — an API key, a password, a token. If a command asks for one, that is `NEEDS_EXTERNAL_SERVICE`.
5. **Never run these projects outside a container.** Always inside `docker run`.
6. **If a command asks you a question and waits for you to type something**, that is not usable. Press `Ctrl+C`, discard it.

---

## 9. When something goes wrong

| Situation | What to do |
|---|---|
| A command has been running for more than 15 minutes | `Ctrl+C`, discard that candidate, try the next one |
| A command is printing endless output | `Ctrl+C`, discard it |
| Your prompt says `>>>` | You are inside Python, not the terminal. Type `exit()` and press Enter. |
| Your prompt says `>` and nothing works | Press `Ctrl+C` |
| You cannot get out of the container | Type `exit` and press Enter |
| The install step in Step 3 failed | Try again once. If it fails again, `status = SKIPPED`, `notes = install failed`, move on. |
| You cannot tell which `kind` applies | Use `cli_usage` and write your uncertainty in `notes` |

### The only two reasons to message [[YOUR NAME]] immediately

1. Docker itself stops working.
2. Three projects in a row come out `SKIPPED`.

Everything else goes in `notes` and waits for the daily review. **Do not sit and wait for a reply — keep moving down the list.**

---

## 10. End of every day

1. Check that every finished project folder has ≥3 `.yaml` files.
2. Update your spreadsheet rows.
3. Post in the group:

```
DAY <n> — <your name>
Projects done: <n>   Partial: <n>   Skipped: <n>
Total workload files written: <n>
Blocked on: <nothing / one line>
```

4. Once a week, run `docker system prune -af` and `rm -rf ~/workloads/repo-*`.

---

## 11. How your work is measured

1. **Replay rate** — every night, a script re-runs every workload file you wrote, using only what is in the file. If it does not reproduce your recorded exit code, the file is rejected and comes back to you. Target: **at least 90% of your files replay successfully.** This is the single most important number.
2. **Completeness** — projects reaching `DONE` with ≥3 workloads including a `test_suite`. Target: **3 per day.**
3. **Field accuracy** — no blank fields, exact spelling on `kind`, `status`, and `blocker`. Target: **100%.**

You are **not** measured on how many projects reach `DONE` versus `PARTIAL`. A correctly-diagnosed `PARTIAL` is a real research finding. Getting to `DONE` by recording a command you didn't really run is the one thing that would genuinely damage the project.
