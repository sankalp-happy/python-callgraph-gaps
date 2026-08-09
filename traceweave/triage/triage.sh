#!/usr/bin/env bash
# triage.sh - v1.2  (TraceWeave-Core)
#
# ONE repository, ONE Python version, one attempt. The recipe ladder (ins1
# Recipes 1-3) and all parallelism live in runner.py -- this script is the atom.
#
# Changes from ins1 v1.0, all from SOP v1.1:
#   A1 (pinning)  : runs against a pinned image DIGEST, not the moving `python:3.12-slim`
#                   tag; emits lock.txt (pip freeze) and records the resolved commit sha.
#   A5 (timing)   : records whole-second wall clock per phase, not "nearest 5".
#   machine-readable: emits result.env as flat KEY=VALUE (no embedded newlines) so
#                   runner.py never has to parse the human log. The human RESULT
#                   block is preserved VERBATIM from v1.0 so that the 10%
#                   human-vs-classifier audit compares like with like.
#
# Changes from v1.1, both verified empirically on this host (2026-08-09):
#   B1 (collect)  : `pytest --collect-only` exits non-zero if ANY module fails to
#                   import, so v1.1 discarded a whole repo for one unimportable
#                   optional extra. psf/black collected 444 of 445 modules in
#                   0.28s, needed `.[d]` for the 445th, and was recorded
#                   COLLECT_FAIL with an EMPTY n_collected and its suite never
#                   run -- though 442 of its tests pass in 30s. v1.2 passes
#                   --continue-on-collection-errors, always records the collected
#                   count, and separates COLLECT_PARTIAL from COLLECT_FAIL.
#   B2 (kills)    : v1.1 discarded the docker exit code and fell back to
#                   `grep -q INSTALL_OK`, which made RED UNREACHABLE once install
#                   succeeded: an OOM kill, the 1800s timeout firing, or a daemon
#                   hiccup all landed as admissible AMBER. v1.2 records docker_rc,
#                   emits a ###SCRIPT_END### sentinel, and classifies a missing
#                   sentinel as TIMEOUT / OOM / KILLED.
#   B3 (oom)      : TESTS_RC=137 is 128+SIGKILL -- the suite was killed, not
#                   failed. v1.1 recorded it as an ordinary AMBER test failure.
#
# Usage: ./triage.sh <github-url> [commit-sha|none] [python-version]
set -uo pipefail

URL="${1:-}"
SHA="${2:-none}"
PYVER="${3:-3.12}"

if [ -z "$URL" ]; then
  echo "USAGE: ./triage.sh <github-url> [commit-sha] [python-version]"
  exit 2
fi

ROOT="${TW_DATA:-$HOME/traceweave-data}"
CONFIG="${TW_CONFIG:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" && pwd)/base_images.json}"

NAME="$(basename "${URL%.git}")"
WORK="$ROOT/work/$NAME"
OUT="$ROOT/out/$NAME/py$PYVER"
LOG="$OUT/attempt.log"
ENVF="$OUT/result.env"
LOCK="$OUT/lock.txt"

mkdir -p "$WORK" "$OUT" "$ROOT/logs"
rm -rf "$WORK"
: > "$LOG"
: > "$ENVF"

# --- A1: resolve the pinned image digest for THIS platform. --------------------
# Never use the floating tag. Platform is auto-detected from the Docker daemon so
# that moving between an x86_64 host and an Apple Silicon host needs no edit.
DETECTED_ARCH="$(docker version --format '{{.Server.Arch}}' 2>/dev/null || echo unknown)"
case "$DETECTED_ARCH" in
  amd64|x86_64) DETECTED_PLATFORM="linux/amd64" ;;
  arm64|aarch64) DETECTED_PLATFORM="linux/arm64" ;;
  *) DETECTED_PLATFORM="unknown" ;;
esac

RESOLVED="$(TW_PLATFORM="${TW_PLATFORM:-}" python3 -c "
import json, os, sys
cfg = json.load(open('$CONFIG'))
img = cfg['images'].get('$PYVER')
if not img:
    sys.exit(0)
want = os.environ.get('TW_PLATFORM') or cfg.get('active_platform', 'auto')
if want == 'auto':
    want = '$DETECTED_PLATFORM'
digest = img.get('digests', {}).get(want)
if not digest:
    sys.exit(0)
