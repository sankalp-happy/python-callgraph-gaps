# INSTRUCTIONS 3 (v1.1) — Project Background Checks

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.1** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 3]] |
| **Your input list** | See §1.1 — starts with a fixed list of 14, grows later |

> **This replaces `ins3.md` (v1.0).** If you worked from that document before, read §5 — one whole
> part of it has been deleted and one has been automated. Nothing you already recorded is wasted;
> rows marked `v1.0` stay valid. You just write `v1.1` from now on.

---

## 0. What you are doing

**You need only a web browser. No programming. No terminal. Nothing to install.**

We are collecting open-source Python projects for a research study. We watch each project while it
runs, and record every configuration setting it reads.

Your job is the other half of that: **find every configuration setting the project's documentation
*mentions*.**

The interesting result is the **difference between the two lists.** A setting the code reads but the
documentation never mentions is invisible to anyone trying to modernise that code — and counting how
often that happens is a finding in our paper. So:

- A project where you find **five** settings is a data point.
- A project where you find **none** is *equally* a data point. It is not a wasted 8 minutes.

**You are not judging whether projects are good.** You are recording what is written on web pages.

You have two tasks. **Part 3** (§3) is your main job. **Part 1-R** (§4) is a short list of leftovers
that a script could not finish.

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Qualification check (§2) — about 30 minutes |
| Day 1, rest of day | Part 3 on as many of the 14 starter projects as you get through |
| Day 2 onward | **12 projects per day** (Part 3) |
| When Part 1-R list arrives | Clear it first — it is short, about 30 seconds per row |

A project counts as done when it has **at least one row** in the `env_vars` tab (even if that row
says `NONE_FOUND`) **and** its main-tab row has every column filled.

### 1.1 Your input list

**Start today with these 14.** They are the projects we use to calibrate everything, so they are the
ones we need first:

```
ansible      celery       scrapy       pytest
flask        sqlalchemy   django       requests
click        records      toolz        chardet
black        TheAlgorithms/Python
```

All are at `https://github.com/<owner>/<name>`. If you cannot find one, ask — do not guess at a
similarly-named project.

A much longer list (400–600 projects) is being generated now and will be added to your sheet. Work
the 14 first.

---

## 2. Qualification check — do this first

Do these two projects by yourself using §3. Then compare with the answers below. **Do not read the
answers first.**

| Project | What to do |
|---|---|
| `https://github.com/chardet/chardet` | Full Part 3 procedure |
| `https://github.com/celery/celery` | Full Part 3 procedure |

<details>
<summary><b>Expected answers — open only after you have written yours down</b></summary>

**chardet → one row, `var_name` = `NONE_FOUND`.**

The README contains the text `MODERN_WEB`, which is in capitals with an underscore. It is **not** a
setting. It appears as `EncodingEra.MODERN_WEB` inside a code example — it is a name from the
project's own code, not something you would set from outside. See §3.4, rule 4.

**celery → two rows.**

| var_name | found_in_file | has_example_value | example_value |
|---|---|---|---|
| `TEST_BROKER` | `CONTRIBUTING.rst` | `yes` | `amqp://rabbit:5672` |
| `TEST_BACKEND` | `CONTRIBUTING.rst` | `yes` | `redis://redis` |

</details>

- **Got both right?** Message [[YOUR NAME]] saying "qualification passed" and start on the 14.
- **Got one wrong?** Re-read §3, and message [[YOUR NAME]] saying which one. Do not start real work yet.
- **Think an expected answer is wrong?** Do not change your answer. Message [[YOUR NAME]] with what
  you found. You might be right — that has already happened twice on this project.

---

## 3. PART 3 — Configuration settings mentioned in the documentation

Software often reads settings from things called **environment variables**. They are written in
CAPITAL LETTERS WITH UNDERSCORES, like `DATABASE_URL`, `API_TIMEOUT`, `LOG_LEVEL`, `PORT`.

Your job: for each project, find every such name that is **mentioned in the documentation**, and
record where you found it.

### 3.1 Where to look

Open the project's GitHub page and check each of these, in this order. Some will not exist — skip
those, that is normal.

1. The **README** on the front page
2. `.env.example`, `.env.sample`, or `env.example`
3. `Dockerfile`
4. `docker-compose.yml`
5. **`CONTRIBUTING.md`** or `CONTRIBUTING.rst`  ← *new in v1.1; celery's only settings live here*
6. Any file inside a folder named `docs/`
7. `CONFIGURATION.md` or `config.md`

### 3.2 How to search each one

Use your browser's find function — `Ctrl+F` on Windows/Linux, `Cmd+F` on Mac — and search for these
four things, one at a time:

- `ENV`
- `environment`
- `getenv`
- `export`  ← *new in v1.1; documentation often writes settings as `export NAME=value`*

Then look at the surrounding text for names in `CAPITAL_LETTERS_WITH_UNDERSCORES`.

### 3.3 What to record

For each name you find, add **one row** to the `env_vars` tab:

