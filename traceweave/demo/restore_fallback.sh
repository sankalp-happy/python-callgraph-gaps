#!/usr/bin/env bash
# restore_fallback.sh - Docker hiccup on demo day: use this instead of
# waiting or retrying live (Success Criteria).
#
# The fallback pair's run_id (9999999999) is a deliberately large fixed
# placeholder -- LiveDemo.tsx rejects any file whose run_id isn't strictly
# greater than the last one it displayed (staleness detection), so a small
# or arbitrary placeholder would itself get rejected as stale right when
# it's needed most. 9999999999 is larger than any real epoch-seconds run_id
# until the year 2286.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd ../.. && pwd)"
LIVE_DIR="$REPO_ROOT/explainer/public/live"

cp "$LIVE_DIR/fallback"/*.json "$LIVE_DIR/"
echo "restored fallback pair (run_id=9999999999) -> $LIVE_DIR"
