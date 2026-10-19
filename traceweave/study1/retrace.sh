#!/usr/bin/env bash
# Trace every finished repo's test suite a second time, into bundles/<repo>/truth.run2.json, so the
# paper can report how stable the observed-call set is between two identical runs. Same image, venv
# and pytest options as batch.py's truth step; the first run's truth.json is never touched.
# Resumable: a repo with truth.run2.json is skipped. Loops while batch.py still has repos to finish.
set -u
H=${TW_HARNESS:-$HOME/traceweave-harness}
D=${TW_DATA:-$HOME/traceweave-data}
CORE=$(cd "$(dirname "$0")/.." && pwd)
IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^tw-study1:')
one() {
  local r=$1 py=$D/study1/venv/$1/bin/python
  [ -d "$D/study1/venv/$1" ] || return 0   # click/toolz: traced on the Mac, no venv here (python links only resolve in the container)
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e TW_TIMEOUT=3000 \
    -e PYTEST_ADDOPTS=--continue-on-collection-errors \
    -v "$H:$H" -v "$D:$D" -v "$CORE:$CORE:ro" "$IMG" bash -c "cd $H && $py -c '
import json, truth
from graph import Bundle
t = truth.build(Bundle(\"$r\"))
open(\"bundles/$r/truth.run2.json\", \"w\").write(json.dumps(t, separators=(\",\", \":\")) + \"\n\")'" \
    && echo "$r: retraced" || echo "$r: retrace FAILED"
}
pass() {
  for f in "$H"/bundles/*/truth.json; do
    r=$(basename "$(dirname "$f")")
    [ -f "$H/bundles/$r/truth.run2.json" ] || one "$r"
  done
}
while pgrep -f '^python3 batch.py' >/dev/null; do pass; sleep 600; done
pass
echo RETRACE_DONE
