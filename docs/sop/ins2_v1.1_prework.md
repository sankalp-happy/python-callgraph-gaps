# INSTRUCTIONS 2 (v1.1) — Part A: Finding Candidate Commands

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.1** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 2]] — the `prework` tab |
| **Your input list** | See §1.1 — starts with a fixed list of 14, grows later |

> **This is the first half of `ins2.md`, split out so it can be done now.** `ins2.md` has you find
> candidate commands in a browser (its §3 Step 2), then verify them inside a container (Steps 3–6).
> The container half needs work that is not finished yet. The browser half does not. So you do the
> browser half now, and the verification becomes quick later.
>
> **You need only a web browser. No terminal. Nothing to install.**

---

## 0. What you are doing

For our research we need to **run** each software project and watch what it does while it runs.
Before that, somebody has to work out *how* each project is meant to be run.

That is the hardest part of this whole project to automate, and it is the reason this job exists. A
script can check whether a project installs. **No script can read a page of English prose and work
out which of the six grey boxes on it is a command you could actually type.** That judgement is
yours, and the research is waiting on it.

Your job: for each project, produce a **list of 5–8 candidate commands** that look like they would
run the project, and say where you found each one.

### The one rule that matters more than all the others

**You are not running anything, so you must not record anything that implies you did.**

Later, somebody opens a container and tries every candidate on your list. Some will work, some will
not — that is expected and fine. What would genuinely damage the research is a row that *looks* like
it was tested when it was not.

So:

- **Never write an exit code.** There is no column for one. If you find yourself wanting one, stop.
- **Never write a duration.** Same.
- **Never mark anything "works" or "verified".** You cannot know that yet, and nobody expects you to.
- A candidate that turns out to fail is **not** a mistake on your part. Listing 6 candidates of which
  2 work is a completely successful project.

You are producing a shortlist for someone else to test. That is the whole job, and it is enough.

### What you will never do

- **You will never read the projects' code** beyond checking whether a file exists.
- **You will never install or download anything.**
- **You will never edit a project.**

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Qualification check (§2) — about 30 minutes |
| Day 1, rest of day | As many of the 14 starter projects as you get through |
| Day 2 onward | **12 projects per day** |

A project counts as done when it has **at least 3 candidate rows** on the `prework` tab, or a row
explaining why it has fewer (§6).

### 1.1 Your input list

**Start with these 14.** They are the projects everything else is calibrated against, so they are
needed first:

```
ansible      celery       scrapy       pytest
flask        sqlalchemy   django       requests
click        records      toolz        chardet
black        TheAlgorithms/Python
```

All are at `https://github.com/<owner>/<name>`. A longer list (400–600 projects) is being generated
and will be added to your sheet later. Work the 14 first.

---

## 2. Qualification check — do this first

Do `https://github.com/pallets/click` by yourself using §3. Then compare with the answers below.
**Do not read the answers first.**

<details>
<summary><b>Expected answer — open only after you have written yours down</b></summary>

You should have found roughly these, and **rejected** the install lines:

| command | source | keep? |
|---|---|---|
| `pip install click` | README.md | ❌ **reject** — installation, not running the project |
| `pip install -e .` | README.md | ❌ **reject** — installation |
| `pytest` | CONTRIBUTING / standard | ✅ candidate, `test_suite` |
| `python examples/colors/colors.py` | `examples/` folder | ✅ candidate, `demo_script` |
| `python examples/naval/naval.py` | `examples/` folder | ✅ candidate, `demo_script` |
| `python examples/termui/termui.py` | `examples/` folder | ✅ candidate, `demo_script` |
| `python hello.py` | README.md | ⚠️ **candidate, but flag it** — see below |

**The `python hello.py` trap.** click's README shows a small program and then `python hello.py`. But
**there is no `hello.py` file in the repository** — the README expects *you* to create it from the
snippet above. So that command will fail with "No such file or directory" for anyone who just clones
the project.

You should still list it, with `file_exists_in_repo` = `no` and `confidence` = `low`. Spotting that
is exactly the judgement this job is for. If you marked it `yes`, re-read §3.4.

**Did you find `examples/hello/hello.py`?** You should not have — it does not exist. If you listed it,
you guessed from the README rather than checking the `examples/` folder. §3.4, rule 3.

</details>

- **Broadly matched?** You do not need to have found the same 6. Message [[YOUR NAME]] with your list
  and start on the 14. What matters is that you rejected the `pip install` lines and flagged
  `hello.py`.
- **Kept an install line, or marked `hello.py` as existing?** Re-read §3, and message [[YOUR NAME]].
  Do not start real work yet.

---

## 3. The procedure for one project

**Time limit: 20 minutes per project.** When it is up, save what you have and move on.

### 3.1 Where to look

Open the project's GitHub page and check these, in this order:

1. The **README** on the front page — sections titled *Quickstart*, *Getting Started*, *Usage*,
   *Running the tests*, *Development*, *Contributing*, *Examples*
