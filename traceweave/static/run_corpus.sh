#!/usr/bin/env bash
# run_corpus.sh - static extraction over the whole corpus. THE LONG RUN.
#
# Send this to the x86_64 Linux box and run it there. MIGRATION.md §4: the Mac is
# the manager host, the Linux box is the execution host, and the corpus is amd64.
# A repo extracted on the Mac is development output, not a corpus record.
#
#   ssh <linux-box>
#   cd ~/Project/major/traceweave/static
#   ./build_image.sh                       # once per machine
#   nohup ./run_corpus.sh > ~/static_run.log 2>&1 &
#   tail -f ~/static_run.log
#
# It is SAFE TO INTERRUPT AND RE-RUN. Every repo is checkpointed to
# ~/traceweave-data/static/ledger.jsonl the moment its result is durable, and a
# re-run skips what is finished. A repo where one baseline failed is recorded
# `partial` and IS retried -- a PyCG OOM must never be mistaken for a done repo.
#
# Runtime, honestly: serial by design, roughly 1-6 hours for a 60-repo corpus.
# Pyright is fast (~13 s for click's 2129 call sites). PyCG is the slow and
# memory-hungry half, and 3 seeds means 3 analyses per repo. Serial because each
# PyCG run may want 8 GB and a 38 GB box would start OOM-killing at 5 concurrent
# -- which would produce "PyCG cannot analyse this repo" records that are really
# "we oversubscribed the machine". If wall-clock matters more than simplicity,
# shard by hand: split the queue and run two copies with different --data dirs,
# then merge the ledgers.
#
# Usage:
#   ./run_corpus.sh                        # from triage's ledger (the real thing)
#   ./run_corpus.sh --reference            # the 14 frozen reference repos
#   ./run_corpus.sh --repos-from list.txt  # any `repo_url [sha]` list
#   ./run_corpus.sh --limit 5              # smoke test: first 5 repos
#   ./run_corpus.sh -- --include-tests     # anything after -- goes to extract.py
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 2

