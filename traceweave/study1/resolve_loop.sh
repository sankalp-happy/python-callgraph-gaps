#!/usr/bin/env bash
# One loop per model, run beside batch.py: every 10 minutes, ask the model about each repo whose
# bench is done. tw.py resolve resumes where it stopped and waits out Groq 429s, so re-asking a
# finished repo costs nothing. Stop it by hand once `tw.py bench` shows every repo answered.
#
#   setsid nohup ./resolve_loop.sh groq:openai/gpt-oss-20b > ~/resolve-20b.log 2>&1 < /dev/null &
#
# Several Groq accounts (co-authors' keys, with Groq's permission): give each its own shard k/n
# and its key in GROQ_API_KEY. A shard owns every n-th repo, so no two loops share an output file.
#
#   GROQ_API_KEY=... ./resolve_loop.sh groq:openai/gpt-oss-20b 2/5
set -u
H=${TW_HARNESS:-$HOME/traceweave-harness}
B=${TW_DATA:-$HOME/traceweave-data}/study1/bench
TSV=$(cd "$(dirname "$0")" && pwd)/repos.tsv
s=${2:-0/1}; k=${s%/*}; n=${s#*/}
cd "$H"
while :; do
  i=0
  for r in $(grep -v '^#' "$TSV" | tail -n +2 | cut -f1); do
    [ $((i++ % n)) -eq "$k" ] && [ -f "$B/$r.txt" ] && python3 tw.py resolve "$r" --model "$1"
  done
  sleep 600
done
