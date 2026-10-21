"""Build the Blender scene from a resolved job JSON and render every camera.

Run with Blender:
    blender -b --factory-startup --python-exit-code 1 -P pipeline/blender/render_job.py -- job.json
or in-process from a Python that has the `bpy` module (see cli.py --in-process).

This file makes no decisions of its own: every value comes from the job.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_engine.materials import UNMAPPED_ID, normalize_name  # noqa: E402

UNMAPPED_COLOR = "#FF00FF"


# --- helpers ----------------------------------------------------------------

def srgb_hex_to_linear(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return (*lin, alpha)


def set_input(node, names, value) -> None:
    """Set the first socket that exists (socket names changed between Blender versions)."""
    for name in names if isinstance(names, (list, tuple)) else [names]:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return


def look_at_quat(location, target):
    return (Vector(target) - Vector(location)).to_track_quat("-Z", "Y")


# --- scene setup ------------------------------------------------------------

def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(model: dict) -> list:
    path = model["path"]
    ext = Path(path).suffix.lower()
    before = set(bpy.data.objects)
    if ext == ".fbx":
        axes = {}
        if model.get("axis_forward") or model.get("axis_up"):
            axes = {"use_manual_orientation": True,
                    "axis_forward": model.get("axis_forward", "-Z"), "axis_up": model.get("axis_up", "Y")}
        bpy.ops.import_scene.fbx(filepath=path, global_scale=model.get("scale", 1.0), **axes)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path, up_axis="Z", forward_axis="Y",
                              global_scale=model.get("scale", 1.0))
    elif ext in (".usd", ".usda", ".usdc", ".usdz"):
        bpy.ops.wm.usd_import(filepath=path, scale=model.get("scale", 1.0))
    else:
        raise RuntimeError(f"unsupported model format: {ext}")
    return [o for o in bpy.data.objects if o not in before]


class MaterialBuilder:
    def __init__(self, defs: dict):
        self.defs = defs
        self.cache: dict[str, bpy.types.Material] = {}

    def get(self, mat_id: str) -> bpy.types.Material:
        if mat_id not in self.cache:
            if mat_id == UNMAPPED_ID:
                d = {"base_color": UNMAPPED_COLOR, "roughness": 0.5, "emission_strength": 0.3}
            else:
                d = self.defs[mat_id]
            self.cache[mat_id] = self._build(mat_id, d)
        return self.cache[mat_id]

    def _texture(self, nt, coord, path: str, non_color: bool, projection: str):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        tex.image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
        if projection == "box":
            tex.projection = "BOX"
            tex.projection_blend = 0.15
        nt.links.new(coord, tex.inputs["Vector"])
        return tex

    def _build(self, mat_id: str, d: dict) -> bpy.types.Material:
        mat = bpy.data.materials.new(f"RE_{mat_id}")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        kind = d.get("type", "principled")

        set_input(bsdf, "Base Color", srgb_hex_to_linear(d.get("base_color", "#BFBFBF")))
        set_input(bsdf, "Roughness", float(d.get("roughness", 0.5)))
        set_input(bsdf, "Metallic", float(d.get("metallic", 0.0)))
        set_input(bsdf, "IOR", float(d.get("ior", 1.5)))
        if "specular" in d:
            set_input(bsdf, ["Specular IOR Level", "Specular"], float(d["specular"]))
        if "coat" in d:
            set_input(bsdf, ["Coat Weight", "Coat"], float(d["coat"]))

        if kind == "glass":
            set_input(bsdf, ["Transmission Weight", "Transmission"], 1.0)
            set_input(bsdf, "Base Color", srgb_hex_to_linear(d.get("tint", "#FFFFFF")))
        if d.get("emission_strength"):
            set_input(bsdf, ["Emission Color", "Emission"], srgb_hex_to_linear(d.get("emission_color", d.get("base_color", "#FFFFFF"))))
            set_input(bsdf, "Emission Strength", float(d["emission_strength"]))
        if "alpha" in d:
            set_input(bsdf, "Alpha", float(d["alpha"]))

        textures = d.get("textures") or {}
        if textures:
            projection = d.get("projection", "box")
            sx, sy = (d.get("size_m") or [1.0, 1.0])[:2]
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (1.0 / sx, 1.0 / sy, 1.0 / sx)
            if "rotation_deg" in d:
                mapping.inputs["Rotation"].default_value[2] = math.radians(float(d["rotation_deg"]))
            if projection == "box":
                # World-space box mapping: texture scale is real-world and continuous
                # across objects, independent of SketchUp's UVs.
                geo = nt.nodes.new("ShaderNodeNewGeometry")
                nt.links.new(geo.outputs["Position"], mapping.inputs["Vector"])
            else:
                uv = nt.nodes.new("ShaderNodeTexCoord")
                nt.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
            coord = mapping.outputs["Vector"]

            if "base_color" in textures:
                tex = self._texture(nt, coord, textures["base_color"], False, projection)
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            if "roughness" in textures:
                tex = self._texture(nt, coord, textures["roughness"], True, projection)
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
            if "metallic" in textures:
                tex = self._texture(nt, coord, textures["metallic"], True, projection)
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Metallic"])
            if "normal" in textures:
                tex = self._texture(nt, coord, textures["normal"], True, projection)
                nmap = nt.nodes.new("ShaderNodeNormalMap")
                nmap.inputs["Strength"].default_value = float(d.get("normal_strength", 1.0))
                nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
                nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
            elif "bump" in textures:
                tex = self._texture(nt, coord, textures["bump"], True, projection)
                bump = nt.nodes.new("ShaderNodeBump")
                bump.inputs["Strength"].default_value = float(d.get("bump_strength", 0.3))
                nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
                nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        return mat


def assign_materials(objects: list, materials: dict) -> tuple[dict, "MaterialBuilder"]:
    """Replace every imported material with its library material. Returns usage stats."""
    builder = MaterialBuilder(materials["defs"])
    mapping = materials["mapping"]
    default_id = materials.get("default") or UNMAPPED_ID
    stats: dict[str, int] = {}
    for obj in objects:
        if obj.type != "MESH":
            continue
        if not obj.material_slots:
            obj.data.materials.append(builder.get(default_id))
            stats[default_id] = stats.get(default_id, 0) + 1
            continue
        for slot in obj.material_slots:
            if slot.material is None:
                mat_id = default_id
            else:
                entry = mapping.get(normalize_name(slot.material.name))
                mat_id = entry["id"] if entry else UNMAPPED_ID
            slot.link = "DATA"
            slot.material = builder.get(mat_id)
            stats[mat_id] = stats.get(mat_id, 0) + 1
    return stats, builder


def add_ground(ground: dict, builder: MaterialBuilder, ground_z: float) -> None:
    if not ground.get("enabled"):
        return
    size = float(ground.get("size_m", 400.0))
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 0.0, ground_z + float(ground.get("offset_m", -0.005))))
    plane = bpy.context.active_object
    plane.name = "RE_Ground"
    plane.data.materials.append(builder.get(normalize_name(ground["material"])))


def sky_rotation(model_azimuth_deg: float) -> float:
    """Blender's sky `sun_rotation` is clockwise from +Y (verified on Blender 5.2:
    0 puts the sun at +Y, 90 at +X), the same convention as our model azimuth."""
    return math.radians(model_azimuth_deg)


def setup_world(env: dict, sun: dict) -> None:
    world = bpy.data.worlds.new("RE_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    kind = env.get("type", "sky")

    if kind == "sky":
        sky_cfg = env.get("sky") or {}
        sky = nt.nodes.new("ShaderNodeTexSky")
        types = [e.identifier for e in sky.bl_rna.properties["sky_type"].enum_items]
        for candidate in (sky_cfg.get("model"), "MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
            if candidate in types:
                sky.sky_type = candidate
                break
        # The sun lamp provides direct light; the sky provides skylight only.
        sky.sun_disc = bool(sky_cfg.get("sun_disc", False))
        sky.sun_elevation = math.radians(max(sun["elevation_deg"], 0.0))
        sky.sun_rotation = sky_rotation(sun["model_azimuth_deg"])
        sky.altitude = float(sky_cfg.get("altitude_m", 0.0))
        for attr, key in (("air_density", "air"), ("aerosol_density", "aerosol"),
                          ("dust_density", "aerosol"), ("ozone_density", "ozone")):
            if hasattr(sky, attr) and key in sky_cfg:
                setattr(sky, attr, float(sky_cfg[key]))
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = float(sky_cfg.get("strength", 1.0))
    elif kind == "hdri":
        h = env["hdri"]
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value[2] = math.radians(float(h.get("rotation_deg", 0.0)))
        tex = nt.nodes.new("ShaderNodeTexEnvironment")
        tex.image = bpy.data.images.load(h["path"], check_existing=True)
        nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = float(h.get("strength", 1.0))
    elif kind == "color":
        bg.inputs["Color"].default_value = srgb_hex_to_linear(env.get("color", "#FFFFFF"))
        bg.inputs["Strength"].default_value = float(env.get("strength", 1.0))
    else:
        raise RuntimeError(f"unknown environment type '{kind}'")

    final = bg.outputs["Background"]
    cam_bg = env.get("camera_background")
    if cam_bg:
        # What the camera sees directly (e.g. a flat studio white) without
        # changing the light the scene receives.
        lp = nt.nodes.new("ShaderNodeLightPath")
        bg2 = nt.nodes.new("ShaderNodeBackground")
        bg2.inputs["Color"].default_value = srgb_hex_to_linear(cam_bg["color"])
        bg2.inputs["Strength"].default_value = float(cam_bg.get("strength", 1.0))
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
        nt.links.new(final, mix.inputs[1])
        nt.links.new(bg2.outputs["Background"], mix.inputs[2])
        final = mix.outputs["Shader"]
    nt.links.new(final, out.inputs["Surface"])

    if sun.get("strength", 0) > 0 and sun["elevation_deg"] > -1.0:
        data = bpy.data.lights.new("RE_Sun", type="SUN")
        data.energy = float(sun["strength"])
        data.angle = math.radians(float(sun["angle_deg"]))
        data.color = srgb_hex_to_linear(sun["color"])[:3]
        lamp = bpy.data.objects.new("RE_Sun", data)
        bpy.context.scene.collection.objects.link(lamp)
        lamp.rotation_mode = "QUATERNION"
        lamp.rotation_quaternion = (-Vector(sun["direction"])).to_track_quat("-Z", "Y")


def setup_render(job: dict) -> dict:
    scene = bpy.context.scene
    r = job["render"]
    color = job["look"]["color"]
    scene.render.engine = "CYCLES"
    c = scene.cycles

    device_used = "CPU"
    if r.get("device", "auto") != "CPU":
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                try:
                    prefs.compute_device_type = backend
                except TypeError:
                    continue
                prefs.get_devices()
                gpus = [d for d in prefs.devices if d.type != "CPU"]
                if gpus:
                    for d in prefs.devices:
                        d.use = d.type != "CPU"
                    c.device = "GPU"
                    device_used = backend
                    break
        except (KeyError, AttributeError):
            pass
    if device_used == "CPU":
        c.device = "CPU"

    c.samples = int(r["samples"])
    c.use_adaptive_sampling = bool(r.get("adaptive_threshold"))
    if c.use_adaptive_sampling:
        c.adaptive_threshold = float(r["adaptive_threshold"])
    c.seed = int(r.get("seed", 0))
    c.use_animated_seed = False
    c.use_denoising = bool(r.get("denoise", True))
    if c.use_denoising:
        c.denoiser = "OPENIMAGEDENOISE"
    b = r.get("bounces", {})
    c.max_bounces = int(b.get("total", 12))
    c.diffuse_bounces = int(b.get("diffuse", 4))
    c.glossy_bounces = int(b.get("glossy", 4))
    c.transmission_bounces = int(b.get("transmission", 12))
    c.transparent_max_bounces = int(b.get("transparent", 8))
    c.sample_clamp_indirect = float(r.get("clamp_indirect", 10.0))
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.filter_width = float(r.get("filter_width", 1.5))

    scene.render.resolution_x, scene.render.resolution_y = job["resolution"]
    scene.render.resolution_percentage = job["resolution_percentage"]
    scene.render.film_transparent = bool(r.get("film_transparent", False))

    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = color.get("view_transform", "AgX")
    scene.view_settings.look = color.get("look", "None")
    scene.view_settings.exposure = float(color.get("exposure", 0.0))
    scene.view_settings.gamma = float(color.get("gamma", 1.0))

    fmt = r.get("format", "PNG")
    s = scene.render.image_settings
    s.file_format = fmt
    if fmt == "PNG":
        s.color_mode = "RGBA" if scene.render.film_transparent else "RGB"
        s.color_depth = str(r.get("color_depth", 16))
    elif fmt == "OPEN_EXR":
        s.color_depth = "32"
    elif fmt == "JPEG":
        s.quality = int(r.get("quality", 95))
    return {"device": device_used}


def place_camera(cam: dict):
    scene = bpy.context.scene
    data = bpy.data.cameras.new(f"RE_{cam['name']}")
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = cam["sensor_width_mm"]
    data.clip_start = cam["clip_start"]
    data.clip_end = cam["clip_end"]
    if cam["orthographic"]:
        data.type = "ORTHO"
        data.ortho_scale = cam["ortho_scale"]
    else:
        data.type = "PERSP"
        data.lens = cam["lens_mm"]
        data.shift_x = cam["shift_x"]
        data.shift_y = cam["shift_y"]
    obj = bpy.data.objects.new(f"RE_{cam['name']}", data)
    scene.collection.objects.link(obj)
    obj.location = cam["location"]
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = look_at_quat(cam["location"], cam["target"])
    scene.camera = obj
    return obj


def safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name).strip("_")


# --- main -------------------------------------------------------------------

def run(job: dict) -> list[dict]:
    out_dir = Path(job["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")

    required = job["provenance"].get("required_blender")
    if required and not bpy.app.version_string.startswith(str(required)):
        print(f"[render-engine] WARNING: project pins Blender {required}, running {bpy.app.version_string}. "
              "Renders may not match earlier ones.", flush=True)

    reset_scene()
    objects = import_model(job["model"])
    look = job["look"]
    stats, builder = assign_materials(objects, look["materials"])
    ground_z = float(job.get("ground_z_m", 0.0))
    add_ground(look.get("ground") or {}, builder, ground_z)
    setup_world(look["environment"], look["sun"])
    render_info = setup_render(job)

    if job["render"].get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "scene.blend"), compress=True)

    ext = {"PNG": "png", "JPEG": "jpg", "OPEN_EXR": "exr"}[job["render"].get("format", "PNG")]
    results = []
    for cam in job["cameras"]:
        place_camera(cam)
        out = out_dir / f"{safe_filename(cam['name'])}.{ext}"
        bpy.context.scene.render.filepath = str(out)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        manifest = {
            "image": out.name,
            "view": cam["name"],
            "look_hash": job["look_hash"],
            "style": look["style"],
            "preset": job["preset"],
            "camera": cam,
            "render_seconds": round(time.time() - t0, 1),
            "blender_version": bpy.app.version_string,
            "device": render_info["device"],
            "material_usage": stats,
            "provenance": job["provenance"],
        }
        (out_dir / f"{safe_filename(cam['name'])}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        results.append(manifest)
        print(f"[render-engine] {cam['name']}: {out} ({manifest['render_seconds']}s)", flush=True)
    return results


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("usage: blender -b -P render_job.py -- job.json")
    run(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
