"""Consistency scorecard for a render set.

  material_delta_e  per material: the largest colour difference (CIE76 Delta E) between any
                    view and the set average. <3 reads as identical, 3-6 noticeable, >6 different.
  edge_recall       per view: share of the SketchUp view's edges found again in the render
                    (within 4 px). Low values mean the AI changed the geometry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from ..config import load_yaml
from ..materials import normalize_name
from .colorkey import material_masks, region_stats
from .settings import key_image_for

GOOD_DE, OK_DE, GOOD_EDGES = 3.0, 6.0, 0.6


def edges(img: Image.Image, density: float = 0.08) -> np.ndarray:
    g = img.convert("L").filter(ImageFilter.GaussianBlur(2)).filter(ImageFilter.FIND_EDGES)
    a = np.asarray(g, dtype=np.float64)
    return a > np.quantile(a, 1 - density)


def edge_recall(source: Image.Image, render: Image.Image, tolerance: int = 4) -> float:
    render = render.resize(source.size)
    src = edges(source)
    near = Image.fromarray(edges(render).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(tolerance * 2 + 1))
    return float((src & (np.asarray(near) > 127)).sum() / max(src.sum(), 1))


def score_run(run_dir: Path, project_dir: Path) -> dict[str, Any]:
    project = load_yaml(project_dir / "project.yaml")
    legend = {str(k).upper(): normalize_name(v) for k, v in ((project.get("ai") or {}).get("color_key") or {}).items()}
    per_material: dict[str, dict[str, list[float]]] = {}
    views: dict[str, Any] = {}
    for mp in sorted(run_dir.glob("*.json")):
        if mp.name in ("job.json", "settings.json"):
            continue
        m = json.loads(mp.read_text())
        if "image" not in m:
            continue
        render = Image.open(run_dir / m["image"]).convert("RGB")
        src_path = project_dir / "input" / m["input"]
        entry: dict[str, Any] = {}
        if src_path.exists():
            src = Image.open(src_path).convert("RGB")
            entry["edge_recall"] = round(edge_recall(src, render), 3)
            key = key_image_for(src_path) if legend else None
            if key:
                for mat, mask in material_masks(key, legend, render.size).items():
                    stats = region_stats(render, mask)
                    if stats:
                        per_material.setdefault(mat, {})[m["view"]] = stats[0].tolist()
        views[m["view"]] = entry

    materials = {}
    for mat, by_view in per_material.items():
        if len(by_view) < 2:
            continue
        labs = np.array(list(by_view.values()))
        de = np.sqrt(((labs - labs.mean(0)) ** 2).sum(1))
        worst = list(by_view)[int(de.argmax())]
        materials[mat] = {"max_delta_e": round(float(de.max()), 2), "worst_view": worst, "views": len(by_view)}

    max_de = max((v["max_delta_e"] for v in materials.values()), default=None)
    min_edges = min((v["edge_recall"] for v in views.values() if "edge_recall" in v), default=None)
    verdict = {
        "materials": None if max_de is None else ("consistent" if max_de < GOOD_DE else "noticeable" if max_de < OK_DE else "inconsistent"),
        "geometry": None if min_edges is None else ("kept" if min_edges >= GOOD_EDGES else "changed"),
    }
    card = {"verdict": verdict, "max_material_delta_e": max_de, "min_edge_recall": min_edges,
            "materials": materials, "views": views}
    (run_dir / "qa").mkdir(exist_ok=True)
    (run_dir / "qa" / "scorecard.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return card


def format_card(card: dict[str, Any]) -> str:
    lines = [f"materials: {card['verdict']['materials'] or 'n/a (no colour keys)'}   "
             f"geometry: {card['verdict']['geometry'] or 'n/a'}"]
    for mat, v in sorted(card["materials"].items(), key=lambda kv: -kv[1]["max_delta_e"]):
        lines.append(f"  {mat:<30} dE {v['max_delta_e']:>5}  (worst: {v['worst_view']})")
    for view, v in card["views"].items():
        if "edge_recall" in v:
            lines.append(f"  {view:<30} edges kept {v['edge_recall']:.0%}")
    return "\n".join(lines)
