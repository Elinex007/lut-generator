import numpy as np
from typing import Optional
from scipy.interpolate import RegularGridInterpolator


LUT_SIZE = 33  # 33x33x33 standard


def _apply_reinhard_transfer(lut: np.ndarray, src_stats: dict, ref_stats: dict) -> np.ndarray:
    """
    Reinhard color transfer in Lab space.
    Maps source color statistics toward reference statistics.
    lut shape: (N*N*N, 3) in linear [0,1] RGB.
    """
    # Convert LUT RGB to Lab
    import cv2
    lut_u8 = np.clip(lut * 255, 0, 255).astype(np.uint8).reshape(1, -1, 3)
    lut_lab = cv2.cvtColor(lut_u8, cv2.COLOR_RGB2LAB).astype(np.float32).reshape(-1, 3)

    src_mean = src_stats["mean"]  # [L, a, b] in OpenCV Lab scale
    src_std  = src_stats["std"]
    ref_mean = ref_stats["mean"]
    ref_std  = ref_stats["std"]

    # Reinhard: shift and scale each channel
    for ch in range(3):
        if src_std[ch] > 1e-6:
            lut_lab[:, ch] = (lut_lab[:, ch] - src_mean[ch]) * (ref_std[ch] / src_std[ch]) + ref_mean[ch]
        else:
            lut_lab[:, ch] = lut_lab[:, ch] - src_mean[ch] + ref_mean[ch]

    lut_lab_u8 = np.clip(lut_lab, 0, 255).astype(np.uint8).reshape(1, -1, 3)
    lut_rgb = cv2.cvtColor(lut_lab_u8, cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return lut_rgb.astype(np.float32) / 255.0


def _apply_style_params(lut: np.ndarray, params: dict) -> np.ndarray:
    """
    Apply style parameters to the LUT (linear RGB [0,1]).
    lut shape: (N, 3)
    """
    r, g, b = lut[:, 0].copy(), lut[:, 1].copy(), lut[:, 2].copy()

    # --- Exposure ---
    exp = params.get("exposure", 0.0)
    factor = 2.0 ** exp
    r *= factor; g *= factor; b *= factor

    # --- Temperature shift (warm/cool) ---
    temp = params.get("temperature_shift", 0.0)
    if temp > 0:  # warm: more red/yellow, less blue
        r = r + temp * 0.12
        g = g + temp * 0.04
        b = b - temp * 0.10
    else:  # cool: more blue, less red
        r = r + temp * 0.10
        b = b - temp * 0.12

    # --- Tint shift (green/magenta) ---
    tint = params.get("tint_shift", 0.0)
    g = g - tint * 0.08
    r = r + tint * 0.04
    b = b + tint * 0.04

    # --- Contrast (S-curve around midpoint) ---
    contrast = params.get("contrast", 0.0)
    if contrast != 0.0:
        pivot = 0.42
        k = 1.0 + contrast * 0.8
        def s_curve(x):
            return pivot + (x - pivot) * k
        r = s_curve(r); g = s_curve(g); b = s_curve(b)

    # --- Highlights ---
    hl = params.get("highlights", 0.0)
    if hl != 0.0:
        mask = np.clip((r + g + b) / 3.0, 0, 1) ** 2
        r += hl * mask * 0.15
        g += hl * mask * 0.15
        b += hl * mask * 0.15

    # --- Shadows ---
    sh = params.get("shadows", 0.0)
    if sh != 0.0:
        mask = np.clip(1.0 - (r + g + b) / 3.0, 0, 1) ** 2
        r += sh * mask * 0.15
        g += sh * mask * 0.15
        b += sh * mask * 0.15

    # --- Shadow lift (matte/fade) ---
    lift = params.get("shadow_lift", 0.0)
    r = r * (1 - lift) + lift
    g = g * (1 - lift) + lift
    b = b * (1 - lift) + lift

    # --- Highlight roll-off (compression) ---
    roll = params.get("highlight_roll", 0.0)
    if roll > 0:
        ceiling = 1.0 - roll * 0.3
        def roll_off(x):
            return np.where(x > ceiling,
                            ceiling + (x - ceiling) / (1 + (x - ceiling) / roll),
                            x)
        r = roll_off(r); g = roll_off(g); b = roll_off(b)

    # --- Saturation ---
    sat = params.get("saturation", 0.0)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat_factor = 1.0 + sat
    r = luma + (r - luma) * sat_factor
    g = luma + (g - luma) * sat_factor
    b = luma + (b - luma) * sat_factor

    # --- Vibrance (boost less-saturated pixels more) ---
    vibrance = params.get("vibrance", 0.0)
    if vibrance != 0.0:
        luma2 = 0.2126 * r + 0.7152 * g + 0.0722 * b
        saturation_level = np.max(np.stack([r, g, b], axis=1), axis=1) - np.min(np.stack([r, g, b], axis=1), axis=1)
        vib_mask = 1.0 - saturation_level
        vib_factor = 1.0 + vibrance * vib_mask
        r = luma2 + (r - luma2) * vib_factor
        g = luma2 + (g - luma2) * vib_factor
        b = luma2 + (b - luma2) * vib_factor

    # --- Split tone ---
    sh_hue = params.get("split_tone_shadow_hue", 210)
    sh_str = params.get("split_tone_shadow_strength", 0.0)
    hl_hue = params.get("split_tone_highlight_hue", 35)
    hl_str = params.get("split_tone_highlight_strength", 0.0)

    if sh_str > 0 or hl_str > 0:
        def hue_to_rgb(h):
            h = h % 360
            h_norm = h / 60.0
            i = int(h_norm)
            f = h_norm - i
            vals = [1, f, 0, 0, 1-f, 1]
            mapping = [(0,1,2),(2,1,0),(2,0,1),(0,2,1),(1,2,0),(1,0,2)]
            segs = [vals[j] for j in mapping[i % 6]]
            return np.array(segs)

        luma3 = 0.2126 * r + 0.7152 * g + 0.0722 * b
        sh_rgb = hue_to_rgb(sh_hue)
        hl_rgb = hue_to_rgb(hl_hue)
        shadow_mask   = np.clip(1.0 - luma3 * 2, 0, 1)
        highlight_mask = np.clip(luma3 * 2 - 1, 0, 1)

        r += sh_str * shadow_mask * (sh_rgb[0] - 0.5) * 0.5
        g += sh_str * shadow_mask * (sh_rgb[1] - 0.5) * 0.5
        b += sh_str * shadow_mask * (sh_rgb[2] - 0.5) * 0.5
        r += hl_str * highlight_mask * (hl_rgb[0] - 0.5) * 0.5
        g += hl_str * highlight_mask * (hl_rgb[1] - 0.5) * 0.5
        b += hl_str * highlight_mask * (hl_rgb[2] - 0.5) * 0.5

    lut[:, 0] = r
    lut[:, 1] = g
    lut[:, 2] = b
    return np.clip(lut, 0.0, 1.0)


def build_lut(src_stats: dict, ref_stats: Optional[dict], style_params: dict, lut_name: str = "LUT") -> np.ndarray:
    """
    Build a 33x33x33 LUT array (shape: LUT_SIZE^3 x 3) in RGB [0,1].
    Order: R varies slowest, B fastest (standard .cube layout).
    """
    size = LUT_SIZE
    axis = np.linspace(0.0, 1.0, size)

    # Build identity LUT grid  (r, g, b) — .cube: B inner, G mid, R outer
    b_grid, g_grid, r_grid = np.meshgrid(axis, axis, axis, indexing='ij')
    lut = np.stack([r_grid.ravel(), g_grid.ravel(), b_grid.ravel()], axis=1).astype(np.float32)
    # Note: lut[:, 0]=R, lut[:, 1]=G, lut[:, 2]=B

    # 1. Reinhard color transfer from source → reference
    if ref_stats is not None:
        lut = _apply_reinhard_transfer(lut, src_stats, ref_stats)

    # 2. Apply style parameters
    lut = _apply_style_params(lut, style_params)

    return lut  # shape (size^3, 3)


def save_cube(lut: np.ndarray, output_path: str, lut_name: str = "Generated LUT") -> None:
    """Write a .cube file from lut array (shape N^3 x 3, RGB [0,1])."""
    size = LUT_SIZE
    lines = [
        f'TITLE "{lut_name}"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
        "",
    ]
    for row in lut:
        r, g, b = float(row[0]), float(row[1]), float(row[2])
        lines.append(f"{r:.6f} {g:.6f} {b:.6f}")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
