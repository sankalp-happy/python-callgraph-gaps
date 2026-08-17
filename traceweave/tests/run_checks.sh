#!/usr/bin/env bash
# run_checks.sh - TraceWeave-Core health checks
#
# Closes the durability gap noted in README §11: these guards previously read
# fixtures from /tmp, so they vanished between sessions. Fixtures now live in
# tests/fixtures/ and travel with the repo.
#
# Usage:
#   ./tests/run_checks.sh            # fast checks only (no network, no docker)
#   ./tests/run_checks.sh --full     # also re-runs the 14-repo calibration sweep
set -uo pipefail

# Capture the flag now: check 4 uses `set -- $res` to split its result into
# positionals, which clobbers $1. Testing "$1" at check 7 therefore never matched
# and --full was silently a no-op.
FULL=0
[ "${1:-}" = "--full" ] && FULL=1

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
REPO="$PWD"
FIX="$REPO/tests/fixtures"
PASS=0; FAIL=0
# Resolve the image for THIS platform. Never hardcode a digest: the amd64 pin
# would silently emulate on an arm64 host and invalidate every timing.
IMG="$(python3 "$REPO/scripts/resolve_image.py" 3.12 2>/dev/null)"
PLATFORM="$(python3 "$REPO/scripts/resolve_image.py" 3.12 --print-platform 2>/dev/null)"

ok   () { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad  () { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "=== 1. density scorer: no false positives ==="
# re.compile, @t.overload, @v.setter, @property, bare `sys.modules` read.
# Must together produce ZERO features. All four were real bugs found in calibration.
mkdir -p /tmp/tw_fp_check && cp "$FIX/false_positives.py" /tmp/tw_fp_check/ 2>/dev/null
out="$(python3 "$REPO/scripts/density_score.py" /tmp/tw_fp_check 2>/dev/null)"
if [ -z "$out" ]; then
  bad "scorer produced no output"
else
  bads="$(printf '%s' "$out" | python3 -c "
import json,sys
f=json.load(sys.stdin)['source']['features']
print(','.join(k for k in ('eval_exec','registry_decorator','sys_modules') if f.get(k,0)))" 2>/dev/null)"
  [ -z "$bads" ] && ok "re.compile / @t.overload / @v.setter / sys.modules-read -> 0 features" \
                 || bad "false positives fired: $bads"
fi

echo "=== 2. density scorer: all features still detected ==="
out="$(python3 "$REPO/scripts/density_score.py" "$FIX/all_features" 2>/dev/null)"
miss="$(printf '%s' "$out" | python3 -c "
import json,sys
need={'dynamic_import','eval_exec','getattr_dynamic','getattr_literal','attr_protocol',
      'dynamic_class','registry_decorator','subscript_call','namespace_access'}
f=set(json.load(sys.stdin)['source']['features'])
print(','.join(sorted(need-f)))" 2>/dev/null)"
[ -z "$miss" ] && ok "all 9 dynamic features detected" || bad "features not detected: $miss"

echo "=== 3. density scorer: size gate + denominator floor ==="
# A tiny fixture must be TOO_SMALL, never a huge score. Before the floor, a
# 29-SLOC file scored 701 because per-KLOC amplifies below 1 KLOC.
st="$(printf '%s' "$out" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['stratum'],d['density_score'])" 2>/dev/null)"
case "$st" in
  TOO_SMALL\ *) sc="${st#TOO_SMALL }"
    awk "BEGIN{exit !($sc < 100)}" && ok "tiny fixture -> TOO_SMALL, score $sc (floor holds)" \
                                   || bad "score $sc implausibly high; denominator floor broken" ;;
  *) bad "expected TOO_SMALL, got '$st'" ;;
esac

echo "=== 4. base image pins are digests, for every platform ==="
res="$(python3 -c "
import json
c=json.load(open('$REPO/config/base_images.json'))
plats=list(c['platforms'])
bad=[]
for ver,img in c['images'].items():
    d=img.get('digests',{})
    for p in plats:
        if not str(d.get(p,'')).startswith('sha256:'):
            bad.append(f'{ver}/{p}')
print(f\"{len(c['images'])} {len(plats)} {','.join(bad)}\")" 2>/dev/null)"
set -- $res
nimg="${1:-0}"; nplat="${2:-0}"; badlist="${3:-}"
if [ -z "$badlist" ] && [ "$nimg" = "5" ]; then
  ok "$nimg images x $nplat platforms all pinned by sha256 digest"
