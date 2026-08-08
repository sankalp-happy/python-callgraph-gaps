PRIMER — what to know before you start
Read §1 before you touch anything. That's 30 minutes. The rest can wait until you hit it.

Total if you read everything: ~2.5 hours. You do not need to.

1. The 30-minute critical path
1.1 docker run — the only Docker you need
Everything in this project happens as: start a container from a pinned image, mount a folder into it, run one command, throw the container away.

docker run --rm --network=none -v /host/path:/repo:ro python@sha256:55842c... python3 /s/script.py /repo
Flag	What it does	Why it's here
--rm	delete the container when the command exits	nothing persists; state lives on disk outside
-v host:container	bind mount — makes a host folder visible inside	this is how the code being analysed gets in
PRIMER — What to know before you start

Read §1 before you touch anything (about 30 minutes). The whole document is ~2.5 hours — you do not need to read everything up front.

## 1. The 30-minute critical path

### 1.1 docker run — the only Docker you need

Everything in this project runs like this: start a container from a pinned image, mount a folder into it, run one command, throw the container away.

```sh
docker run --rm --network=none -v /host/path:/repo:ro python@sha256:55842c... \
	python3 /s/script.py /repo
```

Flags

| Flag | What it does | Why it's here |
|---|---|---|
| `--rm` | Delete the container when the command exits | Nothing persists; state lives on disk outside |
| `-v host:container` | Bind mount — makes a host folder visible inside | This is how the code being analysed gets in |
| `:ro` | Read-only mount | The scorer must not be able to modify a repo |
| `--network=none` | No network at all inside | The scorer only reads files; this proves it |
| `python@sha256:...` | The image, by digest | See §1.2 |

Mac note: Docker Desktop runs containers inside a Linux VM. Bind-mount I/O is much slower than native, and folders outside your home directory cannot be mounted — keep everything under `$HOME`.

### 1.2 Digest vs tag — the single most important 5 minutes

A tag (e.g. `python:3.12-slim`) is mutable and can point at different images over time. A digest (`python@sha256:...`) is a cryptographic hash of the image contents and is immutable. For reproducibility, always use digests. If you see a tag in a command you were asked to run, report it as a bug.

Search: docker image digest vs tag.

### 1.3 A git SHA, and why it's frozen

A commit SHA (e.g. `00e592c...`) identifies an exact repository state. Branch names move. The pipeline resolves and records each repo's SHA once on list-build day; everything afterwards uses that SHA.

You'll see shallow fetches like:

```sh
git fetch --depth 1 origin <sha>
```

Read: Git Book — "Git Internals — Git Objects".

### 1.4 Environment variables and export

An environment variable is a named value a process inherits from its launcher. Example:

```sh
export GITHUB_TOKEN=ghp_xxxx
```

Four variables you will commonly meet:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Lifts GitHub API rate limit from 60/hr to 5000/hr (effectively mandatory) |
| `TW_DATA` | Where the pipeline writes. Default: `~/traceweave-data`. Override for spot-checking — the default holds records that can't be regenerated. |
| `TW_PLATFORM` | Forces an architecture. Do not set. |
| `SSL_CERT_FILE` | Only needed on some macOS Python installs (see §4.3). |

Gotcha (macOS/zsh): `export` lasts only for that terminal window. `~/.zshrc` is read by interactive shells only; scripts and non-interactive shells read `~/.zshenv`. If something works interactively but fails from a script, check where your environment variables are set.

Read: 12factor.net/config

## 2. Python packaging — 45 minutes (directly relevant)

### 2.1 `pyproject.toml` and `setup.py`

These declare how a Python project installs (name, dependencies, build). `setup.py` is the legacy form; `pyproject.toml` is the modern form. The discovery filter keeps only repos that have one of these files — a repo without them cannot be installed and is excluded as `NO_BUILD_FILE`.

Notes that matter later:

- Extras: `pip install ".[test]"` installs optional test deps. The triage script tries `.[test]`, then `.[dev]`, then plain `.`.
- `requires-python` / `python_requires`: declares supported Python versions. Historical classifier behavior means some repos may be labelled for Python version issues even when not directly relevant.

Read: packaging.python.org — "Writing your pyproject.toml".

### 2.2 Wheels, sdists, and why architecture matters

- A wheel (`.whl`) is a pre-built package. Pure-Python wheels are portable.
- Some wheels include compiled C extensions (e.g. `numpy`, `lxml`, `cryptography`, `pydantic-core`) and are platform-specific.
- An `sdist` is source that may require compilation at install time (and a C compiler).

For projects with compiled dependencies, architecture matters — an Intel build and an Apple Silicon build can resolve different artifacts.

