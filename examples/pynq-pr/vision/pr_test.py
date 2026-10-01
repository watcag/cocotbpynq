"""
Run on hardware or in cocotbpynq simulation.
Tests independent RP reconfiguration and chained pipelines for the vision case.

Simulation:
    pynq-pr sim -c pr_z1.yaml --test pr_test.py -f

Hardware:
    python3 pr_test.py --project vision_z1
    python3 pr_test.py --project vision_z1 --icap
"""

import os
from pathlib import Path

import numpy as np

from visual import load_grayscale_image, save_visual_gallery

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ
EXAMPLE_DIR = Path(__file__).resolve().parent

if not COCOTB_IS_RUNNING:
    import argparse
    from pynq import MMIO, allocate
    from overlay import Overlay
else:
    import cocotbpynq
    from cocotbpynq import MMIO
    from pynq_pr.overlay_sim import Overlay, allocate


CTRL_ADDR = 0x00
ROWS_ADDR = 0x10
COLS_ADDR = 0x18
CTRL_START_AUTO_RESTART = 0x81

RP0_MODULES = ("gaussian3x3", "median3x3")
RP1_MODULES = ("laplacian3x3", "sobel_mag")


def _partition_mmio(overlay, partition_name):
    prefix = f"{partition_name}/rp/"
    matches = [
        info for name, info in overlay.ip_dict.items()
        if name.startswith(prefix)
    ]
    if not matches:
        raise RuntimeError(f"Could not locate AXI-Lite IP for partition '{partition_name}'")
    info = matches[0]
    return MMIO(info["phys_addr"], info["addr_range"])


def configure_partition(overlay, partition_name, rows, cols):
    mmio = _partition_mmio(overlay, partition_name)
    mmio.write(ROWS_ADDR, rows)
    mmio.write(COLS_ADDR, cols)
    rows_rb = mmio.read(ROWS_ADDR)
    cols_rb = mmio.read(COLS_ADDR)
    if rows_rb != rows or cols_rb != cols:
        raise AssertionError(
            f"{partition_name} AXI-Lite readback mismatch: "
            f"rows={rows_rb}, cols={cols_rb}, expected {rows}x{cols}"
        )
    mmio.write(CTRL_ADDR, CTRL_START_AUTO_RESTART)


def dma_transfer(dma, frame_u8):
    rows, cols = frame_u8.shape
    words = frame_u8.astype(np.int32).reshape(-1)
    x_buf = allocate(shape=words.shape[0], dtype=np.int32)
    y_buf = allocate(shape=words.shape[0], dtype=np.int32)
    np.copyto(x_buf, words)
    dma.recvchannel.transfer(y_buf)
    dma.sendchannel.transfer(x_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    result = (np.array(y_buf, dtype=np.int32) & 0xFF).astype(np.uint8).reshape(rows, cols)
    if hasattr(x_buf, "freebuffer"):
        x_buf.freebuffer()
    if hasattr(y_buf, "freebuffer"):
        y_buf.freebuffer()
    return result


def pad(frame, mode):
    if mode == "constant":
        return np.pad(frame, ((1, 1), (1, 1)), mode="constant")
    if mode == "edge":
        return np.pad(frame, ((1, 1), (1, 1)), mode="edge")
    raise ValueError(f"Unknown pad mode: {mode}")


def gaussian3x3_ref(frame):
    kernel = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.int32)
    src = pad(frame, "constant").astype(np.int32)
    out = np.zeros_like(frame, dtype=np.uint8)
    for r in range(frame.shape[0]):
        for c in range(frame.shape[1]):
            window = src[r:r + 3, c:c + 3]
            value = int(np.sum(window * kernel) >> 4)
            out[r, c] = np.uint8(max(0, min(255, value)))
    return out


def median3x3_ref(frame):
    src = pad(frame, "edge").astype(np.int32)
    out = np.zeros_like(frame, dtype=np.uint8)
    for r in range(frame.shape[0]):
        for c in range(frame.shape[1]):
            window = src[r:r + 3, c:c + 3].reshape(-1)
            out[r, c] = np.uint8(np.median(window))
    return out


def laplacian3x3_ref(frame):
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.int32)
    src = pad(frame, "constant").astype(np.int32)
    out = np.zeros_like(frame, dtype=np.uint8)
    for r in range(frame.shape[0]):
        for c in range(frame.shape[1]):
            window = src[r:r + 3, c:c + 3]
            value = abs(int(np.sum(window * kernel)))
            out[r, c] = np.uint8(min(255, value))
    return out


def sobel_mag_ref(frame):
    gx_kernel = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.int32)
    gy_kernel = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.int32)
    src = pad(frame, "constant").astype(np.int32)
    out = np.zeros_like(frame, dtype=np.uint8)
    for r in range(frame.shape[0]):
        for c in range(frame.shape[1]):
            window = src[r:r + 3, c:c + 3]
            gx = int(np.sum(window * gx_kernel))
            gy = int(np.sum(window * gy_kernel))
            value = min(255, abs(gx) + abs(gy))
            out[r, c] = np.uint8(value)
    return out


