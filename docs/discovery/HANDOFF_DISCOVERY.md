# HANDOFF — build the candidate queue

### Windows edition (via WSL2). On Linux or macOS instead? Skip §1 and start at §2.

**You have been handed a tarball and pointed at this file. Work through it in order, then send back
what §8 asks for. This file is self-contained — you do not need any prior context.**

Budget: **~45 min of your attention** (most of it in §1, one-time), **~2–4 h of mostly unattended
machine time.**

> **Please read this note before starting.** Every other step in this project was tested on a real
> machine before being written down. **§1 was not** — nobody here has a Windows box to try it on. The
> commands are standard and well documented, but if something contradicts what you see on screen,
> **trust your screen and tell us.** You are not doing it wrong; the instructions are. There are
> verification checkpoints after each step for exactly this reason — please actually run them, so a
> problem surfaces in minute 5 rather than hour 3.

---

## 0. What this is, in 60 seconds

TraceWeave-Core is a 12-week empirical software-engineering project. It measures **how many real
runtime call edges static call-graph analysis misses on Python repositories** — and releases a
benchmark so others can re-measure it.

To measure that we need a corpus of Python repos that actually install and run today. Getting there
has three steps: **discover candidates → triage them → record how to run them.** You are doing step
one.

Your job: produce a **stratified candidate queue** — roughly 450–600 Python repos, each with a frozen
commit SHA and a "dynamic-feature density" score, ordered so the three density bands are interleaved.
Three commands, once you are set up.

### Why this is safe to run on your machine

Nothing you run installs a Python package, resolves a dependency, or writes a lockfile. The only
thing that executes inside a container is a stdlib-only code counter, with networking disabled. So
**nothing you produce can drift or conflict with work on the other machine.** That is deliberate — it
is why this task was scoped to you rather than the full pipeline.

The flip side: **do not run anything not listed in this file.** Specifically, do not run
`triage/triage.sh`. See §9.

---

## 1. Windows setup — WSL2 (one time, ~30 min mostly waiting)

The project is a set of Linux shell scripts and Linux containers. Rather than port them, you run a
real Ubuntu inside Windows. This is Microsoft's own supported path and Docker is built for it.

**You need:** Windows 10 version 2004+ or Windows 11, and virtualization enabled in the BIOS (it
normally is). Admin rights on the machine.

### 1.1 Install WSL2 and Ubuntu

Open **PowerShell as Administrator** (right-click Start → Terminal (Admin)), then:

```
wsl --install -d Ubuntu
```

**Reboot when it tells you to.** After the reboot, an Ubuntu window opens and asks you to create a
username and password. This is a *Linux* account, separate from your Windows login. Pick anything you
will remember — you will need the password for `sudo`.

**Checkpoint** — back in PowerShell:

```
wsl -l -v
```

You must see `Ubuntu` with `VERSION` = **2**. If it says 1, run `wsl --set-version Ubuntu 2` and
wait.

### 1.2 Install Docker Desktop and connect it to Ubuntu

Download Docker Desktop for Windows from docker.com and install it. Then **open it** and:

1. **Settings → General** → tick **"Use the WSL 2 based engine"**
2. **Settings → Resources → WSL Integration** → tick **Ubuntu**
3. **Apply & Restart**

**Docker Desktop must be running on Windows whenever you work.** If you close it, the `docker`
command inside Ubuntu stops working. Leave it open.

### 1.3 From here on, use the Ubuntu terminal — not PowerShell

Open **Ubuntu** from the Start menu. Everything in §2 onwards is typed there.

**Checkpoint** — in the Ubuntu window:

```bash
docker run --rm hello-world
```

You should see a message containing `Hello from Docker!`. If you get `docker: command not found`,
step 1.2 did not take effect — recheck WSL Integration.

### 1.4 ⚠️ Three Windows-specific rules that matter a lot

**1. Keep all files in the Linux home directory. Never under `/mnt/c/`.**