else
  bad "not digest-pinned: ${badlist:-<config unreadable>}"
fi

echo "=== 5. licence mapping reproduces ins3 §2 qualification ==="
if out="$(python3 "$REPO/scripts/github_meta.py" \
      --url https://github.com/psf/requests \
      --url https://github.com/pallets/click \
      --url https://github.com/django/django 2>/dev/null)" && [ -n "$out" ]; then
  res="$(printf '%s' "$out" | python3 -c "
import json,sys
EXP={'requests':'Apache','click':'BSD','django':'BSD'}
bad=[]
for l in sys.stdin:
    d=json.loads(l); n=d['repo_url'].rstrip('/').split('/')[-1]
    if n in EXP and d['licence']!=EXP[n]: bad.append(f\"{n}={d['licence']}\")
print(','.join(bad))" 2>/dev/null)"
  [ -z "$res" ] && ok "requests->Apache, click->BSD, django->BSD" || bad "mismatch: $res"
else
  echo "  SKIP  no network or API rate-limited"
fi

echo "=== 6. platform resolves to a native image ==="
if [ -z "$IMG" ] || [ -z "$PLATFORM" ]; then
  bad "could not resolve a pinned image for this platform"
else
  hostarch="$(docker version --format '{{.Server.Arch}}' 2>/dev/null || echo unknown)"
  case "$hostarch" in
    amd64|x86_64) hostplat="linux/amd64" ;;
    arm64|aarch64) hostplat="linux/arm64" ;;
    *) hostplat="unknown" ;;
  esac
  if [ "$hostplat" = "unknown" ]; then
    echo "  SKIP  docker not reachable"
  elif [ "$PLATFORM" = "$hostplat" ]; then
    ok "$PLATFORM matches host ($hostarch) -- no emulation"
  else
    bad "resolved $PLATFORM but host is $hostplat -- WOULD EMULATE, timings invalid"
  fi
fi

echo "=== 7. static extraction layer (Phase 1 §1.2) ==="
# The full suite lives in tests/test_static.py -- 39 checks over the node set,
# the §2.2 taxonomy, PyCG name mapping and Pyright definition mapping. Rolled up
# to one line here; run it directly for the detail.
if out="$(python3 "$REPO/tests/test_static.py" 2>&1)"; then
  ok "$(printf '%s' "$out" | tail -2 | tr -d '\n' | sed 's/^ *//')"
else
  bad "static extraction checks failed:"
  printf '%s\n' "$out" | grep -E '^  FAIL' | sed 's/^/        /'
fi

if [ "$FULL" = "1" ]; then
  echo "=== 8. full calibration sweep (expects 6 HIGH / 4 MED / 3 LOW / 1 TOO_SMALL) ==="
  RR="${TW_DATA:-$HOME/traceweave-data}/refrepos"
  if [ ! -d "$RR" ] || [ -z "$(ls -A "$RR" 2>/dev/null)" ]; then
    echo "  SKIP  reference repos absent. Regenerate with:"
    echo "        mkdir -p $RR && cd $RR && \\"
    echo "        xargs -P7 -I{} sh -c 'git clone --quiet --depth 1 {} \$(basename {})' < $REPO/config/reference_repos.txt"
  else
    got="$(docker run --rm --network=none -v "$RR":/repos:ro -v "$REPO/scripts":/s:ro "$IMG" \
      bash -c 'for d in /repos/*/; do python3 /s/density_score.py "$d" 2>/dev/null; done' \
      | python3 -c "
import json,sys,collections,re
c=collections.Counter()
for blob in re.findall(r'\{.*?\n\}', sys.stdin.read(), re.S):
    try: c[json.loads(blob)['stratum']]+=1
    except Exception: pass
print(' '.join(f'{k}={v}' for k,v in sorted(c.items())))" 2>/dev/null)"
    echo "        got: $got"
    [ "$got" = "HIGH=6 LOW=3 MED=4 TOO_SMALL=1" ] \
      && ok "calibration reproduces the frozen distribution" \
      || bad "distribution drifted -- see docs/density_scorer_spec.md §2"
  fi
fi

echo
echo "-----------------------------"
echo " passed: $PASS   failed: $FAIL"
echo "-----------------------------"
[ "$FAIL" -eq 0 ] || exit 1
