import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from render_engine.ai.comfy import ComfyClient, ComfyError
from render_engine.ai.graph import build_graph
from render_engine.ai.harmonize import lab_stats, lab_to_srgb, match, srgb_to_lab
from render_engine.ai.run import render_set
from render_engine.ai.settings import (available_presets, build_prompt, load_preset, output_size,
                                       resolve_settings)
from render_engine.config import ConfigError
from render_engine.qa import check_run

PROJECT_YAML = """
name: Test
ai:
  engine: flux_dev
  preset: day_clear
  fidelity: balanced
  context: "suburban site with tropical planting"
  materials: [PLASTER_WHITE, wood teak, GLASS_CLEAR]
  views:
    "INT-01 Living": {materials: [WOOD_OAK_FLOOR], prompt: "double-height living room"}
"""


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    (p / "input").mkdir(parents=True)
    (p / "project.yaml").write_text(PROJECT_YAML)
    for name, color in (("EXT-01 Entrance", (180, 170, 150)), ("INT-01 Living", (120, 110, 100))):
        Image.new("RGB", (1500, 1000), color).save(p / "input" / f"{name}.png")
    return p


# --- settings ----------------------------------------------------------------

def test_presets_inherit_base():
    assert "day_clear" in available_presets() and "_base" not in available_presets()
    day = load_preset("day_clear")
    assert day["seed"] == 20261022 and day["harmonize"]["anchor"] == "first"
    assert "sunlight" in day["scene"]


@pytest.mark.parametrize("size", [(1500, 1000), (1920, 1080), (1000, 1414), (2000, 2000)])
def test_output_size_keeps_aspect_and_grid(size):
    w, h = output_size(*size, megapixels=1.6, multiple_of=16)
    assert w % 16 == 0 and h % 16 == 0
    assert w / h == pytest.approx(size[0] / size[1], rel=0.02)
    assert 1.45e6 < w * h < 1.75e6


def test_quality_changes_speed_not_look(project):
    draft = resolve_settings(project, quality="draft")
    final = resolve_settings(project, quality="final")
    assert draft["look_hash"] == final["look_hash"]
    assert draft["sampler"]["steps"] < final["sampler"]["steps"]
    assert final["upscale"] == {"factor": 2} and draft["upscale"] is None


def test_preset_and_fidelity_change_look(project):
    base = resolve_settings(project)["look_hash"]
    assert resolve_settings(project, preset="blue_hour")["look_hash"] != base
    assert resolve_settings(project, fidelity="strict")["look_hash"] != base


def test_prompt_assembly(project):
    s = resolve_settings(project)
    ext = build_prompt(s, "EXT-01 Entrance")
    assert ext["view_type"] == "EXT"
    assert ext["positive"].startswith("architectural exterior photograph")
    for part in ("crisp sunlight", "tropical planting", "warm teak wood", "clear glass"):
        assert part in ext["positive"]
    interior = build_prompt(s, "INT-01 Living")
    assert interior["view_type"] == "INT"
    assert "light oak" in interior["positive"] and "teak" not in interior["positive"]
    assert "double-height living room" in interior["positive"]


def test_unknown_material_rejected(project):
    (project / "project.yaml").write_text("ai: {materials: [UNOBTAINIUM]}\n")
    with pytest.raises(ConfigError, match="UNOBTAINIUM"):
        resolve_settings(project)


def test_style_reference_requires_flux(project, tmp_path):
    (project / "project.yaml").write_text("ai: {engine: sdxl, preset_overrides: {style_reference: README.md}}\n")
    with pytest.raises(ConfigError, match="flux"):
        resolve_settings(project)


# --- graph -------------------------------------------------------------------

def _by_class(graph):
    out = {}
    for node in graph.values():
        out.setdefault(node["class_type"], []).append(node["inputs"])
    return out


def _assert_links_valid(graph):
    for nid, node in graph.items():
        for value in node["inputs"].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                assert value[0] in graph, f"node {nid} links to missing node {value[0]}"
                assert int(value[0]) < int(nid), "links must point to earlier nodes"


def test_flux_graph(project):
    s = resolve_settings(project, quality="final")
    g = build_graph(s, build_prompt(s, "EXT-01 Entrance"), "in.png", (1552, 1040), "render_engine/x/EXT")
    _assert_links_valid(g)
    c = _by_class(g)
    assert c["UNETLoader"][0]["unet_name"] == "flux1-dev.safetensors"
    assert c["FluxGuidance"][0]["guidance"] == 3.5
    assert len(c["ControlNetApplyAdvanced"]) == 2               # depth + edges
    assert "SetUnionControlNetType" not in c                     # Union Pro 2.0 infers the type
    k = c["KSampler"][0]
    assert k["seed"] == 20261022 and k["denoise"] == 0.75 and k["cfg"] == 1.0
    assert c["ImageScale"][0]["width"] == 1552 and c["ImageScale"][-1]["width"] == 3104   # upscale x2
    assert c["SaveImage"][0]["filename_prefix"] == "render_engine/x/EXT"


