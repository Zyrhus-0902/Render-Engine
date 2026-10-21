"""Build projects/demo: a small pavilion that stands in for a SketchUp export.

It writes exactly what the SketchUp exporter writes (model.fbx, scenes.json,
materials.json), so the whole pipeline can be tried without SketchUp.

    python tools/make_demo_project.py      # needs the bpy module (pip install bpy)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "demo"
EXPORT = PROJECT / "export"

# Mix of naming situations the pipeline has to handle.
MATERIALS = {
    "CONC_BOARDFORM": (0.55, 0.54, 0.52),        # exact library id
    "Wood Teak": (0.48, 0.30, 0.18),             # normalises to WOOD_TEAK
    "Translucent_Glass_Blue": (0.6, 0.7, 0.8),   # alias -> GLASS_CLEAR
    "SITE_PAVING_GREY": (0.5, 0.5, 0.5),
    "Metal_Aluminum_Anodized": (0.4, 0.4, 0.42), # alias -> METAL_ALU_GREY
    "PLASTER_WHITE": (0.85, 0.84, 0.8),
}


def material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*MATERIALS[name], 1.0)
    return m


def box(name, size, location, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material(mat))
    return obj


def build_model():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    box("Plinth", (14, 10, 0.3), (0, 0, 0.15), "SITE_PAVING_GREY")
    box("WallBack", (10, 0.3, 3.2), (0, 3.0, 1.9), "CONC_BOARDFORM")
    box("WallSide", (0.3, 6.3, 3.2), (-4.85, 0, 1.9), "CONC_BOARDFORM")
    box("Core", (2.5, 2.5, 3.2), (3.0, 1.2, 1.9), "PLASTER_WHITE")
    box("Roof", (11.5, 7.5, 0.35), (0.3, 0.2, 3.68), "Wood Teak")
    box("Glazing", (7.0, 0.03, 3.2), (-0.8, -2.6, 1.9), "Translucent_Glass_Blue")
    box("Mullion1", (0.08, 0.12, 3.2), (-2.5, -2.6, 1.9), "Metal_Aluminum_Anodized")
    box("Mullion2", (0.08, 0.12, 3.2), (0.9, -2.6, 1.9), "Metal_Aluminum_Anodized")
    box("Column", (0.25, 0.25, 3.2), (5.3, -3.2, 1.9), "Metal_Aluminum_Anodized")


def main():
    if EXPORT.exists():
        shutil.rmtree(EXPORT)
    (EXPORT / "reference").mkdir(parents=True)
    build_model()
    bpy.ops.export_scene.fbx(filepath=str(EXPORT / "model.fbx"), use_selection=False,
                             apply_unit_scale=True, bake_space_transform=False)

    # Cameras as SketchUp would report them (metres, fov across the height).
    scenes = [
        {"name": "EXT-01 Approach", "description": "Main approach from the south-west",
         "camera": {"eye": [-14.0, -16.0, 1.75], "target": [0.0, 0.0, 2.6], "up": [0, 0, 1],
                    "perspective": True, "fov_deg": 35.0, "fov_is_height": True, "aspect_ratio": 1.5}},
        {"name": "EXT-02 Garden side", "description": "From the east lawn",
         "camera": {"eye": [17.0, -9.0, 1.4], "target": [0.0, 0.5, 2.0], "up": [0, 0, 1],
                    "perspective": True, "fov_deg": 30.0, "fov_is_height": True, "aspect_ratio": 1.5}},
        {"name": "AER-01 Overview", "description": "Bird's eye",
         "camera": {"eye": [-22.0, -26.0, 18.0], "target": [0.0, 0.0, 1.5], "up": [0, 0, 1],
                    "perspective": True, "fov_deg": 28.0, "fov_is_height": True, "aspect_ratio": 1.5}},
        {"name": "INT-01 Pavilion", "description": "Inside, looking out through the glazing",
         "camera": {"eye": [0.8, 2.3, 1.95], "target": [-3.5, -2.6, 1.9], "up": [0, 0, 1],
                    "perspective": True, "fov_deg": 50.0, "fov_is_height": True, "aspect_ratio": 1.5}},
    ]
    export = {
        "exporter_version": "demo",
        "sketchup_version": None,
        "model_name": "Demo pavilion",
        "exported_at": None,
        "model_file": "model.fbx",
        "model_scale": 1.0,
        "up_axis": "Z",
        "units": "m",
        "viewport": {"width": 1500, "height": 1000},
        "shadow_info": {"latitude": 12.9716, "longitude": 77.5946, "north_angle_deg": 0.0,
                        "sun_direction": [-0.5, -0.6, 0.62]},
        "scenes": scenes,
    }
    (EXPORT / "scenes.json").write_text(json.dumps(export, indent=2))
    (EXPORT / "materials.json").write_text(json.dumps(
        [{"name": n, "color": [round(c * 255) for c in rgb], "alpha": 1.0, "texture": None, "texture_size_m": None}
         for n, rgb in MATERIALS.items()], indent=2))

    project_yaml = PROJECT / "project.yaml"
    if not project_yaml.exists():
        text = (ROOT / "projects" / "_template" / "project.yaml").read_text()
        project_yaml.write_text(text.replace("name: Template Project", "name: Demo Pavilion"))
    print(f"demo project written to {PROJECT}")


if __name__ == "__main__":
    main()
