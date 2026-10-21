"""Resolve project + style + preset + SketchUp export into one render job.

The job is plain JSON: every number the renderer needs is decided here, so
renders made from the same job are identical, and two jobs can be compared
by their `look_hash` to prove a set of images shares one look.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .cameras import build_camera
from .config import MATERIALS_DIR, REPO_ROOT, ConfigError, load_config, load_material_library, load_material_mapping, load_yaml
from .materials import UNMAPPED_ID, library_subset, normalize_name, resolve_all
from .sun import resolve_sun


def load_export(project_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    export_dir = project_dir / "export"
    scenes_path = export_dir / "scenes.json"
    materials_path = export_dir / "materials.json"
    if not scenes_path.exists():
        raise ConfigError(f"{scenes_path} not found - run 'Extensions > Render Engine > Export' in SketchUp first")
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    materials = json.loads(materials_path.read_text(encoding="utf-8")) if materials_path.exists() else []
    return scenes, materials


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:10]


def _resolve_textures(defs: dict[str, dict[str, Any]], warnings: list[str]) -> None:
    for mat_id, d in defs.items():
        for slot, rel in list((d.get("textures") or {}).items()):
            path = (MATERIALS_DIR / rel).resolve()
            if path.exists():
                d["textures"][slot] = str(path)
            else:
                warnings.append(f"{mat_id}: texture '{rel}' missing, using flat values for {slot}")
                del d["textures"][slot]


def build_job(
    project_dir: Path,
    style: str | None = None,
    preset: str | None = None,
    views: list[str] | None = None,
    out_root: Path | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    cfg = load_config(project_dir, style, preset)
    export, su_materials = load_export(project_dir)
    warnings: list[str] = []

    render = cfg["render"]
    width, height = int(render["resolution"][0]), int(render["resolution"][1])
    aspect = width / height
    site = cfg.get("site", {})
    style_cfg = cfg["style_settings"]

    # --- cameras --------------------------------------------------------------
    scene_overrides = cfg.get("scene_overrides") or {}
    selected = [s for s in export["scenes"] if not views or s["name"] in views]
    if views:
        missing = set(views) - {s["name"] for s in selected}
        if missing:
            raise ConfigError(f"views not found in export: {', '.join(sorted(missing))}")
    if not selected:
        raise ConfigError("no scenes to render")
    viewport = export.get("viewport") or {}
    vp_aspect = (viewport.get("width") or 0) / (viewport.get("height") or 1) or aspect
    cameras = []
    for s in selected:
        s = {**s, "viewport_aspect": vp_aspect}
        ov = scene_overrides.get(s["name"], {})
        ground_z = float(ov.get("ground_z_m", site.get("ground_z_m", 0.0)))
        cam = build_camera(s, cfg["camera"], aspect, ground_z, ov.get("camera"))
        cameras.append(cam.to_dict() | {"reference_image": s.get("reference_image")})

    # --- materials ------------------------------------------------------------
    library = load_material_library()
    mapping = load_material_mapping(project_dir)
    names = [m["name"] for m in su_materials]
    resolved, unmapped = resolve_all(names, library, mapping)
    override = style_cfg.get("material_override")
    if override:
        lib = library_subset(library, {r["id"] for r in resolved.values()})
        keep = set(override.get("keep_types") or [])
        target = normalize_name(override["material"])
        for r in resolved.values():
            if lib.get(r["id"], {}).get("type", "principled") not in keep:
                r["id"], r["source"] = target, "style override"
        unmapped = []

    strict = bool(render.get("strict_materials", False))
    if unmapped and strict:
        raise ConfigError(
            "unmapped SketchUp materials (fix names or add aliases in materials/mapping.yaml):\n  "
            + "\n  ".join(sorted(unmapped))
        )
    if unmapped:
        warnings.append(f"{len(unmapped)} unmapped material(s) shown in magenta: {', '.join(sorted(unmapped))}")

    used_ids = {r["id"] for r in resolved.values() if r["id"] != UNMAPPED_ID}
    default_id = normalize_name(mapping["default_material"]) if mapping.get("default_material") else None
    if override:
        default_id = normalize_name(override["material"])
    ground = style_cfg.get("ground") or {}
    for extra in (default_id, normalize_name(ground["material"]) if ground.get("material") else None):
        if extra:
            used_ids.add(extra)
    defs = library_subset(library, used_ids)
    _resolve_textures(defs, warnings)

    # --- environment ----------------------------------------------------------
    env = dict(style_cfg.get("environment") or {})
    if env.get("hdri", {}).get("path"):
        hdri = (REPO_ROOT / env["hdri"]["path"]).resolve()
        if not hdri.exists():
            raise ConfigError(f"HDRI not found: {hdri}")
        env["hdri"] = {**env["hdri"], "path": str(hdri)}
    sun = resolve_sun(style_cfg.get("sun") or {"mode": "fixed", "azimuth_deg": 225, "elevation_deg": 35}, site, export.get("shadow_info"))

    model_file = project_dir / "export" / export.get("model_file", "model.fbx")
    if not model_file.exists():
        raise ConfigError(f"model file not found: {model_file}")

    look = {
        "style": cfg["style"],
        "environment": env,
        "sun": sun,
        "ground": ground,
        "color": style_cfg.get("color") or {},
        "materials": {"defs": defs, "mapping": resolved, "default": default_id},
    }
    # Hash the look only (not quality settings), with machine-specific paths removed,
    # so a draft and a final of the same style share a hash.
    look_hash = _hash(json.loads(json.dumps(look).replace(str(REPO_ROOT), "<repo>")))

    run_id = f"{datetime.now():%Y%m%d-%H%M%S}_{cfg['style']}_{cfg['preset']}_{look_hash}"
    out_dir = (out_root or project_dir / "renders") / run_id

    return {
        "job_version": 1,
        "engine_version": __version__,
        "project": cfg.get("name", project_dir.name),
        "project_dir": str(project_dir),
        "preset": cfg["preset"],
        "look_hash": look_hash,
        "run_id": run_id,
        "output_dir": str(out_dir),
        # project.yaml `model:` can correct scale/axes if the alignment overlay is off.
        "model": {
            "path": str(model_file),
            "scale": float(export.get("model_scale", 1.0)),
            **(cfg.get("model") or {}),
        },
        "cameras": cameras,
        "ground_z_m": float(site.get("ground_z_m", 0.0)),
        "resolution": [width, height],
        "resolution_percentage": int(render.get("resolution_percentage", 100)),
        "look": look,
        "render": render,
        "warnings": warnings,
        "provenance": {
            "git_commit": _git_commit(),
            "sketchup_export": {k: export.get(k) for k in ("exporter_version", "sketchup_version", "model_name", "exported_at")},
            "required_blender": cfg.get("blender", {}).get("version"),
        },
    }


def validate_project(project_dir: Path) -> dict[str, Any]:
    """Quick checks that do not need Blender. Returns a report dict."""
    load_yaml(project_dir / "project.yaml")
    export, su_materials = load_export(project_dir)
    library = load_material_library()
    mapping = load_material_mapping(project_dir)
    resolved, unmapped = resolve_all([m["name"] for m in su_materials], library, mapping)
    return {
        "scenes": [s["name"] for s in export["scenes"]],
        "materials": resolved,
        "unmapped": unmapped,
    }
