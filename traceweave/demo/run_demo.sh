#!/usr/bin/env bash
# run_demo.sh - the one-shot command a presenter runs live.
#
# Generates RUN_ID (epoch seconds), runs PyCG against the fixture in Docker
# (-> static.json), then runs the fixture for real under sys.setprofile
# (-> runtime.json). Both files land in explainer/public/live/ with the same
# run_id embedded, atomically written (see Data contract).
#
# Usage: ./run_demo.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd ../.. && pwd)"
LIVE_DIR="$REPO_ROOT/explainer/public/live"
FIXTURE_DIR="$REPO_ROOT/traceweave/demo"

mkdir -p "$LIVE_DIR"
RUN_ID="$(date +%s)"
echo "RUN_ID=$RUN_ID"

echo "[1/2] running PyCG (Docker) -> static.json"
docker run --rm \
  -v "$FIXTURE_DIR:/repo:ro" \
  -v "$LIVE_DIR:/out" \
  --user "$(id -u):$(id -g)" \
  -e RUN_ID="$RUN_ID" \
  traceweave-demo-pycg:latest

echo "[2/2] running the fixture under sys.setprofile -> runtime.json"
python3 "$FIXTURE_DIR/tracer.py" run \
  --fixture "$FIXTURE_DIR/fixture.py" \
  --entry main \
  --run-id "$RUN_ID" \
  --out "$LIVE_DIR/runtime.json"

echo "done. RUN_ID=$RUN_ID"
