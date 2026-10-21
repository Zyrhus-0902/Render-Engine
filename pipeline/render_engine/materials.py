"""Map SketchUp material names onto the studio material library.

Resolution order for each SketchUp material:
  1. project overrides  (<project>/materials.yaml -> overrides)
  2. exact library id   (the SketchUp material is *named* after the library id)
  3. aliases            (legacy / vendor names -> library id)
  4. patterns           (glob rules, first match wins)
  5. fallback           (draft: bright magenta "UNMAPPED"; final: error)

This module must stay free of non-stdlib imports: Blender imports it too.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

UNMAPPED_ID = "_UNMAPPED"


def normalize_name(name: str) -> str:
    """Canonical form shared by SketchUp names, FBX names and library ids.

    'Conc Boardform #1' / 'conc-boardform.001' / 'CONC_BOARDFORM' -> 'CONC_BOARDFORM'
    """
    n = re.sub(r"\.\d{3}$", "", name.strip())   # Blender duplicate suffix
    n = re.sub(r"\s*#\d+$", "", n)              # SketchUp duplicate suffix
    n = re.sub(r"[^0-9A-Za-z]+", "_", n).strip("_")
    return n.upper()


def resolve_one(name: str, library_ids: set[str], mapping: dict[str, Any]) -> tuple[str, str]:
    key = normalize_name(name)
    overrides = {normalize_name(k): v for k, v in (mapping.get("overrides") or {}).items()}
    aliases = {normalize_name(k): v for k, v in (mapping.get("aliases") or {}).items()}

    if key in overrides:
        return normalize_name(overrides[key]), "override"
    if key in library_ids:
        return key, "exact"
    if key in aliases:
        return normalize_name(aliases[key]), "alias"
    for rule in mapping.get("patterns") or []:
        if fnmatch.fnmatch(key, normalize_name_glob(rule["match"])):
            return normalize_name(rule["material"]), f"pattern {rule['match']}"
    if key in ("", "DEFAULT", "MATERIAL") and mapping.get("default_material"):
        return normalize_name(mapping["default_material"]), "default"
    return UNMAPPED_ID, "unmapped"


def normalize_name_glob(pattern: str) -> str:
    """Normalise a glob the same way as names, but keep its wildcards."""
    parts = re.split(r"([*?])", pattern)
    return "".join(p if p in ("*", "?") else re.sub(r"[^0-9A-Za-z]+", "_", p).upper() for p in parts)


def resolve_all(
    sketchup_names: list[str], library: dict[str, Any], mapping: dict[str, Any]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return ({normalized sketchup name: {id, source}}, [unmapped original names])."""
    library_ids = {normalize_name(k) for k in library.get("materials", {})}
    resolved: dict[str, dict[str, str]] = {}
    unmapped: list[str] = []
    for name in sketchup_names:
        mat_id, source = resolve_one(name, library_ids, mapping)
        if mat_id != UNMAPPED_ID and mat_id not in library_ids:
            raise ValueError(f"material '{name}' maps to '{mat_id}', which is not in materials/library.yaml")
        if mat_id == UNMAPPED_ID:
            unmapped.append(name)
        resolved[normalize_name(name)] = {"id": mat_id, "source": source, "sketchup_name": name}
    return resolved, unmapped


def library_subset(library: dict[str, Any], ids: set[str]) -> dict[str, dict[str, Any]]:
    """The library definitions actually used, keyed by normalized id."""
    by_norm = {normalize_name(k): v for k, v in library.get("materials", {}).items()}
    return {i: by_norm[i] for i in sorted(ids) if i in by_norm}
