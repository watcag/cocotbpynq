"""
Video pipeline test for cocotbpynq simulation and PYNQ hardware.
Processes synthetic or real video through DFX-reconfigurable filter pipelines,
verifying correctness per frame and recording timing for paper figures.

Simulation:
    pynq-pr sim -c pr_z1.yaml --test video_test.py -f

Hardware:
    python3 video_test.py --project vision_z1 --icap
"""

import collections
import csv
import os
import time
from pathlib import Path

import numpy as np

from pr_test import REFS
from visual import load_grayscale_image, save_visual_gallery

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    import argparse
    from pynq import MMIO, allocate
    from overlay import Overlay
else:
    import cocotbpynq
    from cocotbpynq import MMIO
    from pynq_pr.overlay_sim import Overlay, allocate

VideoConfig = collections.namedtuple("VideoConfig", [
    "n_frames", "rows", "cols", "swap_frame",
    "skip_visual", "skip_timing", "artifact_dir", "source_dir",
])

CTRL_ADDR = 0x00
ROWS_ADDR = 0x10
COLS_ADDR = 0x18
CTRL_START_AUTO_RESTART = 0x81


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def synth_video(n_frames, rows, cols):
    """Yield (frame_idx, frame_uint8) for a scrolling-bar synthetic clip."""
    for idx in range(n_frames):
        frame = np.full((rows, cols), 30, dtype=np.uint8)
        bar = idx % rows
        frame[bar, :] = 200
        if bar > 0:
            frame[bar - 1, :] = 120
        if bar < rows - 1:
            frame[bar + 1, :] = 80
        yield idx, frame


def real_video(source_dir, rows, cols):
    """Yield (frame_idx, frame_uint8) from a directory of PNG frames."""
    paths = sorted(Path(source_dir).glob("*.png"))
    if not paths:
        raise RuntimeError(f"No PNG frames found in {source_dir}")
    for idx, path in enumerate(paths):
        yield idx, load_grayscale_image(path, rows=rows, cols=cols)


def video_source(source_dir, n_frames, rows, cols):
    if source_dir:
        return real_video(source_dir, rows, cols)
    return synth_video(n_frames, rows, cols)


