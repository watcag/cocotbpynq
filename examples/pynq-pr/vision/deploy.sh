#!/usr/bin/env bash
# Deploy bitstreams, overlay driver, test script, and visual assets to a PYNQ board.
# Run from examples/pynq-pr/vision/.
#
# Usage:
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b <board> [--test <script>] [--no-visual] [bits|run|all]
#
# Examples:
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b z1
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b kv260 bits
#   BOARD_IP=<board> BOARD_PSWD=<pw> ./deploy.sh -b z1 run
#
# Environment: BOARD_IP and BOARD_PSWD are required. Optional: BOARD_USER
# (default xilinx on z1, ubuntu on kv260), BOARD_DIR (default ~), PROJECT.

set -e
cd "$(dirname "$0")"

BOARD=""
CMD="all"
TEST_SCRIPT="pr_test.py"
NO_VISUAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--board) BOARD="$2"; shift 2 ;;
        --test) TEST_SCRIPT="$2"; shift 2 ;;
        --no-visual) NO_VISUAL=1; shift ;;
        bits|run|all) CMD="$1"; shift ;;
        *) echo "Usage: $0 -b <board> [--test <script>] [--no-visual] [bits|run|all]"; exit 1 ;;
    esac
done

if [ -z "$BOARD" ]; then
    echo "Usage: $0 -b <board> [--test <script>] [--no-visual] [bits|run|all]  (board: z1 or kv260)"
    exit 1
fi

if [ "$BOARD" = "kv260" ]; then
    BOARD_USER="${BOARD_USER:-ubuntu}"
elif [ "$BOARD" = "z1" ]; then
    BOARD_USER="${BOARD_USER:-xilinx}"
else
    echo "Unknown board: $BOARD (expected z1 or kv260)"
    exit 1
fi
BOARD_IP="${BOARD_IP:?Set BOARD_IP to the board hostname or IP address}"
BOARD_PSWD="${BOARD_PSWD:?Set BOARD_PSWD to the sudo password of BOARD_USER}"

PROJECT="${PROJECT:-vision_${BOARD}}"
BOARD_DIR="${BOARD_DIR:-~}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BITS_DIR="$ROOT_DIR/output/$PROJECT/bits"
OVERLAY_PY="$ROOT_DIR/../../../packages/pynq-pr/src/pynq_pr/overlay.py"
VISUAL_PY="$ROOT_DIR/visual.py"
VISUAL_SOURCE="$ROOT_DIR/visual_artifacts/goose.jpeg"

CONFIG_FILE="pr_${BOARD}.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Missing config file: $CONFIG_FILE"
    echo "Generate it with: ./scripts/generate_config.py $BOARD"
    exit 1
fi

RECONFIG_METHOD=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('reconfiguration_method', 'pcap'))
" 2>/dev/null || echo "pcap")

require_file() {
    if [ ! -f "$1" ]; then
        echo "Missing required file: $1"
        exit 1
    fi
}

do_bits() {
    if [ ! -d "$BITS_DIR" ]; then
        echo "Missing bitstream directory: $BITS_DIR"
        echo "Build the design first so output/$PROJECT/bits exists."
        exit 1
    fi

    require_file "$BITS_DIR/$PROJECT.bit"
    require_file "$BITS_DIR/$PROJECT.hwh"

    echo "=== Uploading bitstreams ==="
    FILES=(
        "$BITS_DIR/$PROJECT.bit"
        "$BITS_DIR/$PROJECT.hwh"
        "$BITS_DIR"/rp0_*.bit "$BITS_DIR"/rp0_*.hwh
        "$BITS_DIR"/rp1_*.bit "$BITS_DIR"/rp1_*.hwh
    )
    if [ "$RECONFIG_METHOD" = "icap" ]; then
        FILES+=(
            "$BITS_DIR"/rp0_*.bin
            "$BITS_DIR"/rp1_*.bin
        )
    fi
    scp "${FILES[@]}" "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/"
}

do_run() {
    require_file "$OVERLAY_PY"
    require_file "$TEST_SCRIPT"
    require_file "$VISUAL_PY"

    ICAP_FLAG=""
    if [ "$RECONFIG_METHOD" = "icap" ]; then
        ICAP_FLAG="--icap"
    fi

    SCRIPT_BASENAME="$(basename "$TEST_SCRIPT")"
    LOG_NAME="${SCRIPT_BASENAME%.py}.log"

    VISUAL_ARGS=""
    if [ "$NO_VISUAL" = "1" ]; then
        VISUAL_ARGS="--no-visual"
    elif [ "$SCRIPT_BASENAME" = "pr_test.py" ]; then
        VISUAL_ARGS="--visual-source visual_artifacts/goose.jpeg --visual-dir visual_artifacts"
        require_file "$VISUAL_SOURCE"
    fi

    echo "=== Uploading overlay driver, test script, and visual helpers ==="
    UPLOAD_FILES=("$OVERLAY_PY" "$TEST_SCRIPT" "$VISUAL_PY")
    if [ "$SCRIPT_BASENAME" != "pr_test.py" ]; then
        UPLOAD_FILES+=("$ROOT_DIR/pr_test.py")
    fi
    scp "${UPLOAD_FILES[@]}" "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/"

    if [ "$NO_VISUAL" != "1" ] && [ "$SCRIPT_BASENAME" = "pr_test.py" ]; then
        ssh "${BOARD_USER}@${BOARD_IP}" "mkdir -p ${BOARD_DIR}/visual_artifacts"
        scp "$VISUAL_SOURCE" "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/visual_artifacts/"
    fi

    echo "=== Running ${SCRIPT_BASENAME} ==="
    ssh "${BOARD_USER}@${BOARD_IP}" \
        "echo ${BOARD_PSWD} | sudo -SE bash -c 'source /etc/profile && cd ${BOARD_DIR} && python3 ${SCRIPT_BASENAME} --project ${PROJECT} ${ICAP_FLAG} ${VISUAL_ARGS} 2>&1 | tee ${LOG_NAME}'"
    scp "${BOARD_USER}@${BOARD_IP}:${BOARD_DIR}/${LOG_NAME}" .
    echo "=== Done. Log saved to ${LOG_NAME} ==="
}

case "$CMD" in
    bits) do_bits ;;
    run)  do_run ;;
    all)  do_bits; do_run ;;
    *)    echo "Usage: $0 -b <board> [--test <script>] [--no-visual] [bits|run|all]"; exit 1 ;;
esac
