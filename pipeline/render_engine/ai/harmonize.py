"""Colour harmonisation: pull every image in a set toward one anchor's colour statistics.

Diffusion models drift slightly in white balance and contrast from image to
image. Matching each image's mean and spread in CIELAB to an anchor (Reinhard
colour transfer) removes that drift. The geometry and local detail of each
image are untouched.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

# sRGB D65 <-> XYZ
_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_M_INV = np.linalg.inv(_M)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M.T / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _WHITE
    lin = np.clip(xyz @ _M_INV.T, 0, 1)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(np.round(c * 255), 0, 255).astype(np.uint8)


def lab_stats(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    small = img.convert("RGB").copy()
    small.thumbnail((512, 512))  # statistics don't need full resolution
    lab = srgb_to_lab(np.asarray(small)).reshape(-1, 3)
    return lab.mean(axis=0), lab.std(axis=0) + 1e-6


def match(img: Image.Image, anchor: Image.Image, strength: float = 1.0) -> Image.Image:
    if strength <= 0:
        return img.convert("RGB")
    src_mean, src_std = lab_stats(img)
    ref_mean, ref_std = lab_stats(anchor)
    target_mean = src_mean + (ref_mean - src_mean) * strength
    target_std = src_std + (ref_std - src_std) * strength
    lab = srgb_to_lab(np.asarray(img.convert("RGB")))
    lab = (lab - src_mean) / src_std * target_std + target_mean
    return Image.fromarray(lab_to_srgb(lab))


def harmonize_set(images: dict[str, Path], anchor: Path, out_dir: Path, strength: float) -> dict[str, Path]:
    """Write a colour-matched copy of each image into out_dir. The anchor itself is copied unchanged."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = Image.open(anchor).convert("RGB")
    result = {}
    for name, path in images.items():
        target = out_dir / path.name
        img = Image.open(path).convert("RGB")
        (img if path.resolve() == anchor.resolve() else match(img, ref, strength)).save(target)
        result[name] = target
    return result
