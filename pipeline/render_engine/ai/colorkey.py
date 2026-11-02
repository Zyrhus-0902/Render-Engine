"""Material colour keys: a flat-colour SketchUp export where each material has its own colour.

  input/EXT-01 Entrance.png       the normal view
  input/EXT-01 Entrance.key.png   same view, textures/edges/shadows off, one pure colour per material

project.yaml maps the colours to library materials:
  ai:
    color_key: {"#FF0000": WOOD_CEDAR_CLADDING, "#0000FF": GLASS_CLEAR, ...}

From the key we get exact per-material masks, which drive the prompt
("areas coloured red are cedar cladding"), the shade lock (same colour per
material in every view) and the consistency score.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .harmonize import lab_to_srgb, srgb_to_lab

BASIC_COLOURS = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "magenta": (255, 0, 255), "cyan": (0, 255, 255), "orange": (255, 128, 0), "purple": (128, 0, 255),
    "pink": (255, 128, 192), "lime": (128, 255, 0), "teal": (0, 128, 128), "brown": (128, 64, 0),
    "navy": (0, 0, 128), "olive": (128, 128, 0), "maroon": (128, 0, 0), "white": (255, 255, 255),
    "black": (0, 0, 0), "grey": (128, 128, 128),
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def colour_name(hex_color: str) -> str:
    rgb = np.array(hex_to_rgb(hex_color))
    return min(BASIC_COLOURS, key=lambda n: np.sum((np.array(BASIC_COLOURS[n]) - rgb) ** 2))


def material_masks(key_image: Path, legend: dict[str, str], size: tuple[int, int],
                   tolerance: float = 30.0) -> dict[str, np.ndarray]:
    """Boolean mask per material id. Each pixel goes to the nearest legend colour in
    CIELAB if within `tolerance` (Delta E), which absorbs SketchUp's face shading."""
    key = Image.open(key_image).convert("RGB").resize(size, Image.NEAREST)
    lab = srgb_to_lab(np.asarray(key)).reshape(-1, 3)
    colours = list(legend)
    refs = srgb_to_lab(np.array([hex_to_rgb(c) for c in colours], dtype=np.uint8)[None])[0]
    # compare chroma at full weight, lightness at half weight: shading mostly changes L
    weights = np.array([0.5, 1.0, 1.0])
    dist = np.sqrt((((lab[:, None, :] - refs[None, :, :]) * weights) ** 2).sum(-1))
    nearest = dist.argmin(1)
    ok = dist[np.arange(len(lab)), nearest] <= tolerance
    masks: dict[str, np.ndarray] = {}
    for i, colour in enumerate(colours):
        m = ((nearest == i) & ok).reshape(size[1], size[0])
        mat = legend[colour]
        masks[mat] = masks[mat] | m if mat in masks else m
    return masks


def erode(mask: np.ndarray, px: int) -> np.ndarray:
    """Shrink a mask so statistics ignore boundary pixels where materials meet."""
    if px <= 0:
        return mask
    img = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(px * 2 + 1))
    return np.asarray(img) > 127


def region_stats(img: Image.Image, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    core = erode(mask, 2)
    if core.sum() < 200:
        return None
    lab = srgb_to_lab(np.asarray(img.convert("RGB")))[core]
    return lab.mean(0), lab.std(0) + 1e-6


def shade_lock(img: Image.Image, masks: dict[str, np.ndarray],
               targets: dict[str, tuple[np.ndarray, np.ndarray]], strength: float) -> Image.Image:
    """Move each material region's colour statistics toward its target (mean fully,
    spread half-way, so texture contrast survives), with feathered edges."""
    lab = srgb_to_lab(np.asarray(img.convert("RGB")))
    out = lab.copy()
    for mat, mask in masks.items():
        if mat not in targets:
            continue
        stats = region_stats(img, mask)
        if stats is None:
            continue
        mean, std = stats
        t_mean, t_std = targets[mat]
        scale = 1 + (t_std / std - 1) * 0.5 * strength
        shifted = (lab - mean) * scale + mean + (t_mean - mean) * strength
        alpha = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255)
                           .filter(ImageFilter.GaussianBlur(2))).astype(np.float64)[..., None] / 255
        out = out * (1 - alpha) + shifted * alpha
    return Image.fromarray(lab_to_srgb(out))
