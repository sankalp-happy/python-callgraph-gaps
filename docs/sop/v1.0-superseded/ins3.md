# INSTRUCTIONS 3 — Project Background Checks

| | |
|---|---|
| **Your name** | ____________________ |
| **Start date** | ____________________ |
| **Sheet version** | **v1.0** (write this in every row you fill) |
| **Contact** | [[YOUR NAME]] — [[EMAIL / WHATSAPP]] |
| **Your spreadsheet** | [[LINK TO SHEET 3]] |

---

## 0. What you are doing

**You need only a web browser. No programming. No terminal. Nothing to install.**

We are collecting a set of open-source software projects for a research study. Before we can use a project we must check three background facts about it, all of which are found by looking at web pages:

- **Part 1** — Is the project's licence one we are allowed to use?
- **Part 2** — Does a translated copy of this project already exist somewhere public?
- **Part 3** — Which configuration settings does the project's documentation mention?

Part 2 matters most. Our study tests whether a computer program can translate software from one programming language to another. If a translated copy is already published on the internet, our test is meaningless for that project — the answer was already available. Finding these is genuinely important and nobody else on the team is doing it.

**You are not judging whether projects are good.** You are recording facts that are written on web pages.

---

## 1. Your targets

| When | Target |
|---|---|
| Day 1 | Qualification check (Section 2) — takes about 30 minutes |
| Day 1, rest of day | 15 projects, Part 1 + Part 2 |
| Day 2 onward | **30 projects per day**, Part 1 + Part 2 |
| After the Part 1+2 list is finished | Start Part 3 — **12 projects per day** |

A project counts as done when its row has **every column filled in.**

---

## 2. Qualification check — do this first

Do these three by yourself using Section 3. Then compare with the answers below.

| Project | Look up |
|---|---|
| `https://github.com/psf/requests` | licence |
| `https://github.com/pallets/click` | licence |
| `https://github.com/django/django` | licence |

Expected answers: **Apache**, **BSD**, **BSD**.

- Got all three? Message [[YOUR NAME]] saying "qualification passed" and start Part 1.
- Got one wrong? Re-read Section 3 and message [[YOUR NAME]] to say which one. **Do not start real work yet.**
- Think the expected answer is wrong? Do not change your answer — message [[YOUR NAME]] with what you found. You might be right.

---

## 3. PART 1 — The licence check

Every open-source project publishes a licence, which is a document saying how other people are allowed to use it. There are only a handful of common ones and you just need to identify which.

### Steps

1. Open the project's GitHub page.
2. On the front page, look down the **right-hand sidebar** for a section with a small scales-of-justice icon. It usually says something like `Apache-2.0 license` or `MIT license`. **If you see it there, that is your answer — you are done.**
3. If the sidebar shows nothing, look in the file list on the front page for a file named `LICENSE`, `LICENSE.txt`, `LICENSE.md`, or `COPYING`. Click it and read the **first five lines**.
4. Match what you see against this table:

| If you see these words | Write |
|---|---|
| `MIT` | `MIT` |
| `Apache License` or `Apache-2.0` | `Apache` |
| `BSD` (any number of clauses) | `BSD` |
| `GNU General Public License` or `GPL-2.0` or `GPL-3.0` | `GPL` |
| `GNU Lesser General Public License` or `LGPL` | `LGPL` |
| `Mozilla Public License` or `MPL` | `MPL` |
| `The Unlicense` or `Creative Commons Zero` or `CC0` | `PUBLIC_DOMAIN` |
| There is no licence file and nothing in the sidebar | `NONE_FOUND` |
| Something that is not in this list | `OTHER` — and paste the first line into `notes` |

**Note:** `AGPL` counts as `GPL`. `GPL-3.0-or-later` counts as `GPL`. Do not create new values.

### Also record

- `last_commit_date` — On the GitHub front page, above the file list, there is a line showing the most recent change with a time like "3 months ago" or "on 12 Jan 2024". Hover your mouse over it and the exact date appears. Write it as `YYYY-MM-DD`. If you cannot find it, write `unknown`.
- `stars` — the number next to the star icon at the top right of the page. Write it as a plain number: `4200`, not `4.2k`.

---

## 4. PART 2 — The translated-copy search

This is the important one. You are searching for evidence that someone has already published a version of this project rewritten in the Python programming language.

Assume the project is called **Foobar** with URL `https://github.com/someorg/foobar`.

### Search 1 — PyPI

PyPI is the official website where Python software is published.