print(f\"python@{digest}\t{want}\")
" 2>/dev/null)"

PINNED_REF="${RESOLVED%%$'\t'*}"
PLATFORM="${RESOLVED##*$'\t'}"

if [ -z "$PINNED_REF" ] || [ "$PINNED_REF" = "$RESOLVED" ] && [ -z "$PLATFORM" ]; then
  echo "FATAL: no pinned image for python $PYVER on platform '${TW_PLATFORM:-$DETECTED_PLATFORM}'" | tee -a "$LOG"
  echo "       (detected arch: $DETECTED_ARCH). Check $CONFIG" | tee -a "$LOG"
  echo "status=CONFIG_ERROR" >> "$ENVF"
  exit 3
fi

# Running a foreign-architecture image means qemu emulation. It usually WORKS,
# which is the danger: every wall-clock number becomes meaningless, and tracer
# overhead is a reported metric. Warn loudly and record it in the provenance.
EMULATED=no
if [ "$PLATFORM" != "$DETECTED_PLATFORM" ] && [ "$DETECTED_PLATFORM" != "unknown" ]; then
  EMULATED=yes
  {
    echo "########################################################################"
    echo "# WARNING: EMULATION. image platform=$PLATFORM, host=$DETECTED_PLATFORM"
    echo "# Results are usable for correctness but ALL TIMINGS ARE INVALID."
    echo "# Do not publish overhead numbers from this run. See MANIFEST.md 1.1."
    echo "########################################################################"
  } | tee -a "$LOG"
fi

kv () { printf '%s=%s\n' "$1" "$2" >> "$ENVF"; }

now () { date +%s; }
T_START=$(now)

finish () {
  local result="$1"
  local t_end; t_end=$(now)
  kv "result_line"   "$result"
  kv "seconds_total" "$((t_end - T_START))"
  kv "ended_utc"     "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    echo ""
    echo "----------------------------------------"
    echo "RESULT: $result"
    echo "LOG:    $LOG"
    echo "----------------------------------------"
  } | tee -a "$LOG"
  exit 0
}

# --- ins1 v1.0 classifier, kept VERBATIM for audit comparability --------------
classify_v10 () {
  if grep -qiE "requires python|requires-python|python_requires" "$LOG"; then echo "PYTHON_VERSION"; return; fi
  if grep -qiE "ResolutionImpossible|conflicting dependencies|No matching distribution|Could not find a version|version solving failed" "$LOG"; then echo "DEP_RESOLUTION"; return; fi
  if grep -qiE "fatal error: .*\.h: No such file|gcc. failed|error: command .* failed with exit|unable to execute" "$LOG"; then echo "MISSING_SYSTEM_LIB"; return; fi
  if grep -qiE "Temporary failure in name resolution|Could not resolve host|Network is unreachable|Read timed out|Connection refused" "$LOG"; then echo "NETWORK"; return; fi
  echo "OTHER"
}

# --- v1.1 classifier -----------------------------------------------------------
# v1.0 tests the python_requires pattern FIRST and unconditionally, so any repo
# whose metadata merely *mentions* python_requires is labelled PYTHON_VERSION even
# when the real failure was something else entirely. v1.1 reorders (most specific
# first) and requires the version pattern to co-occur with an actual failure.
# BOTH classifiers are recorded; their disagreement rate is a reportable number,
# not a bug to hide.
classify_v11 () {
  if grep -qiE "Temporary failure in name resolution|Could not resolve host|Network is unreachable|Read timed out|Connection refused" "$LOG"; then echo "NETWORK"; return; fi
  if grep -qiE "fatal error: .*\.h: No such file|gcc. failed|error: command .* failed with exit|unable to execute" "$LOG"; then echo "MISSING_SYSTEM_LIB"; return; fi
  if grep -qiE "ResolutionImpossible|conflicting dependencies|No matching distribution|Could not find a version|version solving failed" "$LOG"; then echo "DEP_RESOLUTION"; return; fi
  if grep -qiE "requires a different python|requires python|Package .* requires a different Python" "$LOG"; then echo "PYTHON_VERSION"; return; fi
  echo "OTHER"
}

kv "sheet_version" "v1.1"
kv "repo_url"      "$URL"
kv "repo_name"     "$NAME"
kv "pyver"         "$PYVER"
kv "pinned_ref"    "$PINNED_REF"
kv "image_digest"  "${PINNED_REF#*@}"
kv "platform"      "$PLATFORM"
kv "host_arch"     "$DETECTED_ARCH"
kv "emulated"      "$EMULATED"
kv "started_utc"   "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kv "log_file"      "$LOG"

echo "=== TRIAGE $URL  sha=$SHA  python=$PYVER  ref=$PINNED_REF ===" >> "$LOG"

