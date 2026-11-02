"""Resolve every generation setting for one render set.

Layers, lowest to highest priority:
  config/ai/engines.yaml        model files and sampler for the chosen engine
  config/ai/fidelity.yaml       how tightly the output follows the input image
  config/ai/quality.yaml        draft / final (speed only, never the look)
  config/ai/presets/<p>.yaml    scene setting: light, sky, weather, mood (supports `extends`)
  <project>/project.yaml `ai:`  site context, material palette, per-view tweaks
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..cameras import view_type_for
from ..config import CONFIG_DIR, ConfigError, deep_merge, load_material_library, load_yaml
from ..materials import normalize_name

AI_DIR = CONFIG_DIR / "ai"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def available_presets() -> list[str]:
    return sorted(p.stem for p in (AI_DIR / "presets").glob("*.yaml") if not p.stem.startswith("_"))


def load_preset(name: str, _seen: tuple[str, ...] = ()) -> dict[str, Any]:
    path = AI_DIR / "presets" / f"{name}.yaml"
    if not path.exists():
        raise ConfigError(f"unknown preset '{name}'. Available: {', '.join(available_presets())}")
    if name in _seen:
        raise ConfigError(f"preset inheritance loop: {' -> '.join((*_seen, name))}")
    data = load_yaml(path)
    parent = data.pop("extends", None)
    if parent:
        data = deep_merge(load_preset(parent, (*_seen, name)), data)
    return data


def _pick(table: dict[str, Any], key: str, what: str) -> dict[str, Any]:
    if key not in table:
        raise ConfigError(f"unknown {what} '{key}'. Available: {', '.join(k for k in table if isinstance(table[k], dict))}")
    return table[key]


def material_phrases(ids: list[str]) -> list[str]:
    library = {normalize_name(k): v for k, v in load_material_library()["materials"].items()}
    phrases = []
    for raw in ids:
        key = normalize_name(raw)
        if key not in library:
            raise ConfigError(f"material '{raw}' is not in materials/library.yaml")
        phrases.append(library[key].get("prompt") or key.lower().replace("_", " "))
    return phrases


def output_size(width: int, height: int, megapixels: float, multiple_of: int) -> tuple[int, int]:
    """Keep the input's aspect ratio, scale to the target pixel count, snap to the model grid."""
    scale = math.sqrt(megapixels * 1_000_000 / (width * height))
    w = max(multiple_of, round(width * scale / multiple_of) * multiple_of)
    h = max(multiple_of, round(height * scale / multiple_of) * multiple_of)
    return w, h


