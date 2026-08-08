#!/usr/bin/env bash
# workload_shell.sh - v1.1  (TraceWeave-Core)
#
# Opens a container for recording workloads (ins2), using EXACTLY the environment
# that triage certified: the same pinned image digest and the same frozen
# dependency lockfile.
#
# Why this replaces ins2 v1.0 Step 3's hand-typed install block: if workload
# capture resolves its own dependencies from PyPI, then triage, workload capture
# and tracing each run a DIFFERENT dependency set, and the whole point of pinning
# is lost. Every workload must be recorded against the environment it will later
# be traced in.
#
# Usage:
#   ./workload_shell.sh <repo-name> [pyver]
#
# Then, inside the container, follow ins2 §4: run each candidate command, and type
#   echo $?
# after every one.
set -uo pipefail

NAME="${1:-}"
PYVER="${2:-}"
ROOT="${TW_DATA:-$HOME/traceweave-data}"

if [ -z "$NAME" ]; then
  echo "USAGE: ./workload_shell.sh <repo-name> [pyver]"
  echo ""
  echo "Repos that have been triaged:"
  ls -1 "$ROOT/out" 2>/dev/null | sed 's/^/  /'
  exit 2
fi

# If no pyver given, pick the one triage actually succeeded on.
if [ -z "$PYVER" ]; then
  for cand in "$ROOT/out/$NAME"/py*/result.env; do
    [ -f "$cand" ] || continue
    st="$(grep -m1 '^status=' "$cand" | cut -d= -f2)"
    case "$st" in
      GREEN|AMBER) PYVER="$(basename "$(dirname "$cand")")"; PYVER="${PYVER#py}"; break ;;
    esac
  done
fi

if [ -z "$PYVER" ]; then
  echo "ERROR: no GREEN or AMBER triage attempt found for '$NAME'."
  echo "       (Reminder: AMBER counts. A repo whose tests fail still RUNS, and"
  echo "        running is what we need. See SOP v1.1 amendment 2.)"
  exit 3
fi

OUT="$ROOT/out/$NAME/py$PYVER"
WORK="$ROOT/work/$NAME"
ENVF="$OUT/result.env"

if [ ! -f "$ENVF" ]; then
  echo "ERROR: no triage record at $ENVF"
  exit 3
fi

get () { grep -m1 "^$1=" "$ENVF" | cut -d= -f2-; }
PINNED_REF="$(get pinned_ref)"
LOCK_SHA="$(get lock_sha256)"
STATUS="$(get status)"

if [ ! -d "$WORK" ]; then
  echo "Working copy missing; re-cloning $NAME ..."
  URL="$(get repo_url)"; SHA="$(get sha_resolved)"
  git clone --quiet "$URL" "$WORK" || { echo "clone failed"; exit 4; }
  [ -n "$SHA" ] && [ "$SHA" != unknown ] && git -C "$WORK" checkout --quiet "$SHA"
fi

cat <<INFO
------------------------------------------------------------------
 repo            : $NAME   (triage status: $STATUS)
 python          : $PYVER
 image           : $PINNED_REF
 lock_sha256     : $LOCK_SHA
 workdir         : /repo        (mounted read-write)
 lockfile        : /out/lock.txt
------------------------------------------------------------------
 Record these THREE values in every workload YAML you write:
   pyver:              $PYVER
   base_image_digest:  ${PINNED_REF#*@}
   lock_sha256:        $LOCK_SHA
------------------------------------------------------------------
Installing from the frozen lockfile, then dropping you at a shell.
INFO

exec docker run -it --rm \
  -v "$WORK":/repo -w /repo \
  -v "$OUT":/out:ro \
  "$PINNED_REF" bash -c '
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq git build-essential >/dev/null 2>&1
  python -m pip install -q --upgrade pip setuptools wheel >/dev/null 2>&1
  if [ -s /out/lock.txt ]; then
    echo "installing from frozen lockfile ($(wc -l < /out/lock.txt) packages) ..."
    python -m pip install -q --no-deps -r /out/lock.txt 2>&1 | tail -5
  else
    echo "WARNING: no lockfile; falling back to a fresh install (record this in notes)"
    python -m pip install -q . 2>&1 | tail -3
  fi
  python -m pip install -q pytest pytest-timeout >/dev/null 2>&1
  echo ""
  echo "Ready. Working dir is /repo. Remember: echo \$? after every command."
  exec bash
'
