#!/usr/bin/env python3
from pathlib import Path
import sys


KERNELS = [
    ("gaussian3x3_hls", "gaussian3x3_top"),
    ("median3x3_hls", "median3x3_top"),
    ("laplacian3x3_hls", "laplacian3x3_top"),
    ("sobel_mag_hls", "sobel_mag_top"),
]


def rel_paths(root: Path, paths):
    return [p.relative_to(root).as_posix() for p in paths]


def gather_sources(root: Path):
    sources = []

    wrapper_dir = root / "rtl" / "wrappers"
    for _, top in KERNELS:
        sources.append(wrapper_dir / f"{top}.v")

    generated_dir = root / "rtl" / "generated"
    for kernel, _ in KERNELS:
        kernel_dir = generated_dir / kernel
        if not kernel_dir.exists():
            raise FileNotFoundError(f"Missing generated RTL directory: {kernel_dir}")

        for ext in ("*.v", "*.vh"):
            sources.extend(sorted(kernel_dir.glob(ext)))

    return rel_paths(root, sources)


def build_yaml(board: str, sources):
    project = f"vision_{board}"
    return "\n".join(
        [
            f"project: {project}",
            f"board: {board}",
            "reconfiguration_method: icap",
            "axis_switch: true",
            "",
            "sources:",
            *[f"  - {src}" for src in sources],
            "",
            "reconfigurable_partitions:",
            "  - partition_name: rp0",
            "    modules:",
            "      - cell_name: gaussian3x3",
            "        top: gaussian3x3_top",
            "      - cell_name: median3x3",
            "        top: median3x3_top",
            "",
            "  - partition_name: rp1",
            "    modules:",
            "      - cell_name: laplacian3x3",
            "        top: laplacian3x3_top",
            "      - cell_name: sobel_mag",
            "        top: sobel_mag_top",
            "",
        ]
    )


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"z1", "kv260"}:
        print("usage: generate_config.py <z1|kv260>", file=sys.stderr)
        raise SystemExit(1)

    board = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    sources = gather_sources(root)
    yaml_text = build_yaml(board, sources)
    output = root / f"pr_{board}.yaml"
    output.write_text(yaml_text)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