Inside Ubuntu, `/mnt/c/` is your Windows C: drive. It works, but every file access crosses a slow
translation layer, and container mounts from there are slower still. You are about to clone ~600
repositories. On `/mnt/c/` this task takes many hours; in the Linux home directory it takes a
fraction of that.

So: everything lives under `~` (which is `/home/<your-linux-username>`). The commands below already
do this. Just don't "helpfully" move things to your Desktop.

**2. Unpack the tarball *inside* Ubuntu — not with 7-Zip or Explorer.**

§2.1 shows how. Unpacking with Windows tools then copying in can corrupt the scripts (see rule 3) and
lands everything in the slow filesystem.

**3. Never open the project's `.sh` files in Notepad, or any Windows editor that adds `\r`.**

Windows and Linux end lines differently. A Windows-saved shell script fails with a confusing
`bad interpreter: /bin/bash^M`. You have no reason to edit these files at all — but if it happens:

```bash
sed -i 's/\r$//' ~/Projects/major/traceweave/tests/run_checks.sh
```

**On disk:** WSL2 stores its Linux filesystem in a virtual disk on C: that grows as needed. Your
~150 GB of free space on C: is what's available. This task needs well under 20 GB.

---

## 2. Install

### 2.1 Get the tarball into Ubuntu

You were sent `traceweave-handoff.tar.gz`. Say it is in your Windows Downloads folder. In the
**Ubuntu** terminal, replacing `<WindowsUser>` with your Windows username:

```bash
cp "/mnt/c/Users/<WindowsUser>/Downloads/traceweave-handoff.tar.gz" ~/
```

If you are not sure of the path, `ls /mnt/c/Users/` will list the Windows accounts.

### 2.2 Unpack

```bash
mkdir -p ~/Projects && cd ~/Projects && tar xzf ~/traceweave-handoff.tar.gz
```

```bash
mkdir -p ~/traceweave-data/{work,logs,traces,candidates,refrepos}
```

```bash
mv ~/Projects/traceweave-data/out ~/traceweave-data/ 2>/dev/null; mv ~/Projects/traceweave-data/out.amd64-baseline ~/traceweave-data/ 2>/dev/null; rmdir ~/Projects/traceweave-data 2>/dev/null; echo done
```

Restore the executable bits, which archives do not always preserve:

```bash
chmod +x ~/Projects/major/traceweave/scripts/*.py ~/Projects/major/traceweave/scripts/*.sh ~/Projects/major/traceweave/tests/run_checks.sh ~/Projects/major/traceweave/triage/triage.sh
```

### 2.3 Make sure git and python are present

Ubuntu ships both, but confirm — and note the versions for your report:

```bash
git --version; python3 --version
```

If either is missing: `sudo apt update && sudo apt install -y git python3`. **Python must be 3.9 or
newer.** Nothing here needs `pip` — the scripts use only the standard library.

### 2.4 Checkpoint — did the provenance survive the trip?

```bash
wc -l ~/traceweave-data/out/click/py3.12/lock.txt; grep lock_sha256 ~/traceweave-data/out/click/py3.12/result.env
```

Expect exactly **9** lines and exactly:

```
lock_sha256=10dc90ae86e4b711225ac27e2d5b742e1e72915e69451800abd89cac4b946913
```

If either differs, **stop** — the tarball is corrupt or was unpacked with a Windows tool. Say so and
don't continue.

> `~/traceweave-data/out/` is shipped rather than regenerated because it records what the Python
> package index resolved on a specific date. Re-running triage resolves *newer* versions, which
> changes that hash, which changes each repo's identity. **Never delete or "refresh" it.** You will
> not touch it in this task.

---

## 3. Prerequisites — run these and report the output

```bash
docker version --format 'docker server: {{.Server.Version}} arch={{.Server.Arch}}'
```

```bash
git --version; python3 --version; nproc; df -h ~ | tail -1
```

