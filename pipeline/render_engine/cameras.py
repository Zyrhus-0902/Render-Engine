"""Turn SketchUp scene cameras into standardised render cameras.

Everything here is plain math so it can be unit-tested without Blender.
Coordinates are metres, Z-up, in SketchUp model axes (Blender uses the same
axes once the model is imported in metres).
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

Vec = tuple[float, float, float]


@dataclass
class RenderCamera:
    name: str
    view_type: str
    location: Vec
    target: Vec
    orthographic: bool
    lens_mm: float
    sensor_width_mm: float
    shift_x: float = 0.0
    shift_y: float = 0.0
    ortho_scale: float = 0.0
    clip_start: float = 0.1
    clip_end: float = 2000.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def horizontal_fov_deg(sketchup_cam: dict[str, Any], aspect: float) -> float:
    """Horizontal FOV of a SketchUp camera.

    SketchUp's `fov` is measured across the image height unless
    `fov_is_height` is false. `aspect` is width / height of the frame the
    camera was composed in.
    """
    fov = math.radians(sketchup_cam["fov_deg"])
    if sketchup_cam.get("fov_is_height", True):
        return math.degrees(2 * math.atan(math.tan(fov / 2) * aspect))
    return math.degrees(fov)


def lens_from_hfov(hfov_deg: float, sensor_width_mm: float) -> float:
    return sensor_width_mm / (2 * math.tan(math.radians(hfov_deg) / 2))


def snap_lens(lens_mm: float, allowed: list[float]) -> float:
    """Nearest allowed focal length, compared on a log scale (24 vs 28 matters more than 85 vs 90)."""
    return min(allowed, key=lambda a: abs(math.log(a / lens_mm)))


def view_type_for(scene_name: str, types: dict[str, Any], default: str) -> str:
    """Scene names are prefixed with their view type, e.g. 'EXT-01 Entrance'."""
    m = re.match(r"\s*([A-Za-z]+)", scene_name)
    if m and m.group(1).upper() in types:
        return m.group(1).upper()
    return default


def shift_unit_mm(sensor_width_mm: float, aspect: float) -> float:
    """Blender expresses lens shift as a fraction of the larger frame dimension."""
    return sensor_width_mm * max(1.0, 1.0 / aspect)


def build_camera(
    scene: dict[str, Any],
    camera_cfg: dict[str, Any],
    aspect: float,
    ground_z: float,
    overrides: dict[str, Any] | None = None,
) -> RenderCamera:
    """Apply the studio camera standard to one exported SketchUp scene."""
    types = camera_cfg["types"]
    name = scene["name"]
    view_type = view_type_for(name, types, camera_cfg.get("default_type", "EXT"))
    rule = {**types[view_type], **(overrides or {})}
    sensor = float(camera_cfg.get("sensor_width_mm", 36.0))
    cam = scene["camera"]
    notes: list[str] = []

    eye = tuple(float(v) for v in cam["eye"])
    target = tuple(float(v) for v in cam["target"])

    # The SketchUp frame aspect: the exporter forces it to the output aspect;
    # 0 means "follow the viewport".
    su_aspect = cam.get("aspect_ratio") or scene.get("viewport_aspect") or aspect

    if rule.get("orthographic") or not cam.get("perspective", True):
        height = float(cam.get("ortho_height_m") or 10.0)
        scale = height * max(aspect, 1.0)
        return RenderCamera(
            name=name, view_type=view_type, location=eye, target=target,
            orthographic=True, lens_mm=50.0, sensor_width_mm=sensor,
            ortho_scale=scale, clip_end=float(rule.get("clip_end_m", 2000.0)), notes=notes,
        )

    # 1. Eye height: lock eye-level views to the standard height above ground.
    if rule.get("lock_eye_height"):
        z = ground_z + float(rule["eye_height_m"])
        dz = z - eye[2]
        if abs(dz) > 1e-6:
            notes.append(f"eye height locked to {rule['eye_height_m']} m (moved {dz:+.2f} m)")
        eye = (eye[0], eye[1], z)
        target = (target[0], target[1], target[2] + dz)

    # 2. Focal length policy.
    su_lens = lens_from_hfov(horizontal_fov_deg(cam, su_aspect), sensor)
    policy = rule.get("lens_policy", camera_cfg.get("lens_policy", "snap"))
    if policy == "sketchup":
        lens = su_lens
    elif policy == "fixed":
        lens = float(rule["lens_mm"])
    elif policy == "snap":
        lens = snap_lens(su_lens, rule.get("allowed_lenses_mm") or camera_cfg["allowed_lenses_mm"])
    else:
        raise ValueError(f"unknown lens_policy '{policy}' for {name}")
    if abs(lens - su_lens) > 0.5:
        notes.append(f"lens {su_lens:.1f} mm -> {lens:.0f} mm ({policy})")

    # 3. Two-point perspective: level the camera, keep the framing with lens shift
    #    so verticals stay vertical.
    shift_y = 0.0
    if rule.get("two_point"):
        d = _sub(target, eye)
        horiz = math.hypot(d[0], d[1])
        pitch = math.degrees(math.atan2(d[2], horiz)) if horiz > 1e-9 else 90.0
        max_pitch = float(camera_cfg.get("two_point_max_pitch_deg", 25.0))
        if abs(pitch) <= max_pitch:
            shift_y = lens * math.tan(math.radians(pitch)) / shift_unit_mm(sensor, aspect)
            target = (target[0], target[1], eye[2])
        else:
            notes.append(f"two-point skipped: pitch {pitch:.1f} deg exceeds {max_pitch} deg")

    return RenderCamera(
        name=name, view_type=view_type, location=eye, target=target,
        orthographic=False, lens_mm=round(lens, 3), sensor_width_mm=sensor,
        shift_y=round(shift_y, 5),
        clip_start=float(rule.get("clip_start_m", 0.1)),
        clip_end=float(rule.get("clip_end_m", 2000.0)),
        notes=notes,
    )
