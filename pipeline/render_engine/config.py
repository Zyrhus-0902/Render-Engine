"""Load and merge the layered YAML configuration.

Layers, lowest to highest priority:
  1. config/defaults.yaml          studio-wide defaults
  2. config/styles/<style>.yaml    the "look" (environment, colour, ground)
  3. <project>/project.yaml        site location, levels, per-project overrides
  4. <project>/styles/<style>.yaml optional project-specific style tweaks
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
MATERIALS_DIR = REPO_ROOT / "materials"


class ConfigError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into a copy of base. Lists are replaced, not appended."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def available_styles(project_dir: Path | None = None) -> list[str]:
    names = {p.stem for p in (CONFIG_DIR / "styles").glob("*.yaml")}
    if project_dir is not None:
        names |= {p.stem for p in (project_dir / "styles").glob("*.yaml")}
    return sorted(names)


def load_style(style: str, project_dir: Path | None = None) -> dict[str, Any]:
    studio = CONFIG_DIR / "styles" / f"{style}.yaml"
    local = project_dir / "styles" / f"{style}.yaml" if project_dir else None
    if not studio.exists() and not (local and local.exists()):
        raise ConfigError(
            f"unknown style '{style}'. Available: {', '.join(available_styles(project_dir))}"
        )
    data = load_yaml(studio) if studio.exists() else {}
    if local and local.exists():
        data = deep_merge(data, load_yaml(local))
    return data


def load_config(project_dir: Path, style: str | None = None, preset: str | None = None) -> dict[str, Any]:
    """Return the fully merged configuration for one project/style/preset."""
    defaults = load_yaml(CONFIG_DIR / "defaults.yaml")
    project = load_yaml(project_dir / "project.yaml")

    style = style or project.get("style") or defaults.get("style")
    preset = preset or defaults.get("preset", "draft")

    cfg = deep_merge(defaults, {"style_settings": load_style(style, project_dir)})
    cfg = deep_merge(cfg, project)
    cfg["style"] = style
    cfg["preset"] = preset

    presets = cfg.get("render_presets", {})
    if preset not in presets:
        raise ConfigError(f"unknown preset '{preset}'. Available: {', '.join(sorted(presets))}")
    cfg["render"] = deep_merge(cfg.get("render", {}), presets[preset])
    return cfg


def load_material_library() -> dict[str, Any]:
    return load_yaml(MATERIALS_DIR / "library.yaml")


def load_material_mapping(project_dir: Path | None = None) -> dict[str, Any]:
    mapping = load_yaml(MATERIALS_DIR / "mapping.yaml")
    if project_dir is not None and (project_dir / "materials.yaml").exists():
        mapping = deep_merge(mapping, load_yaml(project_dir / "materials.yaml"))
    return mapping
