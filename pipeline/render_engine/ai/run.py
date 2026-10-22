"""Render a set of SketchUp view images through ComfyUI with one shared look."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import ConfigError
from .comfy import ComfyClient
from .graph import build_graph
from .harmonize import harmonize_set
from .settings import build_prompt, find_inputs, output_size, resolve_settings


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name).strip("_")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _pick_anchor(settings: dict[str, Any], raw: dict[str, Path]) -> Path:
    anchor = settings["preset"].get("harmonize", {}).get("anchor", "first")
    if anchor == "first":
        return next(iter(raw.values()))
    if anchor == "style_reference":
        ref = settings["preset"].get("style_reference")
        if not ref:
            raise ConfigError("harmonize.anchor is 'style_reference' but the preset has no style_reference")
        return Path(ref)
    if anchor not in raw:
        raise ConfigError(f"harmonize.anchor '{anchor}' is not one of the rendered views: {', '.join(raw)}")
    return raw[anchor]


def render_set(
    project_dir: Path,
    preset: str | None = None,
    fidelity: str | None = None,
    quality: str = "draft",
    engine: str | None = None,
    views: list[str] | None = None,
    comfy_url: str = "http://127.0.0.1:8188",
    dry_run: bool = False,
    log=print,
) -> Path:
    project_dir = project_dir.resolve()
    settings = resolve_settings(project_dir, preset, fidelity, quality, engine)
    inputs = find_inputs(project_dir, views)
    eng = settings["engine"]
    if "non-commercial" in eng.get("licence", "").lower():
        log(f"note: {settings['engine_name']} - {eng['licence']}")

    run_id = (f"{datetime.now():%Y%m%d-%H%M%S}_{settings['preset_name']}_{settings['fidelity_name']}"
              f"_{quality}_{settings['look_hash']}")
    run_dir = project_dir / "renders" / run_id
    (run_dir / "graphs").mkdir(parents=True)
    log(f"run: {run_dir}  (look {settings['look_hash']})")

    client = None
    ref = settings["preset"].get("style_reference")
    if dry_run:
        settings["_style_reference_name"] = Path(ref).name if ref else None
    else:
        client = ComfyClient(comfy_url)
        client.ping()
        if ref:
            settings["_style_reference_name"] = client.upload_image(
                Path(ref), f"re_ref_{settings['look_hash']}{Path(ref).suffix}")

    raw: dict[str, Path] = {}
    records: dict[str, dict[str, Any]] = {}
    for src in inputs:
        view = src.stem
        name = safe_name(view)
        with Image.open(src) as im:
            in_size = im.size
        size = output_size(*in_size, settings["megapixels"], int(eng["multiple_of"]))
        prompt = build_prompt(settings, view)
        upload_name = f"re_{settings['look_hash']}_{name}{src.suffix.lower()}"
        graph = build_graph(settings, prompt, upload_name, size, f"render_engine/{run_id}/{name}")
        (run_dir / "graphs" / f"{name}.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
        records[view] = {
            "view": view,
            "view_type": prompt["view_type"],
            "input": src.name,
            "input_sha256": _sha256(src),
            "input_size": list(in_size),
            "generated_size": list(size),
            "prompt": prompt,
        }
        if client is None:
            continue

        log(f"{view}: {size[0]}x{size[1]} ...")
        t0 = time.time()
        client.upload_image(src, upload_name)
        entry = client.wait(client.queue(graph))
        images = client.output_images(entry)
        if not images:
            raise ConfigError(f"ComfyUI returned no image for {view}")
        raw[view] = client.download(images[0], run_dir / "raw" / f"{name}.png")
        records[view]["render_seconds"] = round(time.time() - t0, 1)
        log(f"{view}: done in {records[view]['render_seconds']}s")

    if client is not None:
        harm = settings["preset"].get("harmonize") or {}
        if harm.get("enabled", True) and len(raw) > 1 and float(harm.get("strength", 0)) > 0:
            anchor = _pick_anchor(settings, raw)
            final = harmonize_set(raw, anchor, run_dir, float(harm["strength"]))
            for view in final:
                records[view]["harmonized_to"] = anchor.name
        else:
            final = {}
            for view, path in raw.items():
                final[view] = run_dir / path.name
                shutil.copyfile(path, final[view])
        for view, path in final.items():
            records[view]["image"] = path.name

    public = {k: v for k, v in settings.items() if not k.startswith("_")}
    (run_dir / "settings.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    for view, rec in records.items():
        manifest = {
            **rec,
            "look_hash": settings["look_hash"],
            "renderer": f"comfyui:{settings['engine_name']}",
            "preset": settings["preset_name"],
            "fidelity": settings["fidelity_name"],
            "quality": quality,
            "seed": settings["seed"],
            "dry_run": dry_run,
        }
        (run_dir / f"{safe_name(view)}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return run_dir