# --- clone --------------------------------------------------------------------
echo "[1/4] cloning ..."
T_CLONE=$(now)
if ! git clone --quiet "$URL" "$WORK" >> "$LOG" 2>&1; then
  kv "status" "RED"; kv "error_class_v10" "CLONE"; kv "error_class_v11" "CLONE"
  kv "sha_resolved" "none"
  finish "BUILD_FAIL CLONE"
fi
if [ "$SHA" != "none" ]; then
  git -C "$WORK" checkout --quiet "$SHA" >> "$LOG" 2>&1 || echo "WARN: checkout of $SHA failed" >> "$LOG"
fi

# A1: the sha is mandatory in v1.1. If the sheet gave none, resolve and record it.
SHA_RESOLVED="$(git -C "$WORK" rev-parse HEAD 2>/dev/null || echo unknown)"
kv "sha_requested" "$SHA"
kv "sha_resolved"  "$SHA_RESOLVED"
kv "seconds_clone" "$(( $(now) - T_CLONE ))"

# --- install + test in the pinned container -----------------------------------
echo "[2/4] installing + testing inside $PINNED_REF (can take several minutes) ..."
T_BUILD=$(now)
timeout 1800 docker run --rm \
  -v "$WORK":/repo -w /repo \
  -v "$OUT":/out \
  "$PINNED_REF" bash -c '
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

  # --- A1: freeze the resolved dependency set. THE critical amendment. --------
  # Without this, PyPI resolution drift silently invalidates every later trace and
  # every "same both times" reproducibility claim in ins2.
  python -m pip freeze > /out/lock.txt 2>/dev/null || true
  echo "###LOCK_LINES=$(wc -l < /out/lock.txt)###"
  python -c "import sys;print(\"###PYFULL=%d.%d.%d###\"%sys.version_info[:3])"

  # B1: continue past import errors in individual test modules, and read the
  # count from the pytest summary line rather than from the exit status.
  python -m pytest --collect-only -q --continue-on-collection-errors > /tmp/c.txt 2>&1
  # pytest normally prints "N tests collected", but a repo that deselects by
  # default via addopts prints "N/M tests collected (K deselected)" -- click
  # reports 1965/32965. N is what will actually run and is the number ins2 needs;
  # M is recorded beside it rather than silently substituted for it. Matching the
  # plain form first would capture M out of the middle of the slash form.
  NC=$(grep -oE "[0-9]+/[0-9]+ tests? collected" /tmp/c.txt | tail -1 | grep -oE "^[0-9]+")
  if [ -n "$NC" ]; then
     NT=$(grep -oE "[0-9]+/[0-9]+ tests? collected" /tmp/c.txt | tail -1 \
          | grep -oE "/[0-9]+" | tr -d /)
  else
     NC=$(grep -oE "[0-9]+ tests? collected" /tmp/c.txt | tail -1 | grep -oE "^[0-9]+")
     NT="$NC"
  fi
  CE=$(grep -oE "[0-9]+ errors?" /tmp/c.txt | tail -1 | grep -oE "^[0-9]+")
  echo "###NCOLLECT=${NC:-0}###"
  echo "###NCOLLECT_TOTAL=${NT:-0}###"
  echo "###NCOLLECT_ERRORS=${CE:-0}###"
  if [ "${NC:-0}" -gt 0 ]; then
     if [ "${CE:-0}" -gt 0 ]; then
        # Usable, and the count is known. NOT the same thing as a failed collect.
        echo "###COLLECT_PARTIAL###"; tail -40 /tmp/c.txt
     else
        echo "###COLLECT_OK###"; tail -5 /tmp/c.txt
     fi
  else
     echo "###COLLECT_FAIL###"; tail -40 /tmp/c.txt; echo "###SCRIPT_END###"; exit 1
  fi

  python -m pytest -q --timeout=300 --continue-on-collection-errors > /tmp/t.txt 2>&1
  rc=$?
  tail -30 /tmp/t.txt
  echo "###TESTS_RC=$rc###"
  grep -oE "[0-9]+ (passed|failed|error|errors)" /tmp/t.txt | tail -6 | sed "s/^/###COUNT /; s/$/###/"
  # B2: the sentinel. Its absence means the container died mid-run.
  echo "###SCRIPT_END###"
' >> "$LOG" 2>&1
DOCKER_RC=$?            # B2: v1.1 discarded this, which is how RED became unreachable
kv "docker_rc"     "$DOCKER_RC"
kv "seconds_build" "$(( $(now) - T_BUILD ))"

# --- record pins & telemetry ---------------------------------------------------
echo "[3/4] recording pins ..."
if [ -s "$LOCK" ]; then
  kv "lock_file"    "$LOCK"
  kv "lock_sha256"  "$(sha256sum "$LOCK" | cut -d' ' -f1)"
  kv "lock_pkgs"    "$(wc -l < "$LOCK" | tr -d ' ')"
