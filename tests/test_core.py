import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from render_engine.cameras import build_camera, horizontal_fov_deg, lens_from_hfov, snap_lens, view_type_for
from render_engine.config import load_config, load_material_library, load_material_mapping
from render_engine.job import build_job
from render_engine.materials import UNMAPPED_ID, normalize_name, resolve_all
from render_engine.sun import direction_from_az_el, resolve_sun, solar_position

ROOT = Path(__file__).resolve().parents[1]

CAMERA_CFG = {
    "sensor_width_mm": 36,
    "default_type": "EXT",
    "lens_policy": "snap",
    "allowed_lenses_mm": [18, 24, 28, 35, 50],
    "two_point_max_pitch_deg": 25,
    "types": {
        "EXT": {"lock_eye_height": True, "eye_height_m": 1.6, "two_point": True, "allowed_lenses_mm": [24, 28, 35]},
        "AER": {"two_point": False},
        "ELV": {"orthographic": True},
    },
}


def scene(name, eye, target, fov=35.0, **cam):
    return {"name": name, "camera": {"eye": eye, "target": target, "perspective": True,
                                     "fov_deg": fov, "fov_is_height": True, "aspect_ratio": 1.5, **cam}}


# --- cameras -----------------------------------------------------------------

def test_fov_to_lens_round_trip():
    # 36 mm sensor, 50 mm lens -> 39.6 deg horizontal FOV
    assert lens_from_hfov(39.5978, 36) == pytest.approx(50, abs=0.01)


def test_vertical_fov_converted_with_aspect():
    hfov = horizontal_fov_deg({"fov_deg": 30, "fov_is_height": True}, 1.5)
    assert hfov == pytest.approx(math.degrees(2 * math.atan(math.tan(math.radians(15)) * 1.5)))


def test_snap_lens_uses_log_distance():
    assert snap_lens(26.5, [24, 28, 35]) == 28
    assert snap_lens(30.0, [24, 28, 35]) == 28
    assert snap_lens(32.0, [24, 28, 35]) == 35


def test_view_type_from_prefix():
    types = CAMERA_CFG["types"]
    assert view_type_for("AER-01 Site", types, "EXT") == "AER"
    assert view_type_for("elv-n north", types, "EXT") == "ELV"
    assert view_type_for("Front view", types, "EXT") == "EXT"


def test_eye_height_lock_and_two_point():
    cam = build_camera(scene("EXT-01", [-10, -10, 1.75], [0, 0, 3.0]), CAMERA_CFG, 1.5, ground_z=0.3)
    assert cam.location[2] == pytest.approx(1.9)            # 0.3 ground + 1.6 eye height
    assert cam.target[2] == pytest.approx(cam.location[2])  # levelled
    # framing kept by shifting the lens upwards
    pitch = math.atan2(3.0 + 0.15 - 1.9, math.hypot(10, 10))
    assert cam.shift_y == pytest.approx(cam.lens_mm * math.tan(pitch) / 36, abs=1e-4)
    assert cam.lens_mm in (24, 28, 35)


def test_two_point_skipped_for_steep_views():
    cam = build_camera(scene("EXT-02", [0, -5, 1.6], [0, 0, 20]), CAMERA_CFG, 1.5, 0.0)
    assert cam.shift_y == 0
    assert any("two-point skipped" in n for n in cam.notes)


def test_orthographic_scale():
    s = {"name": "ELV-N", "camera": {"eye": [0, -50, 5], "target": [0, 0, 5], "perspective": False, "ortho_height_m": 12}}
    cam = build_camera(s, CAMERA_CFG, 1.5, 0.0)
    assert cam.orthographic and cam.ortho_scale == pytest.approx(18)


def test_same_scene_same_camera():
    a = build_camera(scene("EXT-01", [-10, -10, 1.7], [0, 0, 3]), CAMERA_CFG, 1.5, 0.0)
    b = build_camera(scene("EXT-01", [-10, -10, 1.7], [0, 0, 3]), CAMERA_CFG, 1.5, 0.0)
    assert a == b


# --- sun ---------------------------------------------------------------------

def test_solar_position_london_midsummer():
    az, el = solar_position(51.5074, -0.1278, datetime(2024, 6, 21, 13, 2, tzinfo=ZoneInfo("Europe/London")))
    assert el == pytest.approx(61.9, abs=0.5)
    assert az == pytest.approx(180, abs=3)