REFS = {
    "gaussian3x3": gaussian3x3_ref,
    "median3x3": median3x3_ref,
    "laplacian3x3": laplacian3x3_ref,
    "sobel_mag": sobel_mag_ref,
}


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_visual_dir(path):
    visual_dir = Path(path).expanduser()
    if not visual_dir.is_absolute():
        visual_dir = EXAMPLE_DIR / visual_dir
    return visual_dir


def resolve_visual_source(path):
    source_path = Path(path).expanduser()
    if not source_path.is_absolute():
        source_path = EXAMPLE_DIR / source_path
    return source_path


def run_ref_chain(frame, modules):
    out = frame
    for module in modules:
        out = REFS[module](out)
    return out


def check_frame(label, result, expected):
    status = "PASS" if np.array_equal(result, expected) else "FAIL"
    print(f"  {label}: [{status}]")
    if status != "PASS":
        mismatches = np.argwhere(result != expected)
        first = tuple(mismatches[0]) if mismatches.size else None
        print(f"    first mismatch: {first}")
        if first is not None:
            print(f"    got/expected: {int(result[first])}/{int(expected[first])}")
        print(f"    mismatch count: {int(mismatches.shape[0])}")
        for row in range(min(4, result.shape[0])):
            print(f"    got row{row}:      {result[row].tolist()}")
            print(f"    expected row{row}: {expected[row].tolist()}")
        raise AssertionError(f"Mismatch for {label}")


def make_frames():
    base = np.fromfunction(lambda r, c: (17 * r + 11 * c) % 256, (16, 16), dtype=int).astype(np.uint8)
    impulse = base.copy()
    impulse[2, 3] = 255
    impulse[4, 11] = 0
    impulse[9, 5] = 255
    impulse[13, 14] = 0

    smooth = np.zeros((16, 16), dtype=np.uint8)
    smooth[3:13, 4:12] = 180
    smooth[6:10, 6:10] = 40
    smooth[:, 8:] = np.clip(smooth[:, 8:] + 30, 0, 255)
    return impulse, smooth


def make_pattern_frame(rows, cols, seed):
    frame = np.fromfunction(
        lambda r, c: (seed + 23 * r + 19 * c + (r * c) % 31) % 256,
        (rows, cols),
        dtype=int,
    ).astype(np.uint8)
    if rows > 4 and cols > 5:
        frame[1, 2] = 255
        frame[rows - 2, cols - 3] = 0
    return frame


def load_module(overlay, partition, module, ext, icap):
    overlay.pr_download(partition, f"{partition}_{module}{ext}", icap=icap)


def run_pipeline(overlay, icap, frame, specs):
    ext = ".bin" if icap else ".bit"
    for partition, module in specs:
        load_module(overlay, partition, module, ext, icap)
        configure_partition(overlay, partition, frame.shape[0], frame.shape[1])

    partitions = [partition for partition, _module in specs]
    dma = overlay.chain(partitions)
    return dma_transfer(dma, frame)


def test_visual_example(overlay, icap, visual_dir, visual_source):
    print("\n=== Visual goose gallery ===")

    frame = load_grayscale_image(visual_source, rows=72, cols=96)
    cases = [
        {
            "label": "gaussian3x3",
            "modules": ("gaussian3x3",),
            "specs": (("rp0", "gaussian3x3"),),
        },
        {
            "label": "median3x3",
            "modules": ("median3x3",),
            "specs": (("rp0", "median3x3"),),
        },
        {
            "label": "laplacian3x3",
            "modules": ("laplacian3x3",),
            "specs": (("rp1", "laplacian3x3"),),
        },
        {
            "label": "sobel_mag",
            "modules": ("sobel_mag",),
            "specs": (("rp1", "sobel_mag"),),
        },
        {
            "label": "median->sobel",
            "modules": ("median3x3", "sobel_mag"),
            "specs": (("rp0", "median3x3"), ("rp1", "sobel_mag")),
        },
        {
            "label": "median->laplacian",
            "modules": ("median3x3", "laplacian3x3"),
            "specs": (("rp0", "median3x3"), ("rp1", "laplacian3x3")),
        },
        {
            "label": "gaussian->laplacian",
            "modules": ("gaussian3x3", "laplacian3x3"),
            "specs": (("rp0", "gaussian3x3"), ("rp1", "laplacian3x3")),
        },
    ]

    results = []
    for case in cases:
        actual = run_pipeline(overlay, icap, frame, case["specs"])
        expected = run_ref_chain(frame, case["modules"])
        results.append({
            "label": case["label"],
            "modules": case["modules"],
            "actual": actual,
            "expected": expected,
        })

    metrics = save_visual_gallery(visual_dir, visual_source.name, frame, results)
    print(f"  python:      {metrics['paths']['python_png']}")
    print(f"  accelerated: {metrics['paths']['accelerated_png']}")
    print(f"  diff:        {metrics['paths']['diff_png']}")

    for result in results:
        check_frame(result["label"], result["actual"], result["expected"])
    overlay.default_routing()


