#!/usr/bin/env bash
# Deploy bitstreams, overlay driver, and test script to PYNQ board.
# Run from examples/pynq-pr/add_sub/.
#
# Usage:
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b <board> [bits|run|all]
#
#   -b, --board: z1 or kv260 (required)
#   command: bits, run, or all (default: all)
#
# Examples:
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b z1
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh --board kv260 bits
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b z1 run
#
# Environment: BOARD_IP and BOARD_PSWD are required. Optional: BOARD_USER
# (default xilinx on z1, ubuntu on kv260), BOARD_DIR (default ~), PROJECT.

set -e
cd "$(dirname "$0")"

BOARD=""
CMD="all"
TEST_SCRIPT="pr_test.py"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--board) BOARD="$2"; shift 2 ;;
        --test) TEST_SCRIPT="$2"; shift 2 ;;
        bits|run|all) CMD="$1"; shift ;;
        *) echo "Usage: $0 -b <board> [--test <script>] [bits|run|all]"; exit 1 ;;
    esac
done

if [ -z "$BOARD" ]; then
    echo "Usage: $0 -b <board> [bits|run|all]  (board: z1 or kv260)"; exit 1
fi

if [ "$BOARD" = "kv260" ]; then
    BOARD_USER="${BOARD_USER:-ubuntu}"
elif [ "$BOARD" = "z1" ]; then
    BOARD_USER="${BOARD_USER:-xilinx}"
else
    echo "Unknown board: $BOARD (expected z1 or kv260)"; exit 1
fi
BOARD_IP="${BOARD_IP:?Set BOARD_IP to the board hostname or IP address}"
BOARD_PSWD="${BOARD_PSWD:?Set BOARD_PSWD to the sudo password of BOARD_USER}"

PROJECT="${PROJECT:-tutorial_${BOARD}}"
BOARD_DIR="${BOARD_DIR:-~}"
BITS_DIR="$(cd "$(dirname "$0")" && pwd)/output/$PROJECT/bits"
OVERLAY_PY="$(cd "$(dirname "$0")" && pwd)/../../../packages/pynq-pr/src/pynq_pr/overlay.py"

CONFIG_FILE="pr_${BOARD}.yaml"
RECONFIG_METHOD=$(python3 -c "
import yaml, sys
with open('$CONFIG_FILE') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('reconfiguration_method', 'pcap'))
" 2>/dev/null || echo "pcap")

# --- Functions ---

do_bits() {
    echo "=== Uploading bitstreams ==="
    FILES=(
        "$BITS_DIR/$PROJECT.bit"
        "$BITS_DIR/$PROJECT.hwh"
        "$BITS_DIR"/add_*.bit "$BITS_DIR"/add_*.hwh
        "$BITS_DIR"/sub_*.bit "$BITS_DIR"/sub_*.hwh
        "$BITS_DIR"/mult_*.bit "$BITS_DIR"/mult_*.hwh
    )
    if [ "$RECONFIG_METHOD" = "icap" ]; then
        FILES+=(
            "$BITS_DIR"/add_*.bin
            "$BITS_DIR"/sub_*.bin
            "$BITS_DIR"/mult_*.bin
        )
    fi
    scp "${FILES[@]}" "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/"
}

do_run() {
    ICAP_FLAG=""
    if [ "$RECONFIG_METHOD" = "icap" ]; then
        ICAP_FLAG="--icap"
    fi

    SCRIPT_BASENAME="$(basename "$TEST_SCRIPT")"
    LOG_NAME="${SCRIPT_BASENAME%.py}.log"

    echo "=== Uploading overlay driver and test script ==="
    scp "$OVERLAY_PY" "$TEST_SCRIPT" "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/"

    echo "=== Running ${SCRIPT_BASENAME} ==="
    ssh "${BOARD_USER}@${BOARD_IP}" \
        "echo ${BOARD_PSWD} | sudo -SE bash -c 'source /etc/profile && cd ${BOARD_DIR} && python3 ${SCRIPT_BASENAME} --project ${PROJECT} ${ICAP_FLAG} 2>&1 | tee ${LOG_NAME}'"
    scp "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/${LOG_NAME}" .
    echo "=== Done. Log saved to ${LOG_NAME} ==="
}

# --- Main ---

case "$CMD" in
    bits) do_bits ;;
    run)  do_run ;;
    all)  do_bits; do_run ;;
    *)    echo "Usage: $0 <board> {bits|run|all}"; exit 1 ;;
esac
