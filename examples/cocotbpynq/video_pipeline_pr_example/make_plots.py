"""Generate plots for everything: scenario overview grid, per-RM atlas,
and side-by-side input/output comparisons. Run after `python run.py`.
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

import test_pynq as tp


OUT = Path(__file__).resolve().parent / "out"
PLOTS = OUT / "plots"
PLOTS.mkdir(parents=True, exist_ok=True)


def load_ppm(path):
    with open(path, "rb") as f:
        assert f.readline().strip() == b"P6"
        wh = f.readline().strip()
        while wh.startswith(b"#"):
            wh = f.readline().strip()
        w, h = map(int, wh.split())
        assert f.readline().strip() == b"255"
        data = f.read()
    return np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)


def u32_to_rgb(img):
    return np.dstack([(img >> 16) & 0xFF, (img >> 8) & 0xFF, img & 0xFF]).astype(np.uint8)


# ─────────────────────────── 1. scenario overview ─────────────────────────────
SCENARIOS = [
    ("input",                          "input.ppm",                                "input"),
    ("1: all_identity",                "scenario_1_all_identity.ppm",              "color_identity → spatial_id → tone_id\n→ palette_id → stylize_id → finalize_id"),
    ("2: grayscale_only",              "scenario_2_grayscale_only.ppm",            "color_grayscale"),
    ("3: grayscale_edge",              "scenario_3_grayscale_edge.ppm",            "color_grayscale → spatial_edge33"),
    ("4: sepia_bright_pixelate",       "scenario_4_sepia_bright_pixelate.ppm",     "color_sepia → tone_brighten → stylize_pixelate"),
    ("5: full_six_stage",              "scenario_5_full_six_stage.ppm",            "sepia → blur33 → brighten → red_only\n→ posterize → gamma_lut"),
    ("6a: color→spatial",              "scenario_6_order_color_then_spatial.ppm",  "color_sepia → spatial_edge33"),
    ("6b: spatial→color",              "scenario_6_order_spatial_then_color.ppm",  "spatial_edge33 → color_sepia"),
    ("7 pre: gray + blur",             "scenario_7_pre_reconfig.ppm",              "color_grayscale → spatial_blur33"),
    ("7 post: gray + edge (reconfig)", "scenario_7_post_reconfig.ppm",             "color_grayscale → spatial_edge33"),
    ("8: subset (tone + finalize)",    "scenario_8_subset_tone_finalize.ppm",      "tone_brighten → finalize_gamma_lut"),
]

cols = 4
rows = (len(SCENARIOS) + cols - 1) // cols
fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
axes = axes.flatten()
for ax in axes:
    ax.axis("off")
for ax, (title, ppm_name, chain_str) in zip(axes, SCENARIOS):
    path = OUT / ppm_name
    if not path.exists():
        ax.set_title(f"{title}\n(missing)", fontsize=9, color="red")
        continue
    img = load_ppm(path)
    ax.imshow(img)
    ax.set_title(f"{title}\n{chain_str}", fontsize=8)
fig.suptitle("All 8 scenarios — 128×128 Grace Hopper photo", fontsize=14, y=1.00)
fig.tight_layout()
fig.savefig(PLOTS / "00_overview.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"saved {PLOTS / '00_overview.png'}")


# ─────────────────────────── 2. per-RM atlas ──────────────────────────────────
# For each partition, show the input image transformed by every RM variant.
# Uses the numpy reference (which is bit-exact equal to FPGA output per scenario
# verification), so each row exercises every RM in that partition.
in_img = tp.make_test_pattern()

PARTITION_RMS = [
    ("rp_color",    ["color_identity",    "color_grayscale", "color_sepia",     "color_invert"]),
    ("rp_spatial",  ["spatial_identity",  "spatial_blur33",  "spatial_sharpen33","spatial_edge33"]),
    ("rp_tone",     ["tone_identity",     "tone_brighten",   "tone_darken",     "tone_threshold"]),
    ("rp_palette",  ["palette_identity",  "palette_red_only","palette_bw_dither","palette_retro_4bit"]),
    ("rp_stylize",  ["stylize_identity",  "stylize_posterize","stylize_pixelate","stylize_vignette"]),
    ("rp_finalize", ["finalize_identity", "finalize_clamp_tv","finalize_gain_1p5x","finalize_gamma_lut"]),
]

fig, axes = plt.subplots(len(PARTITION_RMS), 5, figsize=(15, 3 * len(PARTITION_RMS)))
for r, (part_name, rms) in enumerate(PARTITION_RMS):
    axes[r, 0].imshow(u32_to_rgb(in_img))
    axes[r, 0].set_ylabel(part_name, fontsize=12, fontweight="bold")
    axes[r, 0].set_xticks([])
    axes[r, 0].set_yticks([])
    if r == 0:
        axes[r, 0].set_title("input", fontsize=10)
    for c, rm in enumerate(rms, 1):
        out = tp.REF[rm](in_img)
        axes[r, c].imshow(u32_to_rgb(out))
        axes[r, c].axis("off")
        axes[r, c].set_title(rm, fontsize=9)
fig.suptitle("24-RM atlas: every reconfigurable variant applied to input",
             fontsize=14, y=1.00)
fig.tight_layout()
fig.savefig(PLOTS / "01_rm_atlas.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"saved {PLOTS / '01_rm_atlas.png'}")


# ─────────────────────────── 3. side-by-side: input vs output vs diff ─────────
input_img = load_ppm(OUT / "input.ppm")

side_pairs = [(t, n) for (t, n, _) in SCENARIOS if n != "input.ppm"]

cols = 3
rows = len(side_pairs)
fig, axes = plt.subplots(rows, cols, figsize=(3 * cols, 3 * rows))
for r, (title, ppm_name) in enumerate(side_pairs):
    out_img = load_ppm(OUT / ppm_name)
    diff    = np.abs(out_img.astype(np.int16) - input_img.astype(np.int16)).astype(np.uint8)
    axes[r, 0].imshow(input_img); axes[r, 0].set_title("input" if r == 0 else "", fontsize=9); axes[r, 0].axis("off")
    axes[r, 1].imshow(out_img);   axes[r, 1].set_title(title, fontsize=9);                     axes[r, 1].axis("off")
    axes[r, 2].imshow(diff);      axes[r, 2].set_title("|diff|" if r == 0 else "", fontsize=9); axes[r, 2].axis("off")
fig.tight_layout()
fig.savefig(PLOTS / "02_side_by_side.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"saved {PLOTS / '02_side_by_side.png'}")


# ─────────────────────────── 4. fpga vs numpy ref check ───────────────────────
# Show fpga output and numpy ref side by side — they should be identical.
ref_pairs = [
    ("scenario_5_full_six_stage", "scenario_5_full_six_stage_ref"),
    ("scenario_3_grayscale_edge", "scenario_3_grayscale_edge_ref"),
    ("scenario_4_sepia_bright_pixelate", "scenario_4_sepia_bright_pixelate_ref"),
    ("scenario_6_order_spatial_then_color", "scenario_6_order_spatial_then_color_ref"),
]
fig, axes = plt.subplots(len(ref_pairs), 3, figsize=(9, 3 * len(ref_pairs)))
for r, (fpga, ref) in enumerate(ref_pairs):
    fpga_img = load_ppm(OUT / f"{fpga}.ppm")
    ref_img  = load_ppm(OUT / f"{ref}.ppm")
    diff = np.abs(fpga_img.astype(np.int16) - ref_img.astype(np.int16)).astype(np.uint8)
    axes[r, 0].imshow(fpga_img); axes[r, 0].set_title(f"{fpga}\n(sim)",   fontsize=8); axes[r, 0].axis("off")
    axes[r, 1].imshow(ref_img);  axes[r, 1].set_title("numpy ref",         fontsize=8); axes[r, 1].axis("off")
    axes[r, 2].imshow(diff * 32, vmin=0, vmax=255); axes[r, 2].set_title(f"|diff| ×32 (max={int(diff.max())})", fontsize=8); axes[r, 2].axis("off")
fig.suptitle("FPGA simulation vs numpy reference — pixel-exact equality", fontsize=12, y=1.00)
fig.tight_layout()
fig.savefig(PLOTS / "03_fpga_vs_numpy.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"saved {PLOTS / '03_fpga_vs_numpy.png'}")

print("done.")
