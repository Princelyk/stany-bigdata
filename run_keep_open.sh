#!/usr/bin/env bash
set -u

cd "$(dirname "$0")"
mkdir -p results/logs

source venv/bin/activate
export PYTHONPATH="$(pwd)"

LOG="results/logs/run_$(date +%F_%H-%M-%S).log"
echo "Logging to: $LOG"

bash -x scripts/run_full_pipeline.sh 2>&1 | tee "$LOG"
CODE=${PIPESTATUS[0]}

echo
echo "=========================================="
echo "PIPELINE EXIT CODE: $CODE"
echo "LOG: $LOG"
echo "=========================================="
echo
read -p "Appuyez sur Entrée pour fermer..."
exit "$CODE"