2. `CONTRIBUTING.md` or `CONTRIBUTING.rst`
3. An **`examples/`** folder — click into it and list the actual `.py` files. **This is usually the
   richest source and the most often missed.**
4. A `demo/`, `samples/`, or `scripts/` folder
5. Anything in `docs/` that looks like a tutorial
6. A `Makefile` or `tox.ini` — the target names are candidates (`make test`, `tox`)

### 3.2 What a command looks like

**These are commands:**

```
pytest
python -m mypackage
make test
./run.sh
python examples/demo.py
mytool --help
tox
```

**These are NOT commands — reject them:**

```
pip install requests          <- installing, not running
pip install -e .              <- installing
conda install ...             <- installing
import requests               <- Python code, not a terminal command
def main():                   <- Python code
>>> something                 <- the ">>>" means it is typed inside Python, not a terminal
git clone ...                 <- getting the code, which is already done
docker build ...              <- ask [[YOUR NAME]] before listing these
```

### 3.3 How many

Aim for **5–8 candidates.** Stop at 8 — more is not better, and somebody has to try each one.

If the README gives you fewer than 3, check the `examples/` folder and `CONTRIBUTING`. If you still
have fewer than 3, go to §6.

### 3.4 Three checks that make your list worth having

**1. Does the file actually exist?**

If a candidate names a file — `python examples/demo.py`, `./run.sh` — **click through the repository
and confirm that file is really there.** Set `file_exists_in_repo` to `yes` or `no`.

This one check is most of the value you add. A README written three years ago often references files
that have since moved or been deleted.

**2. Where did you actually find it?**

`source_file` must be the file you *read it in* — `README.md`, `CONTRIBUTING.rst`,
`examples/ folder`. If you inferred a command from a folder listing rather than reading it in prose,
write `examples/ folder` (that is a perfectly good source).

**3. Do not invent commands from a pattern.**

If you see `examples/colors/colors.py`, do **not** also list `examples/hello/hello.py` because it
seems like it should exist. List only what you saw or clicked into and confirmed.

### 3.5 Guessing the kind

Use the same rules `ins2.md` §4 uses. If two seem to apply, take the one higher in the list:

- Runs the tests (`pytest`, `unittest`, `nose`, `tox`, `make test`) → **`test_suite`**
- Runs a file from `examples/`, `demo/`, `samples/`, `scripts/` → **`demo_script`**
- Anything else that runs the project → **`cli_usage`**

**Every project needs at least one `test_suite` candidate.** Almost all of these have a test suite
even if the README never mentions it — if the project has a `tests/` folder, `pytest` is a valid
candidate and you should list it.

---

## 4. What to record — the `prework` tab

One row per candidate:

| Column | What to write |
|---|---|
| `repo` | Short name, e.g. `click` |
| `repo_url` | Full GitHub URL |
| `candidate_id` | `<name>_c01`, `<name>_c02`, … in the order you found them |
| `command` | **Copy-paste it.** Character for character. Do not retype from memory. |
| `source_file` | Where you read it: `README.md`, `CONTRIBUTING.rst`, `examples/ folder`, `Makefile` |
| `likely_kind` | `test_suite` `demo_script` `cli_usage` — your best guess, §3.5 |
| `file_exists_in_repo` | `yes` `no` `na` — `na` if the command names no file (e.g. `pytest`) |
| `confidence` | `high` `medium` `low` — §4.1 |
| `notes` | Anything odd, or `-` |
| `recorded_by` / `date` / `sheet_version` | your name / `YYYY-MM-DD` / `v1.1` |

**There is deliberately no `exit_code`, no `duration_s`, and no `verified` column.** Those get filled
later, by someone who actually ran it.

### 4.1 Choosing `confidence`

| Write | When |
|---|---|
| `high` | Named in the docs as a way to run the project, and any file it references exists |
| `medium` | You are reasonably sure, but it was implied rather than stated — e.g. `pytest` because there is a `tests/` folder |
| `low` | Something looks off — the file does not exist, or it may need a database, a key, or a display |

**`low` is a useful answer, not an admission.** It tells the next person to try it last.

---

## 5. A fully worked example

Project: `https://github.com/pallets/click`

**§3.1 — walking the locations:**

```
README.md          -> "pip install click"   (install, reject)
                      "python hello.py"     (candidate, but no hello.py in the repo!)
CONTRIBUTING       -> not present at top level
examples/ folder   -> clicked in. Contains: aliases/ colors/ completion/
                      imagepipe/ inout/ naval/ repo/ termui/ validation/
                      Each has a .py inside. Rich source.
tests/ folder      -> present, so "pytest" is a fair candidate
```

**The resulting rows:**

| candidate_id | command | source_file | likely_kind | file_exists | confidence |
|---|---|---|---|---|---|
| click_c01 | `pytest` | `tests/ folder` | `test_suite` | `na` | `medium` |
| click_c02 | `python examples/colors/colors.py` | `examples/ folder` | `demo_script` | `yes` | `high` |
| click_c03 | `python examples/naval/naval.py` | `examples/ folder` | `demo_script` | `yes` | `high` |
| click_c04 | `python examples/termui/termui.py` | `examples/ folder` | `demo_script` | `yes` | `high` |
| click_c05 | `python examples/validation/validation.py` | `examples/ folder` | `demo_script` | `yes` | `high` |
| click_c06 | `python hello.py` | `README.md` | `cli_usage` | **`no`** | **`low`** |