def resolve_settings(
    project_dir: Path,
    preset: str | None = None,
    fidelity: str | None = None,
    quality: str = "draft",
    engine: str | None = None,
) -> dict[str, Any]:
    project = load_yaml(project_dir / "project.yaml")
    ai = project.get("ai") or {}

    engine = engine or ai.get("engine", "flux_dev")
    preset = preset or ai.get("preset", "day_clear")
    fidelity = fidelity or ai.get("fidelity", "balanced")

    engines = load_yaml(AI_DIR / "engines.yaml")
    eng = dict(_pick(engines, engine, "engine"))
    eng["depth_model"] = engines.get("depth_model")
    eng["upscale_model"] = engines.get("upscale_model")
    fid = _pick(load_yaml(AI_DIR / "fidelity.yaml"), fidelity, "fidelity")
    qual = _pick(load_yaml(AI_DIR / "quality.yaml"), quality, "quality")
    pre = deep_merge(load_preset(preset), ai.get("preset_overrides") or {})
    views = load_yaml(AI_DIR / "views.yaml")

    ref = pre.get("style_reference")
    if ref:
        ref_path = (AI_DIR / "references" / ref).resolve()
        if not ref_path.exists():
            raise ConfigError(f"style reference not found: {ref_path}")
        pre["style_reference"] = str(ref_path)
    if ref and eng["family"] not in ("flux", "fal_edit"):
        raise ConfigError(f"style_reference needs a flux engine (Redux); '{engine}' is {eng['family']}")

    sampler = dict(eng.get("sampler") or {})
    if "steps" in sampler:
        sampler["steps"] = max(8, round(sampler["steps"] * float(qual.get("steps_factor", 1.0))))

    settings = {
        "engine_name": engine,
        "engine": eng,
        "preset_name": preset,
        "preset": pre,
        "fidelity_name": fidelity,
        "fidelity": fid,
        "quality": quality,
        "sampler": sampler,
        "megapixels": float(eng.get("megapixels", 1.0)) * float(qual.get("megapixels_factor", 1.0)),
        "upscale": qual.get("upscale"),
        "views": views,
        "context": ai.get("context", ""),
        "materials": material_phrases(ai.get("materials") or []),
        "view_overrides": ai.get("views") or {},
        "seed": int(ai.get("seed", pre.get("seed", 0))),
        "hero": ai.get("hero"),
        "color_key": {str(k).upper(): normalize_name(v) for k, v in (ai.get("color_key") or {}).items()},
        "shade_lock": {"enabled": True, "strength": 0.85, "source": "hero", **(ai.get("shade_lock") or {})},
    }
    for mat in settings["color_key"].values():
        material_phrases([mat])  # fail early on unknown ids
    settings["look_hash"] = look_hash(settings)
    return settings


def look_hash(settings: dict[str, Any]) -> str:
    """Everything that defines the look of the set. Quality-only settings are excluded,
    so a draft and a final of the same set share a hash."""
    look = {k: settings[k] for k in ("engine_name", "preset", "fidelity", "views", "context", "materials", "seed",
                                     "color_key", "shade_lock")}
    look["engine"] = {k: v for k, v in settings["engine"].items() if k not in ("licence",)}
    look["engine"].pop("sampler", None)
    look["sampler"] = {k: v for k, v in settings["sampler"].items() if k != "steps"}
    blob = json.dumps(look, sort_keys=True).replace(str(CONFIG_DIR), "<config>")
    return hashlib.sha256(blob.encode()).hexdigest()[:10]


def build_prompt(settings: dict[str, Any], view_name: str) -> dict[str, str]:
    views = settings["views"]
    view_type = view_type_for(view_name, views["types"], views.get("default_type", "EXT"))
    override = settings["view_overrides"].get(view_name) or {}
    materials = material_phrases(override["materials"]) if "materials" in override else settings["materials"]

    parts = [views["types"][view_type], settings["preset"].get("scene", "")]
    if settings["context"]:
        parts.append(settings["context"])
    if materials:
        parts.append(", ".join(materials))
    if override.get("prompt"):
        parts.append(override["prompt"])
    parts.append(views.get("suffix", ""))
    positive = ", ".join(p.strip().rstrip(",") for p in parts if p and p.strip())
    return {
        "view_type": view_type,
        "positive": positive,
        "negative": settings["engine"].get("negative", ""),
    }


def key_image_for(view_image: Path) -> Path | None:
    """The material colour key exported next to a view: 'EXT-01 Entrance.key.png'."""
    for suffix in IMAGE_SUFFIXES:
        candidate = view_image.with_name(f"{view_image.stem}.key{suffix}")
        if candidate.exists():
            return candidate
    return None


def find_inputs(project_dir: Path, only: list[str] | None = None) -> list[Path]:
    folder = project_dir / "input"
    images = sorted(p for p in folder.glob("*")
                    if p.suffix.lower() in IMAGE_SUFFIXES and not p.stem.lower().endswith(".key"))
    if only:
        images = [p for p in images if p.stem in only]
        missing = set(only) - {p.stem for p in images}
        if missing:
            raise ConfigError(f"input images not found: {', '.join(sorted(missing))}")
    if not images:
        raise ConfigError(f"no input images in {folder} (export your SketchUp views there as PNG/JPG)")
    return images
