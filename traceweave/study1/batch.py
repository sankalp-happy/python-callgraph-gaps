#!/usr/bin/env python3
"""Study 1 at corpus scale: every repo in repos.tsv, end to end, unattended.

Per repo, in order, each step skipped once its output exists:

  clone   the pinned sha into <harness>/work/<repo>           harness sandbox.fetch, host git
  repo    <harness>/bundles/<repo>/repo.json                  src_root/package from static summary.json
  env     a venv holding triage's frozen lock.txt             <data>/study1/venv/<repo>
  trace   demo/tracer.py trace-package, the repo's own suite  bundles/<repo>/trace.json
  bundle  build_bundle.py                                     bundles/<repo>/graph.json
  truth   tw.py truth                                         bundles/<repo>/truth.json
  bench   tw.py bench (also freezes the LLM sample,           <data>/study1/bench/<repo>.txt
          results/resolve/<repo>.sample.json)

env..bench run in the pinned python:3.12 image triage used (config/base_images.json) plus git and a
compiler. Host paths are mounted at the same absolute paths inside, so the venv and the editable
install stay valid from one container to the next.

A failed step goes in <data>/study1/ledger.jsonl and that repo is SKIPPED on later runs until it is
named with --retry: a repo that failed once will usually fail the same way, and a blind retry burns
an hour. Read its log (<data>/study1/logs/<repo>.log) first. Delete a step's output to redo it.

    python3 batch.py run                       # all of repos.tsv; Ctrl-C and re-run to resume
    python3 batch.py run --only creosote
    python3 batch.py run --retry sqllineage
    python3 batch.py status

The Mac is not the corpus host (MANIFEST §1). --dev allows a throwaway run there, into a harness
COPY, falling back to triage's install recipe because the locks live on the Linux box.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent                                    # traceweave/
TRACER = CORE / "demo" / "tracer.py"
WORKLOAD = CORE / "dypybench" / "pytest_workload.py"
TESTS_DIRS = ("tests", "test", "testing", "t")        # top level first, then inside the package
STEPS = ("clone", "repo", "env", "trace", "bundle", "truth", "bench")
TIMEOUT = {"env": 1800, "trace": 3600, "bundle": 900, "truth": 7200, "bench": 1800}
SUITE_TIMEOUT = 3000                                  # sandbox.run_tests, per suite run (default 600)

# Same recipe as triage.sh, for --dev only: on the corpus host the frozen lock is the environment.
RECIPE = """
if   [ -f pyproject.toml ]; then pip install ".[test]" || pip install ".[dev]" || pip install .
elif [ -f setup.py ]; then pip install .
fi
for r in requirements.txt requirements-dev.txt dev-requirements.txt test-requirements.txt requirements/dev.txt requirements/test.txt; do
  if [ -f "$r" ]; then pip install -r "$r"; fi