| Column | What to write |
|---|---|
| `repo` | project short name, e.g. `celery` |
| `var_name` | the name exactly as written, e.g. `DATABASE_URL` |
| `found_in_file` | e.g. `README.md`, `Dockerfile`, `CONTRIBUTING.rst` |
| `has_example_value` | `yes` if a sample value is shown next to it, `no` if only the name appears |
| `example_value` | the sample value if shown, otherwise `-` |
| `recorded_by` / `date` / `sheet_version` | your name / `YYYY-MM-DD` / `v1.1` |

If a project has **no** settings anywhere, add **one** row with `var_name` = `NONE_FOUND`. Never
leave a project with zero rows — we need to know that you checked.

### 3.4 What counts and what does not

**Count it:**

- `DATABASE_URL`, `REDIS_HOST`, `LOG_LEVEL`, `MAX_WORKERS`, `PORT`, `DEBUG`, `SECRET_KEY`
- `TEST_BROKER`, `CI_TIMEOUT` — settings used only for testing still count

**Do not count it:**

1. Anything in lowercase or MixedCase.
2. `PATH`, `HOME`, `USER`, `PWD`, `SHELL`, `LANG`, `TERM` — these belong to the operating system,
   not the project.
3. Anything shorter than 3 characters.
4. **A name with a dot before it.** `EncodingEra.MODERN_WEB`, `settings.DEFAULT_TIMEOUT`,
   `self.MAX_SIZE` — a dot means it is a name from inside the project's own code, not a setting you
   could set from outside. *(New rule in v1.1. This is the single most common mistake — it is what
   the chardet qualification tests.)*
5. **Section headings.** `INSTALLATION`, `USAGE`, `QUICK_START`. If it has no underscore and reads
   like an English word, it is a title.
6. **Names inside a `pip install` or `apt-get` line.** Those are package names.

**Time limit: 8 minutes per project.** If you run out, record what you have and set `part3_status`
= `TIMEBOX` on the main row.

---

## 4. PART 1-R — The licence review list

**Do not go looking for this work. You will be handed a short list.**

A script now reads each project's licence, star count and last-commit date straight from GitHub —
those are three facts published in a form a computer can read exactly. That used to be your Part 1
and it is gone.

**But the script cannot finish about 1 project in 10.** When GitHub cannot identify a licence file,
the script writes `OTHER` or `NONE_FOUND`. For example `celery` comes back `OTHER` when it is really
BSD, because its licence file has an unusual preamble.

**Your job:** for each row on the short list, and only those rows:

1. Open the project's GitHub page.
2. Find the file named `LICENSE`, `LICENSE.txt`, `LICENSE.md`, or `COPYING`.
3. Click it and read the **first five lines**.
4. Correct the `licence` value using this table:

| If you see these words | Write |
|---|---|
| `MIT` | `MIT` |
| `Apache License` or `Apache-2.0` | `Apache` |
| `BSD` (any number of clauses) | `BSD` |
| `GNU General Public License` or `GPL-2.0` or `GPL-3.0` | `GPL` |
| `GNU Lesser General Public License` or `LGPL` | `LGPL` |
| `Mozilla Public License` or `MPL` | `MPL` |
| `The Unlicense` or `Creative Commons Zero` or `CC0` | `PUBLIC_DOMAIN` |
| There is genuinely no licence file at all | `NONE_FOUND` |
| Something not in this list | `OTHER` — and paste the first line into `notes` |

`AGPL` counts as `GPL`. `GPL-3.0-or-later` counts as `GPL`. **Do not create new values.**

Also set `licence_reviewed_by` to your name. About 30 seconds per row.

> **Why this matters:** we publish a research artifact built from these projects. A copyleft licence
> does not disqualify a project, but it has to be *flagged* so the release decision is deliberate
> rather than accidental. A wrong licence is the one error here that could actually cause us a
> problem.

---

## 5. What happened to Part 2 — deleted entirely

**Stop doing this. Do not finish rows in progress.**

Part 2 asked you to search PyPI, GitHub and Google for "a version of this project rewritten in
Python". That question came from an earlier plan where the projects were **Java** and were going to
be translated into Python. Checking whether a translation already existed would have told us the
test was meaningless for that project.

Our projects **are already Python.** Searching for a Python version of a Python project is not a
meaningful question, and the answer cannot affect anything we do.

That was ~6 minutes per project across the largest list we have. It is genuinely just deleted.

The `port_exists` column still exists so nothing in the sheet breaks. A script fills it with
`NA_V11`. **Leave that column alone.**

---

## 6. Your spreadsheet — exact columns

### Main tab (one row per project)

| Column | Allowed values |
|---|---|
| `row_id` | already filled — do not change |
| `repo_url` | already filled — do not change |
| `licence` | **filled by script.** Only you change it, and only on a Part 1-R row |
| `licence_reviewed_by` | your name, if you reviewed it. Otherwise `-` |
| `last_commit_date` | **filled by script** — do not change |
| `stars` | **filled by script** — do not change |
| `port_exists` | **filled by script** as `NA_V11` — do not change |
| `part3_status` | **Exactly one of:** `not_started` `DONE` `TIMEBOX` `NONE_FOUND` |
| `minutes_spent` | whole number |
| `recorded_by` | your name |
| `date` | `YYYY-MM-DD` |
| `sheet_version` | `v1.1` |
| `notes` | `-` if nothing to say |

