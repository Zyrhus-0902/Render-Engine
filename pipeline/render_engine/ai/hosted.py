"""Hosted render set (fal.ai multi-reference editing models).

Order of work for one set:
  1. Hero view first: view image + material colour key + texture swatches -> render.
  2. Every other view gets the hero render as an extra reference
     ("same building, match its materials, colours and light exactly").
  3. Shade lock: with colour keys, each material region in every view is pulled to
     the hero's colour for that material. Views without a key get a global colour match.
  4. Scorecard: material colour difference across views + geometry edge fidelity.
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..config import MATERIALS_DIR, ConfigError, load_material_library
from ..materials import normalize_name
from .colorkey import colour_name, material_masks, region_stats, shade_lock
from .fal import FalClient, data_uri
from .harmonize import match
from .run import safe_name
from .settings import build_prompt, find_inputs, key_image_for, resolve_settings

MIN_MATERIAL_SHARE = 0.002  # materials covering less of the frame are left out of the prompt


def _library() -> dict[str, dict[str, Any]]:
    return {normalize_name(k): v for k, v in load_material_library()["materials"].items()}


def build_hosted_prompt(settings: dict[str, Any], view: str, key_materials: list[tuple[str, str]],
                        hero_index: int | None, swatch_refs: list[tuple[int, str]]) -> str:
    """key_materials: [(hex, material id)] present in this view's key (image 2)."""
    base = build_prompt(settings, view)
    lib = _library()
    phrase = settings["views"]["types"][base["view_type"]]
    lines = [
        f"Image 1 is a SketchUp view. Turn it into a photorealistic {phrase}.",
        "Keep the building geometry, camera position, framing, proportions and every door, window and "
        "opening exactly as in image 1. Do not add, remove or move any building element.",
        f"Scene: {settings['preset'].get('scene', '')}.",
    ]
    if settings["context"]:
        lines.append(f"Setting: {settings['context']}.")
    if key_materials:
        parts = [f"{colour_name(h)} ({h}) areas are {lib[m].get('prompt', m.lower())}" for h, m in key_materials]
        lines.append("Image 2 is a material map of image 1: " + "; ".join(parts) + ".")
    elif settings["materials"]:
        lines.append("Materials: " + ", ".join(settings["materials"]) + ".")
    if hero_index:
        lines.append(f"Image {hero_index} is the approved render of the same building from another viewpoint: "
                     "use exactly the same materials, colours, textures, lighting, sky and time of day.")
    for idx, mat in swatch_refs:
        lines.append(f"Image {idx} is a texture sample of the {lib[mat].get('prompt', mat.lower())}.")
    extra = (settings["view_overrides"].get(view) or {}).get("prompt")
    if extra:
        lines.append(extra.rstrip(".") + ".")
    lines.append(settings["views"].get("suffix", "").capitalize().rstrip(".") + ".")
    return " ".join(lines)


def _fit(path: Path, size: tuple[int, int]) -> tuple[Image.Image, float]:
    """Resize a model output back to the input frame. Returns the image and the aspect error."""
    img = Image.open(path).convert("RGB")
    err = abs((img.width / img.height) / (size[0] / size[1]) - 1)
    return img.resize(size, Image.LANCZOS), err


