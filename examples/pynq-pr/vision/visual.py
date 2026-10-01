from pathlib import Path
import re
import struct
import zlib

import numpy as np

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None


GALLERY_ORDER = [
    "input",
    "gaussian3x3",
    "median3x3",
    "laplacian3x3",
    "sobel_mag",
    "median->sobel",
    "median->laplacian",
    "gaussian->laplacian",
]


def load_grayscale_image(path, rows=72, cols=96):
    if Image is None:
        raise RuntimeError("Pillow is required to load JPEG visual test images")

    resample = getattr(Image, "Resampling", Image).LANCZOS
    with Image.open(path) as image:
        gray = image.convert("L").resize((cols, rows), resample)
        return np.asarray(gray, dtype=np.uint8).copy()


def save_visual_gallery(output_dir, source_name, input_frame, cases):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_source = _safe_label(Path(source_name).stem)
    paths = {
        "python_png": output_dir / f"{safe_source}_python.png",
        "accelerated_png": output_dir / f"{safe_source}_accelerated.png",
        "diff_png": output_dir / f"{safe_source}_diff.png",
        "metrics": output_dir / f"{safe_source}_metrics.txt",
    }

    accelerated_items = [("input", input_frame)]
    python_items = [("input", input_frame)]
    diff_items = [("input", np.zeros_like(input_frame, dtype=np.uint8))]
    metric_lines = [
        f"source={source_name}",
        f"shape={input_frame.shape[0]}x{input_frame.shape[1]}",
        "gallery_order=" + ",".join(GALLERY_ORDER),
        f"python={paths['python_png'].name}",
        f"accelerated={paths['accelerated_png'].name}",
        f"diff={paths['diff_png'].name}",
    ]
    max_mismatch = 0

    for case in cases:
        label = case["label"]
        actual = case["actual"]
        expected = case["expected"]
        diff = np.abs(actual.astype(np.int16) - expected.astype(np.int16)).astype(np.uint8)
        diff_vis = np.minimum(diff.astype(np.uint16) * 16, 255).astype(np.uint8)

        accelerated_items.append((label, actual))
        python_items.append((label, expected))
        diff_items.append((label, diff_vis))

        mismatch_count = int(np.count_nonzero(diff))
        max_abs_diff = int(diff.max()) if diff.size else 0
        max_mismatch = max(max_mismatch, mismatch_count)
        metric_lines.append(
            f"{label}: modules={','.join(case['modules'])} "
            f"mismatch_count={mismatch_count} max_abs_diff={max_abs_diff}"
        )

    _write_png_rgb(paths["python_png"], _make_gallery(python_items))
    _write_png_rgb(paths["accelerated_png"], _make_gallery(accelerated_items))
    _write_png_rgb(paths["diff_png"], _make_gallery(diff_items))
    paths["metrics"].write_text("\n".join(metric_lines + [""]), encoding="utf-8")

    return {
        "mismatch_count": max_mismatch,
        "paths": paths,
    }


def _safe_label(label):
    label = label.replace("->", "_")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")


def _write_png_rgb(path, rgb):
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    rows, cols, channels = rgb.shape
    if channels != 3:
        raise ValueError("PNG RGB writer expects an RGB image")
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(rows))
    data = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", cols, rows, 8, 2, 0, 0, 0))
    data += _png_chunk(b"IDAT", zlib.compress(raw))
    data += _png_chunk(b"IEND", b"")
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + data)


def _png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _gray_rgb(image):
    image = np.asarray(image, dtype=np.uint8)
    return np.repeat(image[:, :, None], 3, axis=2)


def _scale_rgb(rgb, scale):
    return np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)


def _make_gallery(items):
    scale = 4
    columns = 4
    label_h = 20
    pad = 8
    tile_h, tile_w = items[0][1].shape
    cell_w = tile_w * scale
    cell_h = tile_h * scale + label_h
    rows = (len(items) + columns - 1) // columns
    canvas = np.full(
        (
            rows * cell_h + (rows + 1) * pad,
            columns * cell_w + (columns + 1) * pad,
            3,
        ),
        255,
        dtype=np.uint8,
    )

    for idx, (label, image) in enumerate(items):
        row = idx // columns
        col = idx % columns
        y = pad + row * (cell_h + pad)
        x = pad + col * (cell_w + pad)
        tile = _scale_rgb(_gray_rgb(image), scale)
        canvas[y + label_h:y + label_h + tile.shape[0], x:x + tile.shape[1]] = tile

    if Image is not None and ImageDraw is not None:
        pil_image = Image.fromarray(canvas, mode="RGB")
        draw = ImageDraw.Draw(pil_image)
        for idx, (label, _image) in enumerate(items):
            row = idx // columns
            col = idx % columns
            y = pad + row * (cell_h + pad) + 3
            x = pad + col * (cell_w + pad)
            draw.text((x, y), label, fill=(0, 0, 0))
        return np.asarray(pil_image, dtype=np.uint8)

    return canvas