| Need | Minimum | Note |
|---|---|---|
| **Docker**, reachable from Ubuntu | any recent | Docker Desktop must be **open** on Windows. |
| git | any recent | |
| python3 | **3.9+** | |
| free disk | 20 GB | You have far more. Peak usage is only a few GB. |
| cores (`nproc`) | 4+ | Sets `--jobs` in §7. |

**Report the `arch=` value verbatim.** It does not affect this task — the code counter is
architecture-independent — but it decides something later, so we need it recorded now.

---

## 4. Verify the install

```bash
cd ~/Projects/major/traceweave && ./tests/run_checks.sh
```

**Expect `passed: 6   failed: 0`.** What the checks guard:

| # | Checks |
|---|---|
| 1 | The code counter produces **zero** hits on four patterns that fooled an earlier version. |
| 2 | All 9 dynamic features still detected on a known-good test file. |
| 3 | Tiny input is correctly rejected as too small, and a size-normalisation floor holds. |
| 4 | All 5 container images × 2 architectures pinned by exact fingerprint, never by a moving label. |
| 5 | Licence lookup reproduces three known answers (requests→Apache, click→BSD, django→BSD). Needs network. |
| 6 | The container architecture **matches your machine** — i.e. nothing is being silently emulated. |

**If check 6 fails, stop and tell us.** It means Docker would run a foreign-architecture image. That
still *works*, which is the danger: results look correct while timings are meaningless.

If check 6 says `SKIP docker not reachable`, Docker Desktop is closed. Open it and re-run.

### Optional but recommended (~250 MB, a few minutes)

This reproduces the frozen calibration of the counter you are about to run 600 times. Worth doing
once so you know the instrument is sound on your machine:

```bash
cd ~/traceweave-data/refrepos && xargs -P7 -I{} sh -c 'git clone --quiet --depth 1 {} "$(basename {})"' < ~/Projects/major/traceweave/config/reference_repos.txt
```

```bash
cd ~/Projects/major/traceweave && ./tests/run_checks.sh --full
```

**Expect `passed: 7   failed: 0`** and `got: HIGH=6 LOW=3 MED=4 TOO_SMALL=1`.

If the distribution differs, **do not adjust anything** — those thresholds are frozen. Report the
actual numbers. The likely cause is benign: those clones are of *current* upstream code and the
projects have moved since calibration.

---

## 5. Get a GitHub token

The first stage makes ~2–3 API calls per repository. Without a token that is capped at 60 per hour,
which cannot build this list. A token raises it to 5000 per hour.

**Make your own — do not ask for or reuse anyone else's.** On github.com: Settings → Developer
settings → Personal access tokens → **Fine-grained token**. Set it to **read-only, public
repositories, no write scopes.** Nothing here needs write access to anything.

In the Ubuntu terminal:

```bash
export GITHUB_TOKEN=github_pat_your_token_here
```

**This lasts only for the current terminal window.** If you close Ubuntu, run it again. To check it
is still set: `echo ${GITHUB_TOKEN:0:8}` should print the first few characters.

Keep it in the terminal only. **Do not write it into a file in the project** — the repository
deliberately refuses to track `.env` and `*.token` files for this reason. Do not paste it into the
report you send back.

---

## 6. Smoke test first (~3 minutes)

This uses a throwaway folder so it cannot affect the real run.

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py pool --data ~/twsmoke --min-stars 20000 --target 6
```

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py score --data ~/twsmoke --jobs 4
```

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py queue --data ~/twsmoke
```

You should see a search log, then a handful of repos sorted into HIGH/MED/LOW/TOO_SMALL, then a
summary. Many projects at that popularity level are curated link-lists with no Python build file —
they get excluded as `NO_BUILD_FILE`, and that is correct behaviour, not a bug.

If that worked, clear it:

```bash
rm -rf ~/twsmoke
```

**Tell us the smoke test passed before starting §7.** It is a natural place to catch a Windows
problem cheaply.

---

## 7. The real run

Set `--jobs` to about half your core count (from §3). With 8+ cores use `--jobs 8`. It limits
concurrent clones and containers, and it also bounds disk — never more than `--jobs` working copies
exist at once.

**Stage 1 — pool (~45–90 min, network-bound).** Searches, samples, records each project's exact
commit, checks each for a build file and a test suite.

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py pool --target 600
```