DATA="${TW_DATA:-$HOME/traceweave-data}"
IMAGE="${TW_IMAGE:-traceweave-static:latest}"
SEEDS="${TW_SEEDS:-0,1,42}"
# Real on this host, unlike on the Mac's 3.83 GB Docker VM. extract.py warns if
# the daemon cannot actually supply it.
PYCG_MEMORY="${TW_PYCG_MEMORY:-8g}"
MODE="triage"
LIMIT=""
REPOS_FROM=""
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --reference)  MODE="reference"; shift ;;
    --repos-from) MODE="list"; REPOS_FROM="$2"; shift 2 ;;
    --limit)      LIMIT="$2"; shift 2 ;;
    --)           shift; EXTRA=("$@"); break ;;
    *)            echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say () { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$1"; }
die () { printf '%s FATAL: %s\n' "$(date -u +%H:%M:%S)" "$1" >&2; exit 3; }

say "=== preflight ==="

command -v docker >/dev/null 2>&1 || die "docker not on PATH"
docker info >/dev/null 2>&1 || die "docker daemon unreachable. On Docker Desktop
       for Linux it ships as a DISABLED USER unit and presents as a missing
       daemon: systemctl --user start docker-desktop  (MIGRATION.md §4)"

ARCH="$(uname -m)"
say "host arch: $ARCH"
if [ "$ARCH" != "x86_64" ]; then
  say "WARNING: this is not the x86_64 execution host. MIGRATION.md §4 -- the"
  say "         corpus is amd64. Output from here is development, not a corpus"
  say "         record. Continuing in 10s; Ctrl-C to stop."
  sleep 10
fi

# `docker images -q`, not `docker image inspect`: inspect exits non-zero on a tag
# that points at an OCI image index (what buildx exports with attestations), which
# would fail this check on an image that is present and working.
if [ -z "$(docker images -q "$IMAGE" 2>/dev/null)" ]; then
  die "image $IMAGE not built on this machine. Run: ./build_image.sh"
fi
if [ ! -f image_provenance.json ]; then
  die "no image_provenance.json. Run ./build_image.sh so the artifacts can name
       the exact pycg / pyright / node versions that produced them."
fi
python3 -c "
import json,sys
p=json.load(open('image_provenance.json'))
i=p['inside']
print(f\"  image {p['image_id'][:19]}  base {p['base_image'][-19:]}  {p['platform']}\")
print(f\"  inside: python {i['python']}  pycg {i['pycg']}  {i['pyright']}  node {i['node']}\")
bad=[]
if i['pycg']!='0.0.8': bad.append('pycg='+i['pycg'])
if i['pycg_importable']!='yes': bad.append('pycg not importable')
if not i['pyright'].endswith('1.1.411'): bad.append(i['pyright'])
if bad: sys.exit('  image contents wrong: '+', '.join(bad))
" || die "image provenance check failed -- rebuild with ./build_image.sh"

# The fast guards. 39 checks, no docker, seconds. Never start a multi-hour run on
# a broken extractor: every invariant in there, when it broke, silently DELETED
# edges rather than raising, and the run would look like it worked.
say "=== guards (tests/test_static.py) ==="
if ! python3 ../tests/test_static.py | tail -3; then
  die "static extraction guards FAILED. Fix them before spending hours here."
fi

LEDGER="$DATA/triage/ledger.jsonl"
ARGS=(run --data "$DATA" --image "$IMAGE" --seeds "$SEEDS"
      --pycg-memory "$PYCG_MEMORY")

if [ "$MODE" = "reference" ]; then
  say "=== source: the 14 frozen reference repos ==="
  ARGS+=(--repos-from ../config/reference_repos.txt)
  [ -d "$DATA/refrepos" ] && ARGS+=(--clone-dir "$DATA/refrepos")
elif [ "$MODE" = "list" ]; then
  [ -f "$REPOS_FROM" ] || die "no such repo list: $REPOS_FROM"
  say "=== source: $REPOS_FROM ==="
  ARGS+=(--repos-from "$REPOS_FROM")
  [ -d "$DATA/refrepos" ] && ARGS+=(--clone-dir "$DATA/refrepos")
else
  say "=== source: triage ledger ==="
  [ -f "$LEDGER" ] || die "no triage ledger at $LEDGER.
       Static extraction consumes triage's output. Run the triage queue first:
         cd ../triage && nohup python3 runner.py run \\
             --queue ../../candidates/03_queue.csv --jobs 4 > ~/triage_run.log 2>&1 &
       That is ~100 worker-hours over 558 repos and is also resumable."
  python3 - "$LEDGER" <<'PY' || die "could not read the triage ledger"
import json, sys, collections
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
latest = {r["repo_url"]: r for r in rows}
admit = [r for r in latest.values() if r.get("admit") == "yes"]
gate = collections.Counter(r.get("corpus_eligible", "yes") for r in admit)
print(f"  {len(latest)} repos triaged, {len(admit)} admissible")
print(f"  redistribution gate (MANIFEST §7): {dict(gate)}")
print(f"  extracting: {gate['yes'] + gate['pending']} "
      f"(eligible + pending licence review; --include-survey-only widens this)")
PY
  ARGS+=(--from-triage "$LEDGER")
fi

[ -n "$LIMIT" ] && ARGS+=(--limit "$LIMIT")
[ ${#EXTRA[@]} -gt 0 ] && ARGS+=("${EXTRA[@]}")

say "=== extracting ==="
say "extract.py ${ARGS[*]}"
START=$(date +%s)
python3 extract.py "${ARGS[@]}"
RC=$?
ELAPSED=$(( $(date +%s) - START ))
say "extraction finished rc=$RC after $((ELAPSED / 60))m$((ELAPSED % 60))s"

say "=== report ==="
python3 extract.py report --data "$DATA"

say ""
say "Artifacts:  $DATA/static/"
say "Ledger:     $DATA/static/ledger.jsonl"
say "Re-run this script to pick up anything recorded 'partial' or not yet done."
exit $RC