1. Go to `https://pypi.org`
2. Search for `foobar` (the project's name).
3. Then search these variations, one at a time: `foobar-py`, `pyfoobar`, `python-foobar`
4. Look at the results. For each one that looks like it could be related, click it and read the short description at the top.

### Search 2 — GitHub

1. Go to `https://github.com/search`
2. Search these, one at a time:
   - `foobar python port`
   - `foobar-py`
   - `pyfoobar`
   - `python-foobar`
3. Click the **Repositories** tab on the left.
4. **Only look at results with more than 20 stars.** Ignore everything below that — it saves a lot of time and low-star results are not a real concern.

### Search 3 — Google

Search: `"foobar" python port site:github.com`

Look at the first page only.

### Now decide — use exactly these rules

Read the description of any candidate you found and pick **one**:

| Write | When |
|---|---|
| `YES` | You found something whose own description says it is a **port**, **rewrite**, **reimplementation**, **Python version**, or **Python translation** of this project. The words are right there. |
| `MAYBE` | You found something with a very similar name that seems related, but its description does not clearly say it is a translation of this project. |
| `NO` | You searched all three places and found nothing that looks like a translation. |

**Important distinctions — read these carefully, they are the most common mistakes:**

- A package that lets Python **talk to** the project (a "client", "bindings", "wrapper", "SDK", "connector", "driver", "API for") is **`NO`**. That is not a translation, it is a bridge. This mistake is very common.
- A package that just has a similar name but does something completely unrelated is **`NO`**.
- The project's **own** official Python package (published by the same organisation, doing the same thing in the same language) is **`NO`** — that is just the project itself.
- If you genuinely cannot tell → **`MAYBE`**. That is a real answer and it is fine to use it. Roughly 1 in 10 being `MAYBE` is normal and expected.

### Also record

- `evidence_url` — if you wrote `YES` or `MAYBE`, paste the link to the thing you found. If `NO`, write `-`.
- `searches_done` — write `all3` if you did all three searches. If you stopped early because you found a clear `YES`, write `stopped_early`.

### Time limit

**Maximum 6 minutes per project.** When the 6 minutes are up, write down whatever you have concluded so far and move on. Do not keep digging.

---

## 5. PART 3 — Configuration settings mentioned in the documentation

**Do not start this until [[YOUR NAME]] tells you Part 1 and Part 2 are finished.**

Software often reads settings from something called "environment variables". These have names written in CAPITAL LETTERS WITH UNDERSCORES, like `DATABASE_URL`, `API_TIMEOUT`, `LOG_LEVEL`, `PORT`.

Your job: for each project, find every such name that is **mentioned in the project's documentation**, and record where you found it.

### Steps

1. Open the project's GitHub page.
2. Check each of these locations, in this order. Some will not exist — that is fine, skip them.

   - The README on the front page
   - A file named `.env.example` or `.env.sample` or `env.example`
   - A file named `Dockerfile`
   - A file named `docker-compose.yml`
   - Any file inside a folder named `docs/`
   - A file named `CONFIGURATION.md` or `config.md`

3. In each one, use your browser's find function (`Ctrl+F` on Windows/Linux, `Cmd+F` on Mac) and search for these three things one at a time:
   - `ENV`
   - `environment`
   - `getenv`

4. Look at the surrounding text for names in `CAPITAL_LETTERS_WITH_UNDERSCORES`.

5. For each name you find, add **one row** to the `env_vars` tab with:

| Column | What to write |
|---|---|
| `repo` | project short name |
| `var_name` | the name exactly as written, e.g. `DATABASE_URL` |
| `found_in_file` | e.g. `README.md`, `Dockerfile`, `.env.example` |
| `has_example_value` | `yes` if a sample value is shown next to it, `no` if only the name appears |
| `example_value` | the sample value if shown, otherwise `-` |
| `recorded_by` / `date` / `sheet_version` | as usual |

6. If a project has **no** environment variables anywhere, add **one** row with `var_name` = `NONE_FOUND`. Do not leave the project with zero rows — we need to know you checked.

### What counts and what does not

**Count it:**
- `DATABASE_URL`, `REDIS_HOST`, `LOG_LEVEL`, `MAX_WORKERS`, `PORT`, `DEBUG`, `SECRET_KEY`

**Do not count it:**
- Anything in lowercase or MixedCase
- `PATH`, `HOME`, `USER`, `PWD`, `SHELL`, `LANG`, `TERM` (these belong to the operating system, not the project)
- Anything shorter than 3 characters
- Section headings that happen to be capitalised, like `INSTALLATION` or `USAGE` — those are titles, not settings. If it has no underscore and reads like an English word, it is probably a heading.

**Time limit: 8 minutes per project.** If you run out, record what you have and set `part3_status` = `TIMEBOX` on the main row.

---

## 6. Your spreadsheet — exact columns

### Main tab (Parts 1 and 2)

| Column | Allowed values |
|---|---|
| `row_id` | already filled — do not change |
| `repo_url` | already filled — do not change |
| `licence` | **Exactly one of:** `MIT` `Apache` `BSD` `GPL` `LGPL` `MPL` `PUBLIC_DOMAIN` `NONE_FOUND` `OTHER` |
| `last_commit_date` | `YYYY-MM-DD` or `unknown` |
| `stars` | a plain number |
| `port_exists` | **Exactly one of:** `YES` `MAYBE` `NO` |
| `evidence_url` | a link, or `-` |
| `searches_done` | `all3` or `stopped_early` |
| `minutes_spent` | whole number |
| `part3_status` | `not_started` `DONE` `TIMEBOX` `NONE_FOUND` |
| `recorded_by` | your name |
| `date` | `YYYY-MM-DD` |
| `sheet_version` | `v1.0` |
| `notes` | `-` if nothing to say |

**Spelling must be exact.** `Yes`, `yes`, and `YES ` (with a space at the end) are all wrong — only `YES` is correct. A computer program reads this file and does not forgive typos.

---

## 7. A fully worked example

Project: `https://github.com/apache/kafka`

**Part 1:**
- Sidebar shows `Apache-2.0 license` → `licence` = `Apache`
- Hovered over the last commit line, it said 2026-07-14 → `last_commit_date` = `2026-07-14`
- Star count showed `29.1k` → `stars` = `29100`

**Part 2:**
- PyPI search `kafka` → found `kafka-python`. Clicked it. Description reads *"Pure Python client for Apache Kafka"*. It says **client** → this is a bridge, not a translation → does not count.
- PyPI `kafka-py`, `pykafka`, `python-kafka` → `pykafka` exists, description says *"Kafka client for Python"* → again a client → does not count.
- GitHub `kafka python port` → nothing above 20 stars that claims to be a rewrite.
- Google `"kafka" python port site:github.com` → nothing relevant on page one.

Conclusion: `port_exists` = `NO`, `evidence_url` = `-`, `searches_done` = `all3`

Time taken: 5 minutes.

**The finished row:**

| column | value |
|---|---|
| licence | `Apache` |
| last_commit_date | `2026-07-14` |
| stars | `29100` |
| port_exists | `NO` |
| evidence_url | `-` |
| searches_done | `all3` |
| minutes_spent | `5` |
| part3_status | `not_started` |
| notes | `-` |

Note the key judgement here: two Python packages with "kafka" in the name both existed, and both were still `NO`, because both described themselves as *clients*. Read the description — do not decide based on the name.

---

## 8. Hard rules

1. **Never leave a cell blank.** If you do not know, there is always a listed value that means "not sure" — use it.
2. **Never invent a new value.** Only use values from the tables in this document.
3. **Never guess a licence from the project's name or how well-known it is.** Read the sidebar or the file.
4. **Never mark `YES` because the names are similar.** The description has to actually say port / rewrite / reimplementation / Python version.
5. **Never skip a row** to come back later. Work top to bottom.
6. **Never spend more than 6 minutes** on Part 2 for one project, or 8 on Part 3.
7. **Do not download or install anything.** Everything is done by reading web pages.

---

## 9. When something goes wrong

| Situation | What to do |
|---|---|
| The GitHub page says `404` / does not exist | `licence` = `NONE_FOUND`, `port_exists` = `NO`, `notes` = `repo not found` |
| The repository is marked "archived" | Process it normally. Archived is fine. |
| The sidebar shows a licence you cannot match to the table | `licence` = `OTHER`, paste the exact wording into `notes` |
| The project is not written in Java or Python at all | Process it normally anyway. Someone else decides what to do with it. |
| PyPI or GitHub search is down | Wait 10 minutes and try again. Still down → stop and message [[YOUR NAME]]. |
| You found five possible ports and cannot choose | `MAYBE`, paste the most likely link, move on |
| You are unsure whether something is a "client" or a "port" | `MAYBE`. That is exactly what `MAYBE` is for. |

### The only two reasons to message [[YOUR NAME]] immediately

1. GitHub or PyPI is unreachable for more than 30 minutes.
2. You cannot access the spreadsheet.

**Everything else goes in `notes` and waits for the daily review.** Never sit and wait for a reply — mark it, move on, keep the count going. Stopping to wait is the most costly thing that can happen on this task.

---

## 10. End of every day

Post in the group:

```
DAY <n> — <your name>
Projects done: <n>
Licences: MIT <n> | Apache <n> | BSD <n> | GPL <n> | other <n>
port_exists: YES <n> | MAYBE <n> | NO <n>
Blocked on: <nothing / one line>
```

---

## 11. How your work is measured

1. **Completeness** — percentage of your rows with every column filled and every value spelled exactly as listed. Target: **100%.** This matters more than speed.
2. **Throughput** — projects per day. Target: **30/day for Parts 1+2, 12/day for Part 3.**
3. **Agreement** — about 1 project in 10 is secretly also checked by another person. Your `licence` and `port_exists` should match theirs. Target: **at least 9 out of 10 matching.**

Your `MAYBE` answers are reviewed by [[YOUR NAME]] every evening, so a `MAYBE` costs almost nothing. A wrong `NO` is the expensive mistake, because nobody re-checks a `NO`.

**So: when genuinely torn between `NO` and `MAYBE`, choose `MAYBE`.**