**Stage 2 — score (~1–3 h, clone- and container-bound).** Clones each project at that exact commit,
runs the counter inside the pinned container, deletes the clone.

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py score --jobs 8
```

**Stage 3 — queue (seconds).**

```bash
cd ~/Projects/major/traceweave && python3 scripts/discover_candidates.py queue
```

### Practical notes

- **All three stages resume.** If something stops, re-run the same command — completed work is
  skipped. You can stop `score` with `Ctrl+C` at any point; it saves progress every 10 projects and
  cleans up after itself.
- **Keep Docker Desktop open** for the whole of stage 2.
- **Do not let Windows sleep** mid-run. Settings → System → Power → set screen/sleep to Never while
  this runs, or the containers get suspended.
- If you see `403` messages during stage 1, that is GitHub's secondary rate limit. The script sleeps
  and retries on its own. Leave it alone.

---

## 8. What to send back

Everything lands in `~/traceweave-data/candidates/`. Bundle it:

```bash
tar czf ~/candidates-result.tar.gz -C ~/traceweave-data candidates && ls -lh ~/candidates-result.tar.gz
```

Copy it somewhere Windows can see, replacing `<WindowsUser>`:

```bash
cp ~/candidates-result.tar.gz "/mnt/c/Users/<WindowsUser>/Desktop/"
```

Or just run `explorer.exe .` from that folder in Ubuntu and drag the file out.

Send that file, plus these five things:

1. **The §3 prerequisite output**, including the `arch=` line.
2. **The `run_checks.sh` result** — the `passed: N failed: N` line, and the `--full` distribution if
   you ran it.
3. **The full console output of `queue`.** This is the important one. It prints the band counts, a
   prefix-composition table, and a feasibility report. Paste it verbatim.
4. **Rough wall-clock** for `pool` and `score`.
5. **Anything that failed or looked wrong — quoted verbatim, not paraphrased.** Including things you
   worked around, and *especially* anything in §1 that didn't match what you saw. A failure you
   report is worth more than a success you produced.

Do not include your token in any of this.

### The one thing we most want to know

The `queue` output ends with something like:

```
[queue] survival needed to hit MANIFEST §4 floors:
         LOW   ... queued -> floor 10 ...
         MED   ... queued -> floor 12 ...
         HIGH  ... queued -> floor 15 ...