Read: packaging.python.org — "Package Formats".

### 2.3 Lockfiles, resolution drift, and where `uv` fits

Package resolution can drift over time. `pip freeze` captures exact installed versions (e.g. `pytest==9.1.1`). This project saves `lock.txt` and hashes it (`lock_sha256`) so each repo identity is stable.

Tools like `uv` and `pip-tools` provide resolver-accurate cross-platform lockfiles, but this project intentionally uses `pip freeze` and a pinned container digest. Switching the resolver changes `lock_sha256` and invalidates recorded identities — don’t swap the installer without a broader discussion.

Read: docs.astral.sh/uv (background only).

## 3. Background — 45 minutes (why this matters)

You don't need this to run the pipeline, but it helps you notice when something is wrong.

- Call graph: nodes are functions; an edge means "calls". Build via static analysis or runtime tracing.
- Static analysis misses many runtime-dispatched calls in Python (e.g. `handlers[key]()`, `getattr(...)`, `importlib.import_module(...)`). Measuring how many edges are missed is the research goal.
- Density scorer: parses files into ASTs and counts dynamic constructs per 1k lines. High score = many runtime-decided dispatches = interesting repo.

Read: Python `ast` module docs (intro).

Optional: PEP 669 (`sys.monitoring`) is a low-overhead tracing mechanism; it's why Python 3.12 is the default across the project.

## 4. What to expect when you run it

This section saves time and late-night questions.

### 4.1 Normal — do not report these as problems

| You'll see | Why it's fine |
|---|---|
| Many repos excluded as `NO_BUILD_FILE` | Popular repos may be lists or tutorials with no build file; exclusion is correct. |
| `403` messages during the pool stage | GitHub's secondary rate limit — the script retries automatically. |
| `parse_failures > 0` on large repos | A handful of unparseable files in a 100k-line repo is expected and recorded. |
| Repos scored `TOO_SMALL` | Under 500 lines of source; ineligible by design. |
| `AMBER` status | Installed and ran but tests failed — acceptable and useful (tracing still happens). |
| Few repos document environment variables | Measured on reference set: only 1 of 14 had any documented env vars — that is a finding. |
| `nope-xyz` failing with `BUILD_FAIL CLONE` | A deliberate fake URL used to test failure handling. |
| A stage taking longer than expected | Pool is API-bound, scoring is clone-bound. Both resume if interrupted. |

### 4.2 Actually alarming — stop and report

| You'll see | Why it matters |
|---|---|
| Check 6 fails, or an emulation banner | Docker ran a foreign-architecture image; timing measurements become meaningless. |
| `LOG:` path points at `traceweave-data` instead of your folder | Risk of overwriting irreplaceable records. Stop immediately. |
| `lock_pkgs=0` on a repo marked `GREEN` | The environment wasn't captured; that repo is unpinned and must not enter the corpus. |
| The HIGH density band coming out thin | This changes downstream sampling and paper results. |
| Any command using an image tag instead of a digest | Reproducibility bug. |
| A check suite result other than all-passed | Do not work around failing checks; investigate. |

### 4.3 Two macOS-specific failures to know

- `timeout: command not found` — macOS doesn't ship GNU `timeout`. Install via `brew install coreutils` if needed.
- License check shows `NONE_FOUND` — some stock python.org builds have an empty certificate store. The scripts detect and work around this; if it persists: `python3 -m pip install certifi`.

## 5. Project jargon you'll meet

| Term | Meaning |
|---|---|
| `GREEN` / `AMBER` / `RED` | Triage outcomes: installs & passes / installs & runs but tests fail / doesn't build. Both GREEN and AMBER are usable. |
| `stratum` | LOW / MED / HIGH by dynamic-feature density (continuous score is what matters). |
| `TOO_SMALL` | Under 500 source lines — ineligible. |
| the 5-tuple | `(repo_url, sha, pyver, base_image_digest, lockfile_sha256)` — a repo missing any element is excluded from the corpus. |
| `workload` | A recorded, replayable way to run a project (command + exit code, verified twice). |
| `frozen` | A document/threshold that must not be edited to fit results (version bump required to change). |
| `provenance` | Records that are evidence (not re-generable); never deleted or refreshed. |

## 6. The rule behind all the other rules

Every pin, digest, and frozen threshold exists so published numbers are measurements, not the result of searching until something looked good.

Report what actually happened, including failures and workarounds. A well-documented failure is more valuable than an unreported success. If following instructions forces you to break a rule, stop and ask — that's the correct action.

---

If you'd like, I can also: add a short README snippet showing the exact `docker run` and `git fetch` commands to copy, or open a PR with this change. Which would you prefer?