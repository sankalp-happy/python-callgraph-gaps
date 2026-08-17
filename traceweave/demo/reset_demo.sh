#!/usr/bin/env bash
# reset_demo.sh - clear a prior run before rehearsing again or before the
# real presentation, so no stale run leaks in (Success Criteria).
#
# Scoped to the top-level files in live/ only -- does not touch
# explainer/public/live/fallback/, which is a subdirectory and stays tracked.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd ../.. && pwd)"
LIVE_DIR="$REPO_ROOT/explainer/public/live"

rm -f "$LIVE_DIR"/*.json "$LIVE_DIR"/*.tmp
echo "reset: cleared $LIVE_DIR/*.json and *.tmp (fallback/ untouched)"