def test_axilite_dynamic_sizes(overlay, icap):
    ext = ".bin" if icap else ".bit"

    print("\n=== AXI-Lite dynamic sizes ===")

    cases = [
        ("rp0", "gaussian3x3", make_pattern_frame(10, 12, 5)),
        ("rp1", "sobel_mag", make_pattern_frame(11, 9, 37)),
    ]

    for partition, module, frame in cases:
        load_module(overlay, partition, module, ext, icap)
        configure_partition(overlay, partition, frame.shape[0], frame.shape[1])
        dma = overlay.chain([partition])
        result = dma_transfer(dma, frame)
        expected = REFS[module](frame)
        check_frame(f"{partition}/{module} {frame.shape[0]}x{frame.shape[1]}", result, expected)

    overlay.default_routing()


def test_independent(overlay, icap):
    impulse, smooth = make_frames()
    ext = ".bin" if icap else ".bit"

    print("\n=== Independent ===")

    for module in RP0_MODULES:
        load_module(overlay, "rp0", module, ext, icap)
        configure_partition(overlay, "rp0", impulse.shape[0], impulse.shape[1])
        dma = overlay.chain(["rp0"])
        result = dma_transfer(dma, impulse)
        expected = REFS[module](impulse)
        check_frame(f"rp0/{module}", result, expected)

    for module in RP1_MODULES:
        load_module(overlay, "rp1", module, ext, icap)
        configure_partition(overlay, "rp1", smooth.shape[0], smooth.shape[1])
        dma = overlay.chain(["rp1"])
        result = dma_transfer(dma, smooth)
        expected = REFS[module](smooth)
        check_frame(f"rp1/{module}", result, expected)

    overlay.default_routing()


def test_chained(overlay, icap):
    impulse, smooth = make_frames()
    ext = ".bin" if icap else ".bit"

    print("\n=== Chains ===")

    sequences = [
        ("median->sobel", impulse, ("median3x3", "sobel_mag")),
        ("median->laplacian", impulse, ("median3x3", "laplacian3x3")),
        ("gaussian->laplacian", smooth, ("gaussian3x3", "laplacian3x3")),
    ]

    current_rp0 = None
    current_rp1 = None
    dma = overlay.chain(["rp0", "rp1"])

    for label, frame, modules in sequences:
        mod_rp0, mod_rp1 = modules
        if current_rp0 != mod_rp0:
            load_module(overlay, "rp0", mod_rp0, ext, icap)
            current_rp0 = mod_rp0
        if current_rp1 != mod_rp1:
            load_module(overlay, "rp1", mod_rp1, ext, icap)
            current_rp1 = mod_rp1

        configure_partition(overlay, "rp0", frame.shape[0], frame.shape[1])
        configure_partition(overlay, "rp1", frame.shape[0], frame.shape[1])
        dma = overlay.chain(["rp0", "rp1"])
        result = dma_transfer(dma, frame)
        expected = run_ref_chain(frame, modules)
        check_frame(label, result, expected)

    overlay.default_routing()


def main(dut=None):
    if COCOTB_IS_RUNNING:
        overlay = Overlay("design.bit")
        icap = False
        visual_enabled = not env_flag("VISION_SKIP_VISUAL")
        visual_dir = resolve_visual_dir(os.environ.get("VISION_VISUAL_DIR", "visual_artifacts"))
        visual_source = resolve_visual_source(os.environ.get("VISION_VISUAL_SOURCE", "visual_artifacts/goose.jpeg"))
    else:
        parser = argparse.ArgumentParser(description="Vision PR test")
        parser.add_argument("--project", required=True)
        parser.add_argument("--icap", action="store_true")
        parser.add_argument(
            "--visual-dir",
            default=os.environ.get("VISION_VISUAL_DIR", "visual_artifacts"),
            help="Directory for generated visual golden image artifacts.",
        )
        parser.add_argument(
            "--visual-source",
            default=os.environ.get("VISION_VISUAL_SOURCE", "visual_artifacts/goose.jpeg"),
            help="Source image for visual golden gallery.",
        )
        parser.add_argument(
            "--no-visual",
            action="store_true",
            help="Skip the visual golden image artifact test.",
        )
        args = parser.parse_args()
        overlay = Overlay(f"{args.project}.bit")
        icap = args.icap
        visual_enabled = not args.no_visual and not env_flag("VISION_SKIP_VISUAL")
        visual_dir = resolve_visual_dir(args.visual_dir)
        visual_source = resolve_visual_source(args.visual_source)

    if visual_enabled:
        test_visual_example(overlay, icap, visual_dir, visual_source)
    test_axilite_dynamic_sizes(overlay, icap)
    test_independent(overlay, icap)
    test_chained(overlay, icap)
    print("\nAll tests done.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
