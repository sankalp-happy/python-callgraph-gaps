#!/usr/bin/env bash
# (Re)start one resolve_loop.sh per (model, Groq key). ~/.groq-keys holds one key per line, one per
# co-author account; '#' lines are comments. Keys never appear on a command line or in a log.
set -eu
cd "$(dirname "$0")"
mapfile -t KEYS < <(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' ~/.groq-keys)
n=${#KEYS[@]}
pkill -f '^bash ./resolve_loop.sh' || true
pkill -f 'tw.py resolve' || true          # a child left running would share a file with its successor
for m in groq:openai/gpt-oss-20b groq:openai/gpt-oss-120b groq:qwen/qwen3.8-27b; do
  for k in "${!KEYS[@]}"; do
    GROQ_API_KEY=${KEYS[$k]} setsid nohup ./resolve_loop.sh "$m" "$k/$n" \
      > ~/resolve-"${m##*/}"-"$k".log 2>&1 < /dev/null &
  done
done
echo "$n keys x 3 models started"
