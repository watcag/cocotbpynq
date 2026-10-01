#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/hls/src"
BUILD_DIR="${ROOT_DIR}/build"
RTL_DIR="${ROOT_DIR}/rtl/generated"
TCL_SCRIPT="${ROOT_DIR}/scripts/export_kernel.tcl"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <z1|kv260> [clock_ns]" >&2
  exit 1
fi

BOARD="$1"
CLOCK_NS="${2:-10.0}"

case "${BOARD}" in
  z1)
    PART="xc7z020clg400-1"
    ;;
  kv260)
    PART="xck26-sfvc784-2LV-c"
    ;;
  *)
    echo "unsupported board: ${BOARD}" >&2
    exit 1
    ;;
esac

if ! command -v vitis_hls >/dev/null 2>&1; then
  echo "vitis_hls not found in PATH" >&2
  exit 1
fi

if [[ -z "${VITIS_LIBRARIES:-}" ]]; then
  VITIS_LIBRARIES="${ROOT_DIR}/Vitis_Libraries"
fi

export VITIS_LIBRARIES

if [[ ! -d "${VITIS_LIBRARIES}/vision/L1/include" ]]; then
  echo "VITIS_LIBRARIES path is invalid: ${VITIS_LIBRARIES}" >&2
  echo "Expected to find: ${VITIS_LIBRARIES}/vision/L1/include" >&2
  exit 1
fi

mkdir -p "${BUILD_DIR}" "${RTL_DIR}"

KERNELS=(
  gaussian3x3_hls
  median3x3_hls
  laplacian3x3_hls
  sobel_mag_hls
)

for kernel in "${KERNELS[@]}"; do
  src_file="${SRC_DIR}/${kernel}.cpp"
  echo "[vision] exporting ${kernel} for ${BOARD} (${PART})"
  export HLS_TOP_NAME="${kernel}"
  export HLS_SRC_FILE="${src_file}"
  export HLS_PROJECT_ROOT="${BUILD_DIR}"
  export HLS_RTL_ROOT="${RTL_DIR}"
  export HLS_PART_NAME="${PART}"
  export HLS_CLOCK_NS="${CLOCK_NS}"
  vitis_hls "${TCL_SCRIPT}"

  kernel_build_dir="${BUILD_DIR}/${kernel}/solution1/impl/verilog"
  kernel_rtl_dir="${RTL_DIR}/${kernel}"

  rm -rf "${kernel_rtl_dir}"
  mkdir -p "${kernel_rtl_dir}"

  if [[ ! -d "${kernel_build_dir}" ]]; then
    echo "missing exported verilog directory: ${kernel_build_dir}" >&2
    exit 1
  fi

  cp -a "${kernel_build_dir}/." "${kernel_rtl_dir}/"
done

echo
echo "[vision] export complete"
echo "[vision] generated RTL copied under ${RTL_DIR}"
echo "[vision] next step: add thin RTL wrappers and generate a YAML source list for pynq-pr"