done
pip install pytest pytest-timeout
"""


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sh(*parts) -> str:
    return " ".join(shlex.quote(str(p)) for p in parts)


class Run:
    def __init__(self, args):
        self.harness, self.static, self.data = (Path(p).expanduser().resolve()
                                                for p in (args.harness, args.static, args.data))
        self.out = self.data / "study1"
        self.ledger = self.out / "ledger.jsonl"
        self.dev = args.dev
        self.fresh_env = args.fresh_env
        sys.path.insert(0, str(self.harness))

    def last(self) -> dict:
        out = {}
        if self.ledger.exists():
            for line in self.ledger.read_text().splitlines():
                r = json.loads(line)
                out[r["repo"]] = r
        return out

    def record(self, **row) -> None:
        with self.ledger.open("a") as fh:
            fh.write(json.dumps({"utc": utc(), "host_arch": platform.machine(), "dev": self.dev, **row}) + "\n")

    def image(self) -> str:
        """The pinned 3.12 base for this platform plus git (the harness resets with it) and a compiler."""
        arch = subprocess.run(["docker", "version", "--format", "{{.Server.Arch}}"],
                              capture_output=True, text=True).stdout.strip()
        plat = {"amd64": "linux/amd64", "x86_64": "linux/amd64",
                "arm64": "linux/arm64", "aarch64": "linux/arm64"}.get(arch)
        if plat is None:
            raise SystemExit(f"docker not reachable (server arch {arch!r})")
        if plat != "linux/amd64" and not self.dev:
            raise SystemExit(f"docker is {plat}: corpus records come only from the amd64 host "
                             "(MANIFEST §1). --dev for a throwaway run.")
        digest = json.loads((CORE / "config" / "base_images.json").read_text())["images"]["3.12"]["digests"][plat]
        tag = f"tw-study1:py312-{digest[7:19]}"
        if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode:
            dockerfile = (f"FROM python@{digest}\nRUN apt-get update -qq && apt-get install -y -qq "
                          "--no-install-recommends git build-essential && rm -rf /var/lib/apt/lists/*\n")
            subprocess.run(["docker", "build", "-t", tag, "-"], input=dockerfile, text=True, check=True)
        return tag

    def docker(self, repo: str, step: str, script: str, log) -> int | str:
        name = f"tw-s1-{repo}-{step}".lower()
        mounts = [f"{self.harness}:{self.harness}", f"{self.data}:{self.data}",
                  f"{CORE}:{CORE}:ro", f"{self.static}:{self.static}:ro"]
        cmd = ["docker", "run", "--rm", "--name", name, "--user", f"{os.getuid()}:{os.getgid()}",
               "-e", "HOME=/tmp", "-e", f"PIP_CACHE_DIR={self.out / 'pip-cache'}",
               # triage counted these suites with their broken test modules (tests_failing_triage);
               # without this one unimportable module stops the whole run, so nothing is traced
               "-e", "PYTEST_ADDOPTS=--continue-on-collection-errors",
               *[a for m in mounts for a in ("-v", m)], self.tag, "bash", "-c", "set -euxo pipefail\n" + script]
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)   # left over from a killed run
        try:
            return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT[step]).returncode
        except subprocess.TimeoutExpired:
            return f"timeout after {TIMEOUT[step]} s"
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    # ------------------------------------------------------------------ one repo

    def repo(self, row: dict, log) -> tuple[str, object] | None:
        """Runs the missing steps. None when all are done, else (failed step, why)."""
        import sandbox
        name = row["repo"]
        bundle = self.harness / "bundles" / name
        venv = self.out / "venv" / name
        summary = json.loads((self.static / name / "summary.json").read_text())
        if summary["clone"]["sha_resolved"] != row["sha"]:
            return "repo", f"static summary is for {summary['clone']['sha_resolved'][:12]}, repos.tsv pins {row['sha'][:12]}"
        repo = {"name": name, "url": row["url"], "sha": row["sha"]}
        checkout = sandbox.root(repo)
        src_root = checkout / summary["src_root"]
        done = {
            "repo": (bundle / "repo.json").exists(),
            "env": (venv / "tw-env.json").exists(),
            "trace": (bundle / "trace.json").exists(),
            "bundle": (bundle / "graph.json").exists(),
            "truth": (bundle / "truth.json").exists(),
            "bench": (self.out / "bench" / f"{name}.txt").exists(),
        }
        py = venv / "bin" / "python"
        for step in STEPS:
            if done.get(step):
                continue
            print(f"  {step} ...", flush=True)
            log.write(f"\n===== {utc()} {name} {step}\n")
            log.flush()
            t0 = time.monotonic()
            if step == "clone":
                try:
                    sandbox.fetch(repo)
                except subprocess.CalledProcessError as exc:
                    log.write(f"{exc.stderr}\n")
                    shutil.rmtree(checkout, ignore_errors=True)   # a half clone would pass as done
                    return step, "clone failed"
                except SystemExit as exc:                         # checkout at another sha
                    return step, str(exc)
                continue
            if step == "repo":
                package = summary["packages"][0]
                tests = next((t for t in (*TESTS_DIRS, *(f"{package}/{d}" for d in TESTS_DIRS))
                              if (checkout / t).is_dir()), None)
                # No fallback to the package dir for Google-style foo_test.py files: the harness treats the
                # tests path as test code, so the whole package drops out (recurrentgemma, 0 nodes).
                if tests is None:
                    return step, "no tests directory found"
                bundle.mkdir(parents=True, exist_ok=True)
                (bundle / "repo.json").write_text(json.dumps(repo | {
                    "licence": row["licence"], "src_root": summary["src_root"], "package": package,
                    "tests": tests, "about": f"TraceWeave corpus {summary['row_id']}, {row['stratum']} stratum",
                }, indent=2) + "\n")
                continue
            meta = json.loads((bundle / "repo.json").read_text())
            if step == "env":
                lock = self.data / "out" / name / "py3.12" / "lock.txt"
                if lock.exists():
                    got = hashlib.sha256(lock.read_bytes()).hexdigest()
                    if got != row["lock_sha256"]:
                        return step, f"{lock} sha256 {got[:12]} is not triage's {row['lock_sha256'][:12]}"
                    # triage pip-installed the repo itself (`pkg @ file:///repo`); it comes from the checkout here
                    install, source = (f"grep -v -e ' @ file://' -e '^-e ' {sh(lock)} > {sh(venv / 'lock.txt')}\n"
                                       f"pip install -r {sh(venv / 'lock.txt')}"), "lock"
                elif self.dev or self.fresh_env:
                    install, source = RECIPE + f"pip freeze > {sh(venv / 'lock.txt')}", "recipe"
                else:
                    return step, f"no triage lock at {lock}: the environment would not be triage's"
                rc = self.docker(name, step, f"""
                    rm -rf {sh(venv)} && python -m venv {sh(venv)} && . {sh(venv / 'bin/activate')}
                    pip install -q --upgrade pip setuptools wheel
                    cd {sh(checkout)}
                    {install}
                    # editable, so import metadata and generated _version.py files exist; imports stay on the checkout
                    pip install --no-deps -e . && editable=true || editable=false
                    printf '{{"source": "{source}", "editable": %s, "python": "%s"}}\\n' $editable \
                        "$(python -c 'import platform; print(platform.python_version())')" > {sh(venv / 'tw-env.json')}
                """, log)
            elif step == "trace":
                rc = self.docker(name, step, f"""
                    cd {sh(checkout)}
                    TW_PYTEST_ARGS={sh(meta['tests'])} PYTHONPATH={sh(src_root)} {sh(py)} {sh(TRACER)} trace-package \
                        --src-root {sh(src_root)} --package {sh(checkout / meta['package'])} --exclude "" \
                        --workload {sh(WORKLOAD)} --entry entry --run-id {sh(f'{name}-{utc()}')} \
                        --out {sh(bundle / 'trace.json')}
                """, log)
                if rc == 0:
                    edges = json.loads((bundle / "trace.json").read_text())["edges"]
                    if not any(e["caller"] != "<entry>" for e in edges):
                        (bundle / "trace.json").unlink()
                        return step, "no internal edges: the package was not imported from the checkout"
            elif step == "bundle":
                rc = self.docker(name, step, f"""
                    cd {sh(self.harness)}
                    {sh(py)} build_bundle.py {sh(name)} --static {sh(self.static / name)} --runtime {sh(bundle / 'trace.json')}
                """, log)
            elif step == "truth":
                rc = self.docker(name, step, f"""
                    cd {sh(self.harness)}
                    TW_TIMEOUT={SUITE_TIMEOUT} {sh(py)} tw.py truth {sh(name)}
                """, log)
            elif step == "bench":
                out = self.out / "bench" / f"{name}.txt"
                out.parent.mkdir(parents=True, exist_ok=True)
                rc = self.docker(name, step, f"""
                    cd {sh(self.harness)}
                    {sh(py)} tw.py bench {sh(name)} > {sh(out)}.tmp
                    mv {sh(out)}.tmp {sh(out)} && cat {sh(out)}
                """, log)
            log.write(f"===== {step} rc={rc} in {time.monotonic() - t0:.0f} s\n")
            log.flush()
            if rc != 0:
                return step, rc
        return None


def cmd_run(args) -> int:
    run = Run(args)
    if run.dev and (run.harness / ".git").exists():
        raise SystemExit(f"--dev refuses {run.harness}: it is the real harness, and dev bundles there would "
                         "be copied to the corpus host and skipped as done. Use a copy without .git.")
    rows = [r for r in csv.DictReader((l for l in (HERE / "repos.tsv").open() if not l.startswith("#")),
                                      delimiter="\t") if not args.only or r["repo"] in args.only]
    if args.only and len(rows) != len(args.only):
        raise SystemExit(f"not in repos.tsv: {sorted(set(args.only) - {r['repo'] for r in rows})}")
    run.tag = run.image()
    image_id = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", run.tag],
                              capture_output=True, text=True).stdout.strip()
    (run.out / "logs").mkdir(parents=True, exist_ok=True)
    failed = 0
    for row in rows:
        name, prev = row["repo"], run.last().get(row["repo"], {})
        if prev.get("status") == "failed" and name not in (args.retry or []):
            print(f"{name}: skipped, failed at {prev['step']} ({prev['why']}); see logs/{name}.log, then --retry {name}")
            failed += 1
            continue
        print(f"{name} ({row['stratum']})", flush=True)
        t0 = time.monotonic()
        with (run.out / "logs" / f"{name}.log").open("a") as log:
            try:
                result = run.repo(row, log)
            except Exception as exc:          # one repo's surprise must not stop the other 19
                log.write(f"\n{type(exc).__name__}: {exc}\n")
                result = "batch.py", f"{type(exc).__name__}: {exc}"
        common = {"repo": name, "stratum": row["stratum"], "image": run.tag, "image_id": image_id,
                  "seconds": round(time.monotonic() - t0)}
        if result:
            step, why = result
            print(f"  FAILED at {step}: {why}")
            run.record(status="failed", step=step, why=str(why), **common)
            failed += 1
        elif prev.get("status") != "done":
            env = json.loads((run.out / "venv" / name / "tw-env.json").read_text())
            run.record(status="done", step="bench", why="", env=env, **common)
            print("  done")
    print(f"\n{len(rows) - failed} of {len(rows)} done. {run.ledger}")
    return 1 if failed else 0


def cmd_status(args) -> int:
    last = Run(args).last()
    for r in csv.DictReader((l for l in (HERE / "repos.tsv").open() if not l.startswith("#")), delimiter="\t"):
        p = last.get(r["repo"], {})
        print(f"{r['repo']:30s} {r['stratum']:5s} {p.get('status', 'pending'):8s} "
              f"{p.get('step', '') if p.get('status') == 'failed' else '':7s} {p.get('why', '')[:70]}")
    return 0


def main() -> int:
    data = Path(os.environ.get("TW_DATA", Path.home() / "traceweave-data"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", default=os.environ.get("TW_HARNESS", Path.home() / "traceweave-harness"))
    ap.add_argument("--data", default=data, help="triage's out/<repo>/py3.12/lock.txt is read here, study1/ written")
    ap.add_argument("--static", default=data / "static", help="extract.py output, one dir per repo")
    ap.add_argument("--dev", action="store_true", help="allow a non-amd64 throwaway run; never corpus data")
    ap.add_argument("--fresh-env", action="store_true",
                    help="amd64 host without triage's locks: install by triage's recipe instead; each repo's "
                         "tw-env.json and ledger row record source=recipe, so the paper can disclose it")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--only", nargs="+")
    p.add_argument("--retry", nargs="+", help="re-run these repos even though they failed before")
    p.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