`click_c06`'s `notes`: `README shows the code to create hello.py; the file is not in the repo`

Time taken: 12 minutes. Six candidates, one flagged. That is a good project.

---

## 6. When you cannot find 3 candidates

Spend at most **20 minutes**. When it is up, or when you have exhausted every location in §3.1:

1. Save whatever candidate rows you did produce — 1 or 2 is fine to save.
2. Add **one** row with `command` = `NONE_FOUND` and `confidence` = `na`.
3. In `notes`, choose **exactly one** reason:
   - `NO_COMMANDS_IN_DOCS` — the README documents no way to run it
   - `LIBRARY_ONLY` — it is a library you import, with no runnable entry point and no examples
   - `NEEDS_EXTERNAL_SERVICE` — everything it documents needs a database, server, or API key
   - `NEEDS_GUI` — it wants a graphical window or a browser
   - `DOCS_NOT_IN_ENGLISH` — say which language
   - `OTHER` — write one sentence
4. Move on.

**A correctly-diagnosed `NONE_FOUND` is a real research finding.** Some of these projects genuinely
cannot be run from their own documentation, and counting how many is part of the paper.
`LIBRARY_ONLY` in particular will be common — `toolz` and `chardet` may well be exactly that.

---

## 7. Hard rules

1. **Never record an exit code, a duration, or a claim that something works.** You have not run it.
   There are no columns for these — if you feel you need one, stop and ask.
2. **Copy-paste every command.** Do not retype from memory. A single wrong character makes the row
   useless, and the whole point is that it can be replayed.
3. **Never invent a command from a pattern.** Only what you read or clicked into and confirmed.
4. **Always check whether a referenced file exists.** This is the main thing you add.
5. **Never record a command needing your personal information** — an API key, a password, a token.
   That is `NEEDS_EXTERNAL_SERVICE`.
6. **Never leave a cell blank.** Every column has a valid "unsure" value.
7. **Never skip a row** to come back later. Work top to bottom.
8. **Do not download or install anything.** This is a browser-only job.
9. **Stop at 8 candidates**, even for a project with a huge `examples/` folder. Note the real number.

---

## 8. When something goes wrong

| Situation | What to do |
|---|---|
| The GitHub page says `404` | One row, `command` = `NONE_FOUND`, `notes` = `repo not found`. Tell the coordinator. |
| The repository is marked "archived" | Process it normally. Archived is fine. |
| `examples/` has 40 scripts | List the first 5 alphabetically, note the real number, move on. |
| A command spans several lines with `\` | Copy it as one line, replacing each `\` + newline with a single space. Note that you joined it. |
| The command has a placeholder like `<your-file>` or `FILENAME` | `confidence` = `low`, and note that it needs an input. |
| It is a library with nothing runnable | §6, `LIBRARY_ONLY`. This is a real and common answer. |
| Docs are in a language you cannot read | Still list anything from the `examples/` folder — filenames are usually readable. Then §6 with `DOCS_NOT_IN_ENGLISH`. |
| You cannot tell which `kind` applies | Use `cli_usage` and say so in `notes`. |
| You are tempted to open a terminal and try it | Don't. That is the next stage, and it needs a specific container setup you do not have. |

### The only two reasons to message [[YOUR NAME]] immediately

1. GitHub is unreachable for more than 30 minutes.
2. You cannot access the spreadsheet.

**Everything else goes in `notes` and waits for the daily review.** Mark it, note it, move on. Sitting
and waiting for a reply is the most expensive thing that can happen on this task.

---

## 9. End of every day

Post one message in the group with exactly this format:

```
DAY <n> — <your name>  (ins2 v1.1 Part A)
Projects done: <n>    NONE_FOUND: <n>
Candidates listed: <n>   (high: <n>  medium: <n>  low: <n>)
Files flagged as missing: <n>
Blocked on: <nothing / one line>
```

---

## 10. How your work is measured

Later, someone runs every candidate you listed. That produces the only number that matters here:

1. **Hit rate** — the fraction of your `high`-confidence candidates that actually run. Target:
   **at least 70%.** If your `high` rows are mostly failing, you are marking things `high` that you
   should be marking `medium`.
2. **Coverage** — projects reaching 3+ candidates including one `test_suite`. Target: **12/day.**
3. **Field accuracy** — no blanks, exact spelling, and `file_exists_in_repo` correct. Target: 100%.

You are explicitly **not** measured on:

- **How many candidates turn out to work.** A project where 2 of 6 work is a success. We need the
  shortlist, not a perfect list.
- **How many projects reach 3 candidates.** A correctly-diagnosed `LIBRARY_ONLY` is a finding.

The one thing that would genuinely damage this project is a row implying you ran something you did
not. Nothing else you could do here is difficult to fix.
