#!/usr/bin/env bash
# build_image.sh - build the demo's PyCG image, pinned to THIS platform.
#
# Resolves the base image digest via scripts/resolve_image.py rather than
# hardcoding one in the Dockerfile -- the amd64 pin would silently emulate
# under QEMU on an arm64 Mac (see resolve_image.py, run_checks.sh check 6).
#
# Usage: ./build_image.sh   (run once per machine, or after a Dockerfile edit)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd .. && pwd)"

BASE_IMAGE="$(python3 "$REPO_ROOT/scripts/resolve_image.py" 3.10)"
if [ -z "$BASE_IMAGE" ]; then
  echo "could not resolve a pinned python:3.10 base image -- is Docker running?" >&2
  exit 3
fi

echo "building traceweave-demo-pycg:latest FROM $BASE_IMAGE"
docker build --build-arg BASE_IMAGE="$BASE_IMAGE" -t traceweave-demo-pycg:latest .
