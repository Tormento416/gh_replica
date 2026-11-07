#!/bin/sh
# Run the skill-quiz eval against the llama-server containers on this node.
#
# Usage: node_run.sh LABEL DATASET [OUTPUT_DIR]
#   LABEL      hardware label recorded in the report, e.g. g4dn-xlarge
#   DATASET    path to a golden dataset, relative to the repo root or absolute
#   OUTPUT_DIR where the report and environment snapshot go (default: .)
#
# Container IPs change when compose recreates a container, so they are resolved by name on every
# run. The run is marked INVALID (exit 3) if either model container restarts while it runs.
# Reads docker metadata only; it never starts, stops or reconfigures a container.
set -eu

LABEL=${1:?usage: node_run.sh LABEL DATASET [OUTPUT_DIR]}
DATASET=${2:?usage: node_run.sh LABEL DATASET [OUTPUT_DIR]}
OUT=${3:-.}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
GEMMA=${GEMMA_CONTAINER:-hyrlink_small_model_server}
QWEN=${QWEN_CONTAINER:-hyrlink_llama_server}
GEMMA_MODEL=${GEMMA_MODEL:-gemma-4-e4b}
QWEN_MODEL=${QWEN_MODEL:-qwen2.5-7b}
MAX_TOKENS=${MAX_TOKENS:-4096}
PY=${PYTHON:-$ROOT/venv/bin/python}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)  # caller-relative, resolved before the cd below

ip_of() { docker inspect "$1" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'; }
started_of() { docker inspect "$1" --format '{{.State.StartedAt}} restarts={{.RestartCount}}'; }

wait_healthy() {
  n=0
  while [ "$n" -lt 60 ]; do
    code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$1:8080/health" || true)
    [ "$code" = 200 ] && return 0
    n=$((n + 1)); sleep 5
  done
  echo "server at $1 is not healthy after 5 minutes" >&2
  return 1
}

mkdir -p "$OUT"
GIP=$(ip_of "$GEMMA"); QIP=$(ip_of "$QWEN")
[ -n "$GIP" ] && [ -n "$QIP" ] || { echo "could not resolve container IPs ($GEMMA, $QWEN)" >&2; exit 2; }
wait_healthy "$GIP"; wait_healthy "$QIP"

STAMP=$(date +%Y%m%dT%H%M%S)
BASE=$(basename "$DATASET" .jsonl)
REPORT="$OUT/$BASE-$LABEL-$STAMP.json"
ENVFILE="$OUT/$BASE-$LABEL-$STAMP.env.txt"
BEFORE_G=$(started_of "$GEMMA"); BEFORE_Q=$(started_of "$QWEN")
{
  echo "label=$LABEL dataset=$DATASET max_tokens=$MAX_TOKENS date=$(date -u +%FT%TZ)"
  nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>&1 || true
  echo "gemma container=$GEMMA ip=$GIP $BEFORE_G"
  echo "qwen container=$QWEN ip=$QIP $BEFORE_Q"
  ps -eo args | grep '[l]lama-server' | sed -E 's/(--(api-key|api-key-file|hf-token)[= ])[^ ]+/\1***/g' | cut -c1-300
} > "$ENVFILE"

cd "$ROOT"
status=0
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" adapters/openai_compat/openai_compat_eval.py \
  --dataset "$DATASET" --label "$LABEL" --max-tokens "$MAX_TOKENS" --timeout 600 \
  --allow-remote --base-url "http://$GIP:8080/v1" --model "$GEMMA_MODEL" \
  --judge-base-url "http://$QIP:8080/v1" --judge-model "$QWEN_MODEL" --output "$REPORT" \
  ${STRUCTURED:+--structured} || status=$?

AFTER_G=$(started_of "$GEMMA"); AFTER_Q=$(started_of "$QWEN")
if [ "$BEFORE_G" != "$AFTER_G" ] || [ "$BEFORE_Q" != "$AFTER_Q" ]; then
  echo "INVALID RUN: a model container restarted during the run (gemma: $BEFORE_G -> $AFTER_G; qwen: $BEFORE_Q -> $AFTER_Q)" | tee -a "$ENVFILE" >&2
  exit 3
fi
[ "$status" -eq 0 ] || exit "$status"
echo "report: $REPORT"
