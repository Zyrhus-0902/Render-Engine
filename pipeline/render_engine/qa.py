"""Consistency checks on a finished render set (needs Pillow)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def check_run(run_dir: Path) -> dict[str, Any]:
    """All images in a run (or several runs) must share one look hash."""
    manifests = [json.loads(p.read_text()) for p in sorted(run_dir.rglob("*.json")) if p.name != "job.json"]
    manifests = [m for m in manifests if "look_hash" in m]
    hashes = sorted({m["look_hash"] for m in manifests})
    versions = sorted({m["blender_version"] for m in manifests})
    return {
        "images": len(manifests),
        "look_hashes": hashes,
        "blender_versions": versions,
        "consistent": len(hashes) <= 1 and len(versions) <= 1,
    }


def alignment_overlays(run_dir: Path, export_dir: Path) -> list[Path]:
    """Blend each render 50/50 with the SketchUp reference image of the same scene.

    If the geometry, camera and lens are right, edges line up exactly.
    """
    from PIL import Image, ImageChops, ImageOps

    out = []
    for manifest_path in sorted(run_dir.glob("*.json")):
        if manifest_path.name == "job.json":
            continue
        m = json.loads(manifest_path.read_text())
        ref_rel = m["camera"].get("reference_image")
        if not ref_rel or not (export_dir / ref_rel).exists():
            continue
        render = Image.open(run_dir / m["image"]).convert("RGB")
        ref = Image.open(export_dir / ref_rel).convert("RGB").resize(render.size)
        blend = Image.blend(render, ref, 0.5)
        edges = ImageChops.difference(ImageOps.grayscale(render), ImageOps.grayscale(ref))
        target = run_dir / "qa" / f"{manifest_path.stem}_overlay.jpg"
        target.parent.mkdir(exist_ok=True)
        blend.save(target, quality=90)
        edges.save(run_dir / "qa" / f"{manifest_path.stem}_diff.jpg", quality=90)
        out.append(target)
    return out


def contact_sheet(run_dir: Path, columns: int = 3, thumb_width: int = 600) -> Path | None:
    """One sheet with every view side by side - the fastest visual consistency check."""
    from PIL import Image, ImageDraw

    images = sorted(p for p in run_dir.iterdir() if p.suffix.lower() in (".png", ".jpg"))
    if not images:
        return None
    thumbs = []
    for p in images:
        im = Image.open(p).convert("RGB")
        im.thumbnail((thumb_width, thumb_width * 4))
        thumbs.append((p.stem, im))
    th = max(im.height for _, im in thumbs) + 28
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * th), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(thumbs):
        x, y = (i % columns) * thumb_width, (i // columns) * th
        sheet.paste(im, (x, y))
        draw.text((x + 6, y + im.height + 6), name, fill="black")
    target = run_dir / "qa" / "contact_sheet.jpg"
    target.parent.mkdir(exist_ok=True)
    sheet.save(target, quality=90)
    return target