def transfer_frame(dma, x_buf, y_buf, frame_u8):
    """Write frame_u8 into x_buf, DMA through FPGA, return result as uint8."""
    rows, cols = frame_u8.shape
    np.copyto(x_buf, frame_u8.astype(np.int32).reshape(-1))
    dma.recvchannel.transfer(y_buf)
    dma.sendchannel.transfer(x_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    return (np.array(y_buf, dtype=np.int32) & 0xFF).astype(np.uint8).reshape(rows, cols)


def write_timing_csv(all_timing, artifact_dir):
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    csv_path = artifact_dir / "timing.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["test_name", "frame_idx", "config", "frame_time_s", "swap_latency_s"])
        for row in all_timing:
            swap = row.get("swap_latency_s")
            writer.writerow([
                row["test_name"],
                row["frame_idx"],
                row["config"],
                f"{row['frame_time_s']:.6f}",
                f"{swap:.6f}" if swap is not None else "",
            ])
    print(f"\nTiming CSV written to {csv_path}")


def print_summary(test_name, config_label, frame_times, rows, cols, swap_info=None):
    n = len(frame_times)
    avg_t = sum(frame_times) / n
    min_t = min(frame_times)
    max_t = max(frame_times)
    fps = 1.0 / avg_t if avg_t > 0 else 0
    mpix = fps * rows * cols / 1e6

    print(f"\n=== {test_name} ===")
    print(f"  frames: {n}  size: {rows}x{cols}  config: {config_label}")
    print(f"  avg frame time: {avg_t * 1e3:.2f} ms  min: {min_t * 1e3:.2f} ms  max: {max_t * 1e3:.2f} ms")
    print(f"  throughput: {fps:.1f} frames/s  (pixel rate: {mpix:.2f} Mpix/s)")

    if swap_info is not None:
        swap_lat, swap_frame = swap_info
        overhead = swap_lat / avg_t if avg_t > 0 else 0
        print(f"  swap latency: {swap_lat * 1e3:.2f} ms  (at frame {swap_frame})")
        print(f"  overhead: {overhead:.2f}x frame time")


CHAIN_CONFIGS = [
    ("gaussian3x3", "laplacian3x3"),
    ("gaussian3x3", "sobel_mag"),
    ("median3x3", "laplacian3x3"),
    ("median3x3", "sobel_mag"),
]


def _short_name(module):
    return module.replace("3x3", "").replace("_mag", "")


def test_video_chained(overlay, icap, cfg, all_timing):
    ext = ".bin" if icap else ".bit"
    rows, cols = cfg.rows, cfg.cols

    for rp0_mod, rp1_mod in CHAIN_CONFIGS:
        config_label = f"{_short_name(rp0_mod)}_{_short_name(rp1_mod)}"
        test_name = f"test_chained_{config_label}"

        overlay.pr_download("rp0", f"rp0_{rp0_mod}{ext}", icap=icap)
        overlay.pr_download("rp1", f"rp1_{rp1_mod}{ext}", icap=icap)
        configure_partition(overlay, "rp0", rows, cols)
        configure_partition(overlay, "rp1", rows, cols)
        dma = overlay.chain(["rp0", "rp1"])

        x_buf = allocate(shape=rows * cols, dtype=np.int32)
        y_buf = allocate(shape=rows * cols, dtype=np.int32)
        frame_times = []
        try:
            for idx, frame in video_source(cfg.source_dir, cfg.n_frames, rows, cols):
                t0 = time.perf_counter()
                result = transfer_frame(dma, x_buf, y_buf, frame)
                frame_time = time.perf_counter() - t0
                frame_times.append(frame_time)

                expected = REFS[rp1_mod](REFS[rp0_mod](frame))
                check_frame(f"chained {rp0_mod}->{rp1_mod} frame {idx}", result, expected)

                all_timing.append({
                    "test_name": test_name,
                    "frame_idx": idx,
                    "config": config_label,
                    "frame_time_s": frame_time,
                    "swap_latency_s": None,
                })
        finally:
            if hasattr(x_buf, "freebuffer"):
                x_buf.freebuffer()
            if hasattr(y_buf, "freebuffer"):
                y_buf.freebuffer()

        print_summary(test_name, config_label, frame_times, rows, cols)
        overlay.default_routing()


def test_video_midstream_swap(overlay, icap, cfg, all_timing):
    ext = ".bin" if icap else ".bit"
    rows, cols = cfg.rows, cfg.cols
    test_name = "test_midstream_swap"

    overlay.pr_download("rp0", f"rp0_gaussian3x3{ext}", icap=icap)
    overlay.pr_download("rp1", f"rp1_laplacian3x3{ext}", icap=icap)
    configure_partition(overlay, "rp0", rows, cols)
    configure_partition(overlay, "rp1", rows, cols)
    dma = overlay.chain(["rp0", "rp1"])

    x_buf = allocate(shape=rows * cols, dtype=np.int32)
    y_buf = allocate(shape=rows * cols, dtype=np.int32)
    swap_done = False
    swap_latency_s = None
    frame_times = []
    gallery_frames = []

    try:
        for idx, frame in video_source(cfg.source_dir, cfg.n_frames, rows, cols):
            if idx == cfg.swap_frame and not swap_done:
                t0 = time.perf_counter()
                overlay.pr_download("rp0", f"rp0_median3x3{ext}", icap=icap)
                overlay.pr_download("rp1", f"rp1_sobel_mag{ext}", icap=icap)
                configure_partition(overlay, "rp0", rows, cols)
                configure_partition(overlay, "rp1", rows, cols)
                # re-assert switch routing after decoupler interaction during PR
                dma = overlay.chain(["rp0", "rp1"])
                swap_latency_s = time.perf_counter() - t0
                swap_done = True

            t_frame_start = time.perf_counter()
            result = transfer_frame(dma, x_buf, y_buf, frame)
            frame_time = time.perf_counter() - t_frame_start
            frame_times.append(frame_time)

            if idx < cfg.swap_frame:
                expected = REFS["laplacian3x3"](REFS["gaussian3x3"](frame))
                config_label = "gaussian_laplacian"
            else:
                expected = REFS["sobel_mag"](REFS["median3x3"](frame))
                config_label = "median_sobel"

            check_frame(f"midswap frame {idx} [{config_label}]", result, expected)

            all_timing.append({
                "test_name": test_name,
                "frame_idx": idx,
                "config": config_label,
                "frame_time_s": frame_time,
                "swap_latency_s": swap_latency_s if idx == cfg.swap_frame else None,
            })

            if not cfg.skip_visual:
                if idx == cfg.swap_frame - 1 and cfg.swap_frame > 0:
                    gallery_frames.append((idx, config_label, ("gaussian3x3", "laplacian3x3"), frame, result, expected))
                elif idx == cfg.swap_frame:
                    gallery_frames.append((idx, config_label, ("median3x3", "sobel_mag"), frame, result, expected))
    finally:
        if hasattr(x_buf, "freebuffer"):
            x_buf.freebuffer()
        if hasattr(y_buf, "freebuffer"):
            y_buf.freebuffer()

    print_summary(
        test_name, "gaussian_laplacian -> median_sobel", frame_times, rows, cols,
        swap_info=(swap_latency_s, cfg.swap_frame) if swap_latency_s is not None else None,
    )

    if not cfg.skip_visual and gallery_frames:
        artifact_dir = Path(cfg.artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        input_frame = gallery_frames[0][4]
        cases = []
        for g_idx, g_config, g_modules, g_frame, g_result, g_expected in gallery_frames:
            cases.append({
                "label": f"frame_{g_idx}_{g_config}",
                "modules": g_modules,
                "actual": g_result,
                "expected": g_expected,
            })
        save_visual_gallery(str(artifact_dir), "midstream_swap_gallery", input_frame, cases)

    overlay.default_routing()


def main(dut=None):
    if COCOTB_IS_RUNNING:
        overlay = Overlay("design.bit")
        icap = False
        cfg = VideoConfig(
            n_frames=int(os.environ.get("VIDEO_FRAMES", 6)),
            rows=int(os.environ.get("VIDEO_ROWS", 16)),
            cols=int(os.environ.get("VIDEO_COLS", 32)),
            swap_frame=int(os.environ.get("VIDEO_SWAP_FRAME", -1)),
            skip_visual=env_flag("VIDEO_SKIP_VISUAL"),
            skip_timing=env_flag("VIDEO_SKIP_TIMING"),
            artifact_dir=os.environ.get("VIDEO_ARTIFACT_DIR", "video_artifacts"),
            source_dir=os.environ.get("VIDEO_SOURCE_DIR", ""),
        )
    else:
        parser = argparse.ArgumentParser(description="Video pipeline PR test")
        parser.add_argument("--project", required=True)
        parser.add_argument("--icap", action="store_true")
        parser.add_argument("--frames", type=int, default=int(os.environ.get("VIDEO_FRAMES", 30)))
        parser.add_argument("--rows", type=int, default=int(os.environ.get("VIDEO_ROWS", 240)))
        parser.add_argument("--cols", type=int, default=int(os.environ.get("VIDEO_COLS", 320)))
        parser.add_argument("--swap-frame", type=int, default=int(os.environ.get("VIDEO_SWAP_FRAME", -1)))
        parser.add_argument("--no-visual", action="store_true")
        parser.add_argument("--no-timing", action="store_true")
        parser.add_argument("--artifact-dir", default=os.environ.get("VIDEO_ARTIFACT_DIR", "video_artifacts"))
        parser.add_argument("--source-dir", default=os.environ.get("VIDEO_SOURCE_DIR", ""))
        args = parser.parse_args()
        overlay = Overlay(f"{args.project}.bit")
        icap = args.icap
        cfg = VideoConfig(
            n_frames=args.frames,
            rows=args.rows,
            cols=args.cols,
            swap_frame=args.swap_frame,
            skip_visual=args.no_visual,
            skip_timing=args.no_timing,
            artifact_dir=args.artifact_dir,
            source_dir=args.source_dir,
        )

    if cfg.swap_frame < 0:
        cfg = cfg._replace(swap_frame=cfg.n_frames // 2)

    all_timing = []
    test_video_chained(overlay, icap, cfg, all_timing)
    test_video_midstream_swap(overlay, icap, cfg, all_timing)

    if not cfg.skip_timing:
        write_timing_csv(all_timing, cfg.artifact_dir)

    print("\nAll video tests passed.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