def test_solar_position_morning_is_east():
    az, el = solar_position(12.97, 77.59, datetime(2026, 3, 21, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert 80 < az < 100 and 10 < el < 40


def test_north_angle_rotates_sun():
    assert direction_from_az_el(90, 0) == pytest.approx((1, 0, 0), abs=1e-9)
    assert direction_from_az_el(0, 0, north_angle_deg=90) == pytest.approx((1, 0, 0), abs=1e-9)


def test_resolve_sun_sketchup_mode_normalises():
    sun = resolve_sun({"mode": "sketchup"}, {}, {"sun_direction": [0, -2, 2]})
    assert sun["direction"] == pytest.approx([0, -0.707107, 0.707107], abs=1e-5)
    assert sun["elevation_deg"] == pytest.approx(45)


# --- materials ---------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Conc Boardform #1", "CONC_BOARDFORM"),
    ("conc-boardform.001", "CONC_BOARDFORM"),
    ("CONC_BOARDFORM", "CONC_BOARDFORM"),
    ("  wood  teak ", "WOOD_TEAK"),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_resolution_order():
    library = load_material_library()
    mapping = load_material_mapping()
    mapping["overrides"] = {"CONC_EXPOSED": "CONC_BOARDFORM"}
    resolved, unmapped = resolve_all(
        ["Wood Teak", "Translucent_Glass_Blue", "Lobby Glass Panel", "CONC_EXPOSED", "Color_A01", "Default"],
        library, mapping)
    assert resolved["WOOD_TEAK"] == {"id": "WOOD_TEAK", "source": "exact", "sketchup_name": "Wood Teak"}
    assert resolved["TRANSLUCENT_GLASS_BLUE"]["source"] == "alias"
    assert resolved["LOBBY_GLASS_PANEL"]["id"] == "GLASS_CLEAR"
    assert resolved["CONC_EXPOSED"]["id"] == "CONC_BOARDFORM"
    assert resolved["DEFAULT"]["id"] == "PLASTER_WHITE"
    assert resolved["COLOR_A01"]["id"] == UNMAPPED_ID
    assert unmapped == ["Color_A01"]


def test_alias_to_unknown_material_is_an_error():
    with pytest.raises(ValueError):
        resolve_all(["x"], load_material_library(), {"aliases": {"x": "NOT_A_MATERIAL"}})


def test_library_ids_are_normalised():
    for key in load_material_library()["materials"]:
        assert normalize_name(key) == key


# --- config & job --------------------------------------------------------------

@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    (p / "export").mkdir(parents=True)
    (p / "project.yaml").write_text("name: Test\nsite: {latitude: 12.97, longitude: 77.59, timezone: Asia/Kolkata}\n")
    (p / "export" / "model.fbx").write_bytes(b"")
    (p / "export" / "scenes.json").write_text(json.dumps({
        "model_file": "model.fbx",
        "scenes": [scene("EXT-01 A", [-10, -10, 1.6], [0, 0, 2]), scene("AER-01 B", [-30, -30, 20], [0, 0, 0])],
        "shadow_info": {"sun_direction": [0.3, -0.5, 0.8]},
    }))
    (p / "export" / "materials.json").write_text(json.dumps([{"name": "CONC_BOARDFORM"}, {"name": "Color_A01"}]))
    return p


def test_load_config_merges_preset(project):
    cfg = load_config(project, "exterior_day", "final")
    assert cfg["render"]["samples"] == 1024
    assert cfg["render"]["seed"] == 0
    assert cfg["style_settings"]["sun"]["azimuth_deg"] == 225


def test_draft_and_final_share_look_hash(project):
    draft = build_job(project, "exterior_day", "draft")
    preview = build_job(project, "exterior_day", "preview")
    assert draft["look_hash"] == preview["look_hash"]
    assert draft["cameras"] == preview["cameras"]
    assert any("unmapped" in w for w in draft["warnings"])


def test_different_style_different_hash(project):
    assert build_job(project, "exterior_day", "draft")["look_hash"] != build_job(project, "exterior_dusk", "draft")["look_hash"]


def test_final_refuses_unmapped_materials(project):
    from render_engine.config import ConfigError
    with pytest.raises(ConfigError, match="Color_A01"):
        build_job(project, "exterior_day", "final")


def test_massing_style_overrides_materials(project):
    job = build_job(project, "massing_white", "final")
    ids = {m["id"] for m in job["look"]["materials"]["mapping"].values()}
    assert ids == {"MASSING_WHITE"}
    assert job["look"]["sun"]["source"] == "sketchup shadow settings"


def test_all_studio_styles_build(project):
    from render_engine.config import available_styles
    for style in available_styles():
        build_job(project, style, "draft")