def render_set_hosted(
    project_dir: Path,
    preset: str | None = None,
    quality: str = "draft",
    engine: str | None = None,
    views: list[str] | None = None,
    hero_from: Path | None = None,
    dry_run: bool = False,
    client: FalClient | None = None,
    log=print,
) -> Path:
    project_dir = project_dir.resolve()
    settings = resolve_settings(project_dir, preset, None, quality, engine)
    eng = settings["engine"]
    inputs = find_inputs(project_dir, views)
    legend = settings["color_key"]
    lib = _library()

    hero = settings["hero"] or inputs[0].stem
    hero_img: Path | None = None
    if hero_from:
        hero_img = Path(hero_from) / f"{safe_name(hero)}.png"
        if not hero_img.exists():
            raise ConfigError(f"approved hero render not found: {hero_img}")
        inputs = [p for p in inputs if p.stem != hero]
    else:
        names = [p.stem for p in inputs]
        if hero not in names:
            all_names = [p.stem for p in find_inputs(project_dir)]
            if hero not in all_names:
                raise ConfigError(f"hero view '{hero}' not found in input/")
            raise ConfigError(f"hero view '{hero}' is not in --views; add it, or pass --hero-from <run> to reuse an approved hero")
        inputs.sort(key=lambda p: p.stem != hero)

    run_id = f"{datetime.now():%Y%m%d-%H%M%S}_{settings['preset_name']}_{settings['engine_name']}_{quality}_{settings['look_hash']}"
    run_dir = project_dir / "renders" / run_id
    n = 2
    while run_dir.exists():  # two runs in the same second (e.g. hero, then --hero-from)
        run_dir = project_dir / "renders" / f"{run_id}-{n}"
        n += 1
    (run_dir / "requests").mkdir(parents=True)
    log(f"run: {run_dir}  (look {settings['look_hash']}, hero: {hero})")
    if not dry_run and client is None:
        client = FalClient()

    finals: dict[str, Path] = {}
    masks_by_view: dict[str, dict[str, np.ndarray]] = {}
    records: dict[str, dict[str, Any]] = {}

    for src in inputs:
        view, name = src.stem, safe_name(src.stem)
        with Image.open(src) as im:
            size = im.size
        refs: list[tuple[Path, str]] = [(src, "view")]
        key_materials: list[tuple[str, str]] = []
        key = key_image_for(src) if legend else None
        if key:
            masks = material_masks(key, legend, size)
            masks_by_view[view] = masks
            present = {m for m, mk in masks.items() if mk.mean() >= MIN_MATERIAL_SHARE}
            key_materials = [(h, m) for h, m in legend.items() if m in present]
            refs.append((key, "material key"))
        hero_index = None
        if view != hero and hero_img:
            refs.append((hero_img, "hero render"))
            hero_index = len(refs)
        swatch_refs: list[tuple[int, str]] = []
        for _, mat in key_materials:
            swatch = lib[mat].get("swatch")
            if swatch and len(refs) < int(eng.get("max_images", 4)) and (MATERIALS_DIR / swatch).exists():
                refs.append((MATERIALS_DIR / swatch, f"swatch {mat}"))
                swatch_refs.append((len(refs), mat))

        prompt = build_hosted_prompt(settings, view, key_materials, hero_index, swatch_refs)
        request = {**eng.get("args", {}), "prompt": prompt}
        if eng.get("seed_field"):
            request[eng["seed_field"]] = settings["seed"]
        logged = {**request, eng["image_field"]: [f"{p.name} ({role})" for p, role in refs]}
        (run_dir / "requests" / f"{name}.json").write_text(json.dumps(logged, indent=2), encoding="utf-8")
        records[view] = {"view": view, "input": src.name, "key": key.name if key else None,
                         "references": logged[eng["image_field"]], "prompt": {"positive": prompt},
                         "input_size": list(size), "is_hero": view == hero}
        if dry_run:
            continue

        log(f"{view}: {len(refs)} reference image(s) -> {eng['model']} ...")
        t0 = time.time()
        request[eng["image_field"]] = [data_uri(p) for p, _ in refs]
        result = client.run(eng["model"], request)
        images = result.get("images") or []
        if not images:
            raise ConfigError(f"{eng['model']} returned no image for {view}: {json.dumps(result)[:300]}")
        raw = client.download(images[0]["url"], run_dir / "raw" / f"{name}.png")
        fitted, aspect_err = _fit(raw, size)
        fitted.save(run_dir / "raw" / f"{name}.png")
        records[view].update(render_seconds=round(time.time() - t0, 1), aspect_error=round(aspect_err, 4))
        if aspect_err > 0.02:
            log(f"{view}: warning - model changed the aspect ratio by {aspect_err:.1%}; resized back to the input frame")
        finals[view] = run_dir / "raw" / f"{name}.png"
        if view == hero:
            hero_img = finals[view]
        log(f"{view}: done in {records[view]['render_seconds']}s")

    if not dry_run:
        _lock_and_save(settings, hero, hero_img, finals, masks_by_view, run_dir, records, project_dir)

    for view, rec in records.items():
        manifest = {**rec, "look_hash": settings["look_hash"], "renderer": f"fal:{settings['engine_name']}",
                    "model": eng["model"], "preset": settings["preset_name"], "quality": quality,
                    "seed": settings["seed"] if eng.get("seed_field") else None, "dry_run": dry_run}
        (run_dir / f"{safe_name(view)}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    public = {k: v for k, v in settings.items() if not k.startswith("_")}
    (run_dir / "settings.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return run_dir


def _lock_and_save(settings, hero, hero_img, finals, masks_by_view, run_dir, records, project_dir) -> None:
    lock = settings["shade_lock"]
    hero_render = Image.open(hero_img).convert("RGB") if hero_img else None

    targets: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if lock.get("enabled") and settings["color_key"]:
        if lock.get("source") == "library":
            from .harmonize import srgb_to_lab
            from .colorkey import hex_to_rgb
            lib = _library()
            for mat in set(settings["color_key"].values()):
                lab = srgb_to_lab(np.array([[hex_to_rgb(lib[mat]["base_color"])]], dtype=np.uint8))[0, 0]
                targets[mat] = (lab, None)
        elif hero_render is not None:
            hero_masks = masks_by_view.get(hero)
            if hero_masks is None:
                hero_key = key_image_for(project_dir / "input" / records.get(hero, {}).get("input", f"{hero}.png"))
                if hero_key:
                    hero_masks = material_masks(hero_key, settings["color_key"], hero_render.size)
            for mat, mask in (hero_masks or {}).items():
                stats = region_stats(hero_render, mask)
                if stats:
                    targets[mat] = stats

    harm = settings["preset"].get("harmonize") or {}
    for view, path in finals.items():
        img = Image.open(path).convert("RGB")
        if view != hero or lock.get("source") == "library":
            masks = masks_by_view.get(view)
            if masks and targets:
                resolved = {m: (t[0], t[1] if t[1] is not None else (region_stats(img, masks[m]) or (0, 1))[1])
                            for m, t in targets.items() if m in masks}
                img = shade_lock(img, masks, resolved, float(lock.get("strength", 0.85)))
                records[view]["shade_locked"] = sorted(resolved)
            elif hero_render is not None and view != hero and harm.get("enabled", True):
                img = match(img, hero_render, float(harm.get("strength", 0.7)))
                records[view]["harmonized_to"] = hero
        target = run_dir / path.name
        img.save(target)
        records[view]["image"] = target.name
    if hero_img and hero not in finals:  # reused approved hero: include it in the set for scoring
        shutil.copyfile(hero_img, run_dir / hero_img.name)
        records[hero] = {"view": hero, "input": f"{hero}.png", "image": hero_img.name, "is_hero": True,
                         "reused_from": str(hero_img.parent)}