def test_concept_drops_edges_and_sdxl_sets_union_type(project):
    s = resolve_settings(project, fidelity="concept", engine="sdxl")
    g = build_graph(s, build_prompt(s, "EXT-01 Entrance"), "in.png", (1224, 816), "p")
    _assert_links_valid(g)
    c = _by_class(g)
    assert "Canny" not in c and len(c["ControlNetApplyAdvanced"]) == 1
    assert c["SetUnionControlNetType"][0]["type"] == "depth"
    assert "cartoon" in c["CLIPTextEncode"][1]["text"]          # SDXL negative prompt


def test_style_reference_adds_redux(project):
    s = resolve_settings(project)
    s["preset"]["style_reference"] = "/refs/look.jpg"
    s["_style_reference_name"] = "look.jpg"
    c = _by_class(build_graph(s, build_prompt(s, "EXT-01 Entrance"), "in.png", (1024, 1024), "p"))
    assert c["StyleModelApply"][0]["strength"] == 0.3
    assert {"image": "look.jpg"} in c["LoadImage"]


# --- harmonisation -----------------------------------------------------------

def test_lab_round_trip():
    rgb = np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    assert np.abs(lab_to_srgb(srgb_to_lab(rgb)).astype(int) - rgb).max() <= 1


def test_match_pulls_colour_toward_anchor():
    rng = np.random.default_rng(1)
    warm = Image.fromarray(np.clip(rng.normal((200, 150, 110), 20, (100, 150, 3)), 0, 255).astype(np.uint8))
    cool = Image.fromarray(np.clip(rng.normal((120, 140, 190), 30, (100, 150, 3)), 0, 255).astype(np.uint8))
    matched = match(warm, cool, 1.0)
    m_mean, _ = lab_stats(matched)
    c_mean, _ = lab_stats(cool)
    w_mean, _ = lab_stats(warm)
    assert np.abs(m_mean - c_mean).max() < 3 < np.abs(w_mean - c_mean).max()
    half, _ = lab_stats(match(warm, cool, 0.5))
    assert np.all(np.abs(half - (w_mean + c_mean) / 2) < 4)


# --- end to end against a fake ComfyUI ---------------------------------------

class FakeComfy(BaseHTTPRequestHandler):
    prompts: dict = {}
    uploads: list = []

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/system_stats":
            return self._send(200, {"system": {}})
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            prefix = self.prompts[pid]
            return self._send(200, {pid: {"status": {"status_str": "success", "completed": True},
                                          "outputs": {"99": {"images": [{"filename": f"{prefix}.png", "subfolder": "", "type": "output"}]}}}})
        if self.path.startswith("/view"):
            # a different colour per view so harmonisation has work to do
            tint = (200, 120, 80) if "EXT" in self.path else (90, 130, 200)
            buf = BytesIO()
            Image.new("RGB", (64, 48), tint).save(buf, "PNG")
            return self._send(200, buf.getvalue(), "image/png")
        self._send(404, {})

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            name = body.split(b'filename="')[1].split(b'"')[0].decode()
            self.uploads.append(name)
            return self._send(200, {"name": name, "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            graph = json.loads(body)["prompt"]
            if any(n["class_type"] == "Broken" for n in graph.values()):
                return self._send(400, {"error": {"message": "Prompt outputs failed validation"},
                                        "node_errors": {"1": {"class_type": "Broken", "errors": [{"message": "Value not in list", "details": "unet_name: 'x' not in []"}]}}})
            pid = f"p{len(self.prompts)}"
            save = next(n for n in graph.values() if n["class_type"] == "SaveImage")
            self.prompts[pid] = save["inputs"]["filename_prefix"].rsplit("/", 1)[1]
            return self._send(200, {"prompt_id": pid})
        self._send(404, {})


@pytest.fixture
def comfy():
    server = HTTPServer(("127.0.0.1", 0), FakeComfy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_render_set_end_to_end(project, comfy):
    run_dir = render_set(project, comfy_url=comfy, log=lambda *_: None)
    assert sorted(p.name for p in run_dir.glob("*.png")) == ["EXT-01_Entrance.png", "INT-01_Living.png"]
    assert len(list((run_dir / "graphs").glob("*.json"))) == 2
    m = json.loads((run_dir / "INT-01_Living.json").read_text())
    assert m["harmonized_to"] == "EXT-01_Entrance.png" and m["generated_size"][0] % 16 == 0
    # INT was pulled toward the warm EXT anchor
    raw = np.asarray(Image.open(run_dir / "raw" / "INT-01_Living.png")).mean(axis=(0, 1))
    final = np.asarray(Image.open(run_dir / "INT-01_Living.png")).mean(axis=(0, 1))
    assert final[0] > raw[0] + 50 and final[2] < raw[2] - 50
    report = check_run(run_dir)
    assert report["images"] == 2 and report["consistent"]


def test_dry_run_needs_no_server(project):
    run_dir = render_set(project, dry_run=True, log=lambda *_: None)
    assert not list(run_dir.glob("*.png"))
    graph = json.loads((run_dir / "graphs" / "EXT-01_Entrance.json").read_text())
    assert any(n["class_type"] == "KSampler" for n in graph.values())


def test_validation_errors_are_readable(comfy):
    with pytest.raises(ComfyError, match="unet_name"):
        ComfyClient(comfy).queue({"1": {"class_type": "Broken", "inputs": {}}})


def test_unreachable_server_message():
    with pytest.raises(ComfyError, match="Is it running"):
        ComfyClient("http://127.0.0.1:9", timeout=2).ping()
