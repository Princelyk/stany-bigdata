#!/usr/bin/env bash
#
# run_scalability_protocol.sh — one-command Linux driver for the full JISA
# scalability protocol: 3 weak-scaling replicates per dataset (D1/D2/D3),
# strong-scaling on D2, then statistical analysis.
#
# This is the Linux counterpart to scripts/run_scalability_protocol.ps1. It is
# meant to run on Ubuntu with the *native* liboqs (venv/), where ML-KEM is
# ~100x faster than the pure-Python Windows shim — the full protocol is only
# practical there.
#
# Usage (from the project root):
#   bash scripts/run_scalability_protocol.sh                 # full protocol
#   bash scripts/run_scalability_protocol.sh --dry-run       # print commands only
#   bash scripts/run_scalability_protocol.sh --reps 3 --no-strong
#   bash scripts/run_scalability_protocol.sh --max-files 200 # quick smoke of every step
#
# Options:
#   --d1-dir DIR            (default data/user_data/D1)
#   --d2-dir DIR            (default data/user_data/D2)
#   --d3-dir DIR            (default data/user_data/D3)
#   --out DIR              output root (default results/data/protocol)
#   --reps N               weak replicates per dataset + strong repetitions (default 3)
#   --threads LIST         strong-scaling worker counts (default 1,2,4,8,16)
#   --correctness-samples N (default 100)
#   --max-files N          cap files per run, 0 = all (default 0)
#   --max-bytes-per-file N  cap bytes read per file, 0 = full (default 0)
#   --no-strong            skip strong-scaling on D2
#   --dry-run              print the commands without running them
#
set -euo pipefail

# ---- resolve project root (script lives in <root>/scripts) ----------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

# ---- defaults --------------------------------------------------------------
D1_DIR="data/user_data/D1"
D2_DIR="data/user_data/D2"
D3_DIR="data/user_data/D3"
OUT_DIR="results/data/protocol"
REPS=3
THREADS="1,2,4,8,16"
CORRECTNESS_SAMPLES=100
MAX_FILES=0
MAX_BYTES=0
RUN_STRONG=1
DRY_RUN=0

# ---- parse args ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --d1-dir)               D1_DIR="$2"; shift 2 ;;
        --d2-dir)               D2_DIR="$2"; shift 2 ;;
        --d3-dir)               D3_DIR="$2"; shift 2 ;;
        --out)                  OUT_DIR="$2"; shift 2 ;;
        --reps)                 REPS="$2"; shift 2 ;;
        --threads)              THREADS="$2"; shift 2 ;;
        --correctness-samples)  CORRECTNESS_SAMPLES="$2"; shift 2 ;;
        --max-files)            MAX_FILES="$2"; shift 2 ;;
        --max-bytes-per-file)   MAX_BYTES="$2"; shift 2 ;;
        --no-strong)            RUN_STRONG=0; shift ;;
        --dry-run)              DRY_RUN=1; shift ;;
        -h|--help)              sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

