#!/usr/bin/env bash
# run_real.sh - the real-repo counterpart to run_demo.sh.
#
# Same three steps as the toy demo, but against click at its pinned SHA
# instead of a 20-line fixture:
#   1. PyCG over click's 16 analysable modules   -> real_static.json
#   2. click's own test suite under the tracer   -> real_runtime.json
#   3. diff + per-module rollup                  -> real_summary.json
#
# click/testing.py is excluded from BOTH sides. With it, PyCG's behaviour on
# click stops being stable: identical invocations sometimes return a graph
# (and not always the same one -- 1137, 1160 and 1286 nodes were all
# observed) and sometimes exhaust 8GB and are OOM-killed. Without it, all 16
# remaining modules analyse in ~1.5s at ~36MB, every time. Measured by
# scripts/pycg_determinism.py; do not restate this as "PyCG cannot parse
# testing.py", which is a different and unsupported claim.
#
# Tracing a module the static side never saw would also score all of its
# edges as missed for free. The exclusion is recorded in every output file.
#
# PYTHONHASHSEED is PINNED (override with TW_HASH_SEED). PyCG's fixpoint
# iterates over sets, so an unpinned seed makes its output vary run to run --
# leaving it unpinned would mean re-running this script quietly changed the
# headline number. Pinning does not make the number seed-INDEPENDENT, and the
# page says so; it makes this run reproducible, which is the part we control.
#
# This is n=1: one repo, one workload. It is a Phase-2 prototype, not the
# H2a corpus result. See the UI framing on the Live Demo page.
#
# Usage: ./run_real.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd ../.. && pwd)"
LIVE_DIR="$REPO_ROOT/explainer/public/live"
CLICK_REPO="${CLICK_REPO:-$HOME/traceweave-data/refrepos/click}"
EXPECTED_SHA="00e592cea702e0b2caa0dee42489fdb1c22cd845"

if [ ! -d "$CLICK_REPO/src/click" ]; then
  echo "click clone not found at $CLICK_REPO" >&2
  echo "set CLICK_REPO, or clone pallets/click at $EXPECTED_SHA" >&2
  exit 2
fi

SHA="$(git -C "$CLICK_REPO" rev-parse HEAD)"
if [ "$SHA" != "$EXPECTED_SHA" ]; then
  # Not fatal -- but the number must never be quoted against the wrong tree.
  echo "WARNING: click is at $SHA, triage certified $EXPECTED_SHA" >&2
fi

mkdir -p "$LIVE_DIR"
RUN_ID="$(date +%s)"
echo "RUN_ID=$RUN_ID  repo=click  sha=${SHA:0:12}"

echo "[1/3] PyCG over click/src/click (excluding testing.py) -> real_static.json"
docker run --rm \
  -v "$CLICK_REPO:/repo:ro" \
  -v "$LIVE_DIR:/out" \
  --user "$(id -u):$(id -g)" \
  -e RUN_ID="$RUN_ID" \
  -e PYTHONHASHSEED="${TW_HASH_SEED:-0}" \
  -e MODE=package \
  -e PACKAGE=src/click \
  -e SRC_ROOT=src \
  -e EXCLUDE=testing.py \
  -e OUT_NAME=real_static.json \
  traceweave-demo-pycg:latest

echo "[2/3] click's own test suite under sys.setprofile -> real_runtime.json"
# PYTHONPATH, not just the tracer's in-process sys.path insert: a handful of
# click's tests shell out to a fresh interpreter, and those subprocesses
# would otherwise import whatever click is installed system-wide instead of
# the pinned clone (observed: test_path_dash_no_byteswarning failing against
# a site-packages click that the pinned tree has already fixed).
CLICK_REPO="$CLICK_REPO" PYTHONPATH="$CLICK_REPO/src${PYTHONPATH:+:$PYTHONPATH}" \
python3 tracer.py trace-package \
  --src-root "$CLICK_REPO/src" \
  --package "$CLICK_REPO/src/click" \
  --exclude testing.py \
  --workload "$PWD/workloads/click_testsuite.py" \
  --entry main \
  --run-id "$RUN_ID" \
  --out "$LIVE_DIR/real_runtime.json"

echo "[3/3] diff -> real_summary.json"
python3 tracer.py summarize \
  --static "$LIVE_DIR/real_static.json" \
  --runtime "$LIVE_DIR/real_runtime.json" \
  --src-root "$CLICK_REPO/src" \
  --repo click \
  --sha "$SHA" \
  --out "$LIVE_DIR/real_summary.json"

echo "done. RUN_ID=$RUN_ID"
