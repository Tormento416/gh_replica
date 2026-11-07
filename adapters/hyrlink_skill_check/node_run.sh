#!/bin/sh
# Run the hyrlink-pro skill-check pipeline eval on this node, once per reasoning mode.
#
# Usage: node_run.sh LABEL HYRLINK_ROOT DATASET OUTPUT_DIR [MODES]
#   LABEL         hardware label, e.g. g7e-2xlarge
#   HYRLINK_ROOT  the node's deployed hyrlink-pro checkout (the pipeline code under test)
#   DATASET       blueprint JSONL, relative to the gh_replica eval root or absolute
#   OUTPUT_DIR    reports and environment snapshots go here
#   MODES         space-separated reasoning modes, default "off auto on"
#
# Container IPs are resolved by name for every mode. A mode's run is marked INVALID if either model
# container restarts during it, and the script exits 3 at the end. Reads docker metadata only.
set -eu

LABEL=${1:?usage: node_run.sh LABEL HYRLINK_ROOT DATASET OUTPUT_DIR [MODES]}
HYRLINK_ROOT=${2:?usage}
DATASET=${3:?usage}
OUT=${4:?usage}
MODES=${5:-off auto on}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# Resolve caller-relative paths before any cd, so the report, its snapshot and the checkout agree.
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
HYRLINK_ROOT=$(cd "$HYRLINK_ROOT" && pwd)
GEMMA=${GEMMA_CONTAINER:-hyrlink_small_model_server}
QWEN=${QWEN_CONTAINER:-hyrlink_llama_server}
PY=${PYTHON:-$ROOT/venv/bin/python}

ip_of() { docker inspect "$1" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'; }
started_of() { docker inspect "$1" --format '{{.State.StartedAt}} restarts={{.RestartCount}}'; }
wait_healthy() {
  n=0
  while [ "$n" -lt 60 ]; do
    [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$1:8080/health" || true)" = 200 ] && return 0
    n=$((n + 1)); sleep 5
  done
  echo "server at $1 is not healthy after 5 minutes" >&2
  return 1
}

mkdir -p "$OUT"
invalid=0
for MODE in $MODES; do
  GIP=$(ip_of "$GEMMA"); QIP=$(ip_of "$QWEN")
  [ -n "$GIP" ] && [ -n "$QIP" ] || { echo "could not resolve container IPs ($GEMMA, $QWEN)" >&2; exit 2; }
  wait_healthy "$GIP"; wait_healthy "$QIP"
  STAMP=$(date +%Y%m%dT%H%M%S)
  BASE="skill-check-$LABEL-$MODE-$STAMP"
  BEFORE_G=$(started_of "$GEMMA"); BEFORE_Q=$(started_of "$QWEN")
  {
    echo "label=$LABEL mode=$MODE dataset=$DATASET date=$(date -u +%FT%TZ)"
    echo "hyrlink_commit=$(git -c safe.directory="$HYRLINK_ROOT" -C "$HYRLINK_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>&1 || true
    echo "gemma container=$GEMMA ip=$GIP $BEFORE_G"
    echo "qwen container=$QWEN ip=$QIP $BEFORE_Q"
    ps -eo args | grep '[l]lama-server' | sed -E 's/(--(api-key|api-key-file|hf-token)[= ])[^ ]+/\1***/g' | cut -c1-300
  } > "$OUT/$BASE.env.txt"
  (cd "$ROOT" && PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" adapters/hyrlink_skill_check/skill_check_eval.py \
    --hyrlink-root "$HYRLINK_ROOT" --dataset "$DATASET" --reasoning "$MODE" --label "$LABEL" --allow-remote \
    --generator-url "http://$GIP:8080" --verifier-url "http://$QIP:8080" --output "$OUT/$BASE.json") || {
      echo "mode $MODE failed" | tee -a "$OUT/$BASE.env.txt" >&2; invalid=1; }
  # Checked whether or not the eval failed: a restart is the usual reason it fails.
  if [ "$BEFORE_G" != "$(started_of "$GEMMA")" ] || [ "$BEFORE_Q" != "$(started_of "$QWEN")" ]; then
    echo "INVALID RUN ($MODE): a model container restarted during the run" | tee -a "$OUT/$BASE.env.txt" >&2
    invalid=1
  fi
done
[ "$invalid" -eq 0 ] || exit 3