# ---- activate venv (native liboqs on Linux) --------------------------------
if [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    PY="python"
    echo "Activated venv/ (expecting native liboqs)."
else
    PY="python3"
    echo "WARNING: venv/bin/activate not found. Using system python3."
    echo "         Run 'bash scripts/setup_environment.sh' first for native liboqs."
fi

# ---- sanity check: oqs importable, and warn if it's the slow shim ----------
"${PY}" - <<'PYCHECK'
import sys
try:
    import oqs
except Exception as exc:
    sys.exit(f"ERROR: 'import oqs' failed: {exc}\nInstall/activate the environment first.")
mechs = set(oqs.get_enabled_kem_mechanisms())
if "ML-KEM-1024" not in mechs:
    sys.exit("ERROR: ML-KEM-1024 not available from oqs.")
# The kyber-py Windows shim exposes internals (e.g. _KEM_BACKENDS) that native
# liboqs-python does not; use that as a reliable, docstring-independent marker.
is_shim = hasattr(oqs, "_KEM_BACKENDS") or "kyber-py" in (getattr(oqs, "__doc__", "") or "")
if is_shim:
    print("WARNING: oqs is the pure-Python Windows shim - the protocol will be SLOW.")
    print("         For real timings, run on Linux with native liboqs (venv/).")
else:
    print("oqs OK: native liboqs, ML-KEM-1024 available.")
PYCHECK

# ---- logging ---------------------------------------------------------------
mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${OUT_DIR}/protocol_run_${STAMP}.log"
echo "Logging to ${LOG}"
# tee everything from here on
exec > >(tee -a "${LOG}") 2>&1

echo "=============================================================="
echo "Scalability protocol  |  start $(date)"
echo "root=${ROOT_DIR}"
echo "out=${OUT_DIR}  reps=${REPS}  threads=${THREADS}  strong=${RUN_STRONG}"
echo "max_files=${MAX_FILES}  max_bytes_per_file=${MAX_BYTES}  dry_run=${DRY_RUN}"
echo "=============================================================="

# ---- helpers ---------------------------------------------------------------
run_cmd() {
    echo "+ ${PY} $*"
    if [[ "${DRY_RUN}" -eq 0 ]]; then
        "${PY}" "$@"
    fi
}

run_weak_dataset() {
    local ds="$1" dir="$2" rep run_id
    if [[ ! -d "${dir}" ]]; then
        echo "WARNING: skipping ${ds} — data dir not found: ${dir}"
        return 0
    fi
    for (( rep=1; rep<=REPS; rep++ )); do
        run_id="${ds}_r${rep}"
        echo ""
        echo "----- weak scaling: ${ds} replicate ${rep}/${REPS} ($(date +%H:%M:%S)) -----"
        run_cmd -m src.benchmarks.scalability_protocol_run \
            --dataset-id "${ds}" \
            --data-dir "${dir}" \
            --out "${OUT_DIR}" \
            --run-id "${run_id}" \
            --correctness-samples "${CORRECTNESS_SAMPLES}" \
            --max-files "${MAX_FILES}" \
            --max-bytes-per-file "${MAX_BYTES}"
    done
}

# ---- 1) weak scaling -------------------------------------------------------
echo ""
echo "### Weak scaling (${REPS} replicates each) ###"
run_weak_dataset "D1" "${D1_DIR}"
run_weak_dataset "D2" "${D2_DIR}"
run_weak_dataset "D3" "${D3_DIR}"

# ---- 2) strong scaling on D2 ----------------------------------------------
if [[ "${RUN_STRONG}" -eq 1 ]]; then
    if [[ -d "${D2_DIR}" ]]; then
        echo ""
        echo "### Strong scaling on D2 (threads=${THREADS}, reps=${REPS}) ###"
        run_cmd -m src.benchmarks.scalability_protocol_strong \
            --dataset-id "D2" \
            --data-dir "${D2_DIR}" \
            --out "${OUT_DIR}" \
            --run-id "D2_strong_${STAMP}" \
            --threads "${THREADS}" \
            --repetitions "${REPS}" \
            --max-files "${MAX_FILES}" \
            --max-bytes-per-file "${MAX_BYTES}"
    else
        echo "WARNING: skipping strong scaling — D2 dir not found: ${D2_DIR}"
    fi
else
    echo ""
    echo "### Strong scaling skipped (--no-strong) ###"
fi

# ---- 3) analysis -----------------------------------------------------------
echo ""
echo "### Protocol analysis (baseline D1) ###"
run_cmd -m src.benchmarks.scalability_protocol_analyze \
    --out "${OUT_DIR}" \
    --baseline-dataset "D1"

echo ""
echo "=============================================================="
echo "Done $(date). Outputs in ${OUT_DIR}"
echo "Log: ${LOG}"
echo "=============================================================="
