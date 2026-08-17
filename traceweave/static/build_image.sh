#!/usr/bin/env bash
# build_image.sh - build the static-extraction image, pinned to THIS platform,
# and record what landed inside it.
#
# Run once per machine, and again after any Dockerfile edit. The provenance file
# it writes is an artifact, not a log: `image_provenance.json` names the base
# digest, the platform, and the resolved pycg / pyright / node versions that
# produced a given S. Without it, "S came from the pinned image" is a claim
# rather than a record.
#
# Usage: ./build_image.sh [--tag traceweave-static:latest] [--python 3.10]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd .. && pwd)"

TAG="traceweave-static:latest"
PYVER="3.10"
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --python) PYVER="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

BASE_IMAGE="$(python3 "$REPO_ROOT/scripts/resolve_image.py" "$PYVER")"
PLATFORM="$(python3 "$REPO_ROOT/scripts/resolve_image.py" "$PYVER" --print-platform)"
if [ -z "$BASE_IMAGE" ]; then
  echo "could not resolve a pinned python:$PYVER base image -- is Docker running?" >&2
  exit 3
fi

echo "building $TAG FROM $BASE_IMAGE ($PLATFORM)"
# --provenance=false --sbom=false: buildx otherwise exports an OCI image INDEX
# with attestation manifests, and `docker image inspect` then exits non-zero on
# the tag even though the image is there -- which reads to every preflight check
# as "the image is not built". A plain single-platform image is also the honest
# artifact here: one image, one platform, one digest to cite.
docker build --provenance=false --sbom=false \
    --build-arg BASE_IMAGE="$BASE_IMAGE" -t "$TAG" .

echo "recording provenance"
INSIDE="$(docker run --rm "$TAG" /provenance.sh)"
python3 - "$TAG" "$BASE_IMAGE" "$PLATFORM" "$INSIDE" <<'PY'
import json, subprocess, sys
tag, base, platform, inside = sys.argv[1:5]
digest = subprocess.run(
    ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
    capture_output=True, text=True).stdout.strip()
payload = {
    "tag": tag,
    "image_id": digest,
    "base_image": base,
    "platform": platform,
    "inside": json.loads(inside),
    "_comment": "Written by build_image.sh. `inside.node` is the one component "
                "the project does not pin (Debian repos); it is recorded so a "
                "rebuild that moves it is visible in the artifact.",
}
with open("image_provenance.json", "w") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
print(json.dumps(payload["inside"], indent=2))
PY

if ! python3 -c "
import json,sys
p=json.load(open('image_provenance.json'))['inside']
bad=[]
if p['pycg'] != '0.0.8': bad.append('pycg='+p['pycg'])
if p['pycg_importable'] != 'yes': bad.append('pycg not importable')
if not p['pyright'].endswith('1.1.411'): bad.append('pyright='+p['pyright'])
print('image check:', 'PASS' if not bad else 'FAIL '+', '.join(bad))
sys.exit(1 if bad else 0)"; then
  exit 1
fi