```

**HIGH is the band the whole paper depends on**, and a random sample of GitHub is expected to be much
more LOW-heavy than our hand-picked calibration set was. If HIGH comes out thin, that changes what we
do next. That block matters more than the total count.

---

## 9. Rules that must not be quietly broken

These are not style preferences. Each protects a claim we intend to publish.

1. **Do not run `triage/triage.sh`, and do not start "Phase 1".** Out of scope. It resolves packages
   from the internet and writes files whose contents depend on the date and the CPU architecture, and
   creating those is a decision that has to be made deliberately.
2. **Do not delete or regenerate `~/traceweave-data/out/`.** It is evidence, not output, and it
   cannot be recreated.
3. **Do not edit anything in `traceweave/docs/`, or the pinned versions in `MANIFEST.md` or
   `config/base_images.json`.** Those are frozen. If something appears to conflict with a pin, stop
   and tell us — do not adjust the pin to make it work.
4. **Do not adjust the density thresholds** (`4.0` / `10.0`) even if the distribution looks wrong.
   They were set once, before any of this code existed. That is what makes the result a measurement
   rather than a search.
5. **Do not modify the source of any project the script clones.** Not one character.
6. **Do not "clean up" a project that fails.** Failures are data — they become a published survey. A
   project that drops out silently creates bias in a released benchmark.
7. **Never refer to a container image by label** (`python:3.12-slim`). Everything resolves exact
   fingerprints via `scripts/resolve_image.py`. Labels move; fingerprints do not.

If following this file seems to require breaking one of these, **stop and ask.** That is always the
right call and never a delay we'll mind.

---

## 10. Troubleshooting

### Windows / WSL

| Symptom | Cause and fix |
|---|---|
| `wsl --install` fails, or Ubuntu won't start | Virtualization is off in BIOS, or Windows features are missing. Run `wsl --install` again in an **Admin** PowerShell; if it still fails, enable virtualization in BIOS/UEFI. |
| `docker: command not found` in Ubuntu | §1.2 — WSL Integration not enabled for Ubuntu in Docker Desktop. |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running on Windows. Open it. |
| Check 6 says `SKIP docker not reachable` | Same as above. |
| `bad interpreter: /bin/bash^M` | A script was saved by a Windows editor. `sed -i 's/\r$//' <the-file>` |
| Everything is extremely slow | Your files are on `/mnt/c/`. They must be under `~`. See §1.4 rule 1. Start over from §2.2. |
| `Permission denied` running a script | The `chmod +x` in §2.2 didn't run. Run it again. |
| Ubuntu window closed and `GITHUB_TOKEN` stopped working | Expected — it only lives in that window. §5, run the `export` again. |
| C: filling up | WSL's disk grows as needed. `docker system prune -af` inside Ubuntu, and `rm -rf ~/traceweave-data/work/*`. |
| Run died overnight | Windows slept. §7's practical notes. All stages resume — just re-run. |

### The project itself

| Symptom | Cause and fix |
|---|---|
| Check 5 `FAIL mismatch: requests=NONE_FOUND,...` | A network or certificate problem on the host, **not** a wrong licence mapping. Do not "fix" the mapping. Retry once; if it persists, tell us. |
| `FATAL: GITHUB_TOKEN not set` | §5. |
| Lots of `403` during `pool` | GitHub secondary rate limit. The script sleeps and retries. Leave it. |
| `parse_failures > 0` on some projects | Expected on a few files in very large projects. Recorded per project, not an error. Only worrying if it is high across many — report it if so. |
| `pool` finds fewer than `--target` eligible | It says so at the end. Re-run with `--min-stars 25` or `--max-age-days 1825`, same command otherwise — it resumes and adds. **Tell us what you changed.** |
| A stage dies mid-run | Re-run it. All three resume. |

---

## 11. What this produces, for your own orientation

In `~/traceweave-data/candidates/`:

| File | Contents |
|---|---|
| `01_pool.jsonl` | Every project considered, with its frozen commit, licence, stars, and an `excluded_reason` for those that dropped out |
| `01_pool_meta.json` | How many matched, how many were examined, and the sampling seed |
| `02_scored.jsonl` | The above plus `density_score`, `stratum`, `source_sloc`, `parse_failures` |
| `03_queue.csv` | **The deliverable.** The interleaved queue with `row_id` — opens in Excel |
| `03_queue.jsonl` | Same, machine-readable |
| `03_qc_sample.csv` | A seeded random 10% with the verdict columns blank, for an independent human pass later |
| `discovery_run.json` | Selection criteria, seeds, counts — so the pool is reproducible |

A few notes on reading it:

- **`density_score` is the real quantity**; `stratum` (LOW / MED / HIGH) is just a band for sampling
  balance. A project near a boundary is not meaningfully different from one just across it.
- **A project's own code and its tests are counted separately, and the band comes from its code
  only.** Test suites use dynamic tricks for reasons unrelated to a project's architecture — counting
  them together made every project that uses pytest look HIGH.
- **`TOO_SMALL` means under 500 lines of source**, which makes a project ineligible regardless of how
  well it builds. It stays in the file with a reason rather than being dropped.
- Nothing is ever silently dropped. If a project is not in the queue, `excluded_reason` says why.

---

*Questions on anything in here are welcome and cheap. Guessing is expensive. And if §1 was wrong
anywhere, telling us is a real contribution — you are the first person to run it.*