else
  kv "lock_file" "none"; kv "lock_sha256" "none"; kv "lock_pkgs" "0"
fi
kv "python_full"  "$(grep -oE '###PYFULL=[0-9.]+###' "$LOG" | tail -1 | tr -dc '0-9.' )"
kv "n_collected"  "$(grep -oE '###NCOLLECT=[0-9]+###' "$LOG" | tail -1 | tr -dc '0-9')"
kv "n_collect_errors" "$(grep -oE '###NCOLLECT_ERRORS=[0-9]+###' "$LOG" | tail -1 | tr -dc '0-9')"
kv "n_collected_total" "$(grep -oE '###NCOLLECT_TOTAL=[0-9]+###' "$LOG" | tail -1 | tr -dc '0-9')"
kv "script_completed" "$(grep -q '###SCRIPT_END###' "$LOG" && echo yes || echo no)"

# --- classify ------------------------------------------------------------------
echo "[4/4] classifying ..."
# B2: a container that died after install leaves INSTALL_OK and no sentinel.
# v1.1 read that as COLLECT_FAIL/AMBER, i.e. admissible. It is not.
if grep -q "###INSTALL_OK###" "$LOG" && ! grep -q "###SCRIPT_END###" "$LOG"; then
  case "$DOCKER_RC" in
    124) EC="TIMEOUT" ;;   # `timeout 1800` fired
    137) EC="OOM" ;;       # 128+9 = SIGKILL: the OOM killer
    *)   EC="KILLED" ;;
  esac
  kv "status" "RED"; kv "error_class_v10" "$EC"; kv "error_class_v11" "$EC"
  kv "n_failing" "na"
  finish "BUILD_OK KILLED $EC docker_rc=$DOCKER_RC"
elif grep -qE "###COLLECT_OK###|###COLLECT_PARTIAL###" "$LOG"; then
  PARTIAL=no
  grep -q "###COLLECT_PARTIAL###" "$LOG" && PARTIAL=yes
  kv "collect_partial" "$PARTIAL"
  if grep -q "###TESTS_RC=0###" "$LOG"; then
    kv "status" "GREEN"; kv "error_class_v10" "NONE"; kv "error_class_v11" "NONE"; kv "n_failing" "0"
    [ "$PARTIAL" = yes ] && finish "BUILD_OK TESTS_OK collect_partial"
    finish "BUILD_OK TESTS_OK"
  elif grep -q "###TESTS_RC=137###" "$LOG"; then
    # B3: killed, not failed. Pass counts and timings from this run are invalid.
    kv "status" "RED"; kv "error_class_v10" "OOM"; kv "error_class_v11" "OOM"
    kv "n_failing" "na"
    finish "BUILD_OK TESTS_KILLED OOM"
  elif grep -q "###TESTS_RC=124###" "$LOG"; then
    kv "status" "RED"; kv "error_class_v10" "TIMEOUT"; kv "error_class_v11" "TIMEOUT"
    kv "n_failing" "na"
    finish "BUILD_OK TESTS_KILLED TIMEOUT"
  else
    NF="$(grep -oE '###COUNT [0-9]+ (failed|error|errors)###' "$LOG" | grep -oE '[0-9]+' | head -1)"
    # A2: AMBER is USABLE. H2a needs repos that run, not repos that pass.
    kv "status" "AMBER"; kv "error_class_v10" "NONE"; kv "error_class_v11" "NONE"
    kv "n_failing" "${NF:-unknown}"
    [ "$PARTIAL" = yes ] && finish "BUILD_OK TESTS_FAIL failing=${NF:-unknown} collect_partial"
    finish "BUILD_OK TESTS_FAIL failing=${NF:-unknown}"
  fi
elif grep -q "###COLLECT_FAIL###" "$LOG"; then
  # Zero tests collected. Still AMBER per amendment 2, but it cannot supply an
  # ins2 test_suite workload, so runner.py decides admission separately.
  kv "status" "AMBER"; kv "error_class_v10" "NONE"; kv "error_class_v11" "NONE"
  kv "n_failing" "collect_fail"
  finish "BUILD_OK COLLECT_FAIL"
else
  C10="$(classify_v10)"; C11="$(classify_v11)"
  kv "status" "RED"; kv "error_class_v10" "$C10"; kv "error_class_v11" "$C11"
  kv "n_failing" "na"
  kv "classifier_disagree" "$([ "$C10" = "$C11" ] && echo no || echo yes)"
  finish "BUILD_FAIL $C10"
fi