Use `part3_status` = `NONE_FOUND` when you searched properly and the project documents no settings.
Use `DONE` when you found at least one.

### `env_vars` tab

One row per setting found, columns as listed in §3.3.

**Spelling must be exact.** `Yes`, `yes`, and `YES ` (with a trailing space) are three different
things to a computer, and a computer reads this file. Only the values in these tables are valid.

---

## 7. A fully worked example

Project: `https://github.com/celery/celery`

**§3.1 — checking each location:**

```
README.rst           Ctrl+F "ENV" -> nothing that is a setting
.env.example         does not exist
Dockerfile           does not exist at top level
docker-compose.yml   does not exist at top level
CONTRIBUTING.rst     Ctrl+F "ENV" -> found a block of test settings   <-- hit
docs/                checked docs/configuration.html -> project's own config keys,
                     not environment variables, so not counted
```

**What the hit looked like:**

```
    TEST_BROKER: amqp://rabbit:5672
    TEST_BACKEND: redis://redis
```

Both are capitals-with-underscores, neither has a dot before it, both have a value shown. Two rows.

**The two `env_vars` rows:**

| repo | var_name | found_in_file | has_example_value | example_value |
|---|---|---|---|---|
| celery | `TEST_BROKER` | `CONTRIBUTING.rst` | `yes` | `amqp://rabbit:5672` |
| celery | `TEST_BACKEND` | `CONTRIBUTING.rst` | `yes` | `redis://redis` |

**The main-tab row:** `part3_status` = `DONE`, `minutes_spent` = `6`, `notes` = `-`

---

### The contrasting example — chardet

The README contains this:

```python
for r in detect_all(data, encoding_era=EncodingEra.MODERN_WEB):
```

`MODERN_WEB` is capitals with an underscore, so `Ctrl+F` will land on it. **It does not count** —
there is a dot before it (`EncodingEra.MODERN_WEB`), which means it is a name from inside the
project's own code. §3.4 rule 4.

chardet gets **one** row, `var_name` = `NONE_FOUND`, and `part3_status` = `NONE_FOUND`.

---

## 8. Hard rules

1. **Never leave a cell blank.** If you do not know, there is always a listed value that means "not
   sure" — use it.
2. **Never invent a new value.** Only values from the tables in this document.
3. **Never guess a licence** from the project's name or how well known it is. Read the file.
4. **Never change a column marked "filled by script"** — except `licence`, and only on a Part 1-R row.
5. **Never skip a row** to come back later. Work top to bottom.
6. **Never spend more than 8 minutes** on Part 3 for one project.
7. **Do not download or install anything.** Everything here is done by reading web pages.
8. **Never record a setting you did not actually see.** If you are inferring it from how the project
   probably works, it does not count.

---

## 9. When something goes wrong

| Situation | What to do |
|---|---|
| The GitHub page says `404` | `part3_status` = `NONE_FOUND`, `notes` = `repo not found`, tell the coordinator |
| The repository is marked "archived" | Process it normally. Archived is fine. |
| The README is in a language you cannot read | Check `docs/` and `.env.example` anyway — settings are in capitals either way. If still stuck: `TIMEBOX`, note the language. |
| You cannot tell if something is a setting or a code name | Look for a dot before it. Dot = not a setting. Still unsure → do **not** record it, and write the name in `notes` |
| The project has 40+ settings listed | Record the first 20, set `part3_status` = `TIMEBOX`, note the real number. Do not spend an hour. |
| The same setting appears in three files | One row, and put the **first** file from §3.1's order in `found_in_file` |
| GitHub is slow or down | Wait 10 minutes and try again. Still down → tell the coordinator. |

### The only two reasons to message [[YOUR NAME]] immediately

1. GitHub is unreachable for more than 30 minutes.
2. You cannot access the spreadsheet.

**Everything else goes in `notes` and waits for the daily review.** Mark it, note it, move on.
Stopping to wait for a reply is the most expensive thing that can happen on this task.

---

## 10. End of every day

Post one message in the group with exactly this format:

```
DAY <n> — <your name>  (ins3 v1.1)
Part 3 done: <n>    NONE_FOUND: <n>    TIMEBOX: <n>
Settings recorded: <n>
Part 1-R rows reviewed: <n>
Blocked on: <nothing / one line>
```

---

## 11. How your work is measured

1. **Completeness** — every column filled, every value spelled exactly as listed. Target: **100%.**
   This matters more than speed.
2. **Throughput** — projects per day. Target: **12/day** for Part 3.
3. **Accuracy on the `NONE_FOUND` call** — a sample of your `NONE_FOUND` projects is re-checked. The
   expensive mistake is recording `NONE_FOUND` when settings were there to be found, because nobody
   re-checks a project that reported nothing.

You are **not** measured on how many settings you find. Most of these projects are libraries and
genuinely document very few — on the 14 starter projects we expect **most to come back
`NONE_FOUND`.** That low number is itself the result. Finding nothing, carefully, is the job.
