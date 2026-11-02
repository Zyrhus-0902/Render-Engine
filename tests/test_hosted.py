import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from render_engine.ai.colorkey import material_masks
from render_engine.ai.fal import FalClient, FalError
from render_engine.ai.hosted import render_set_hosted
from render_engine.ai.score import score_run
from render_engine.ai.settings import find_inputs

WOOD, METAL = (160, 110, 70), (60, 62, 66)

PROJECT = """
ai:
  engine: nano_banana_pro
  preset: day_clear
  hero: "EXT-01 Front"
  context: "courtyard house"
  color_key:
    "#FF0000": WOOD_CEDAR_CLADDING
    "#0000FF": METAL_STANDING_SEAM_CHARCOAL
"""


def view_and_key(split: str):
    """Two-material test view. split 'v' = wood left / metal right, 'h' = wood top / metal bottom."""
    w, h = 300, 200
    view, key = np.zeros((h, w, 3), np.uint8), np.zeros((h, w, 3), np.uint8)
    a = (slice(None), slice(0, w // 2)) if split == "v" else (slice(0, h // 2), slice(None))
    b = (slice(None), slice(w // 2, None)) if split == "v" else (slice(h // 2, None), slice(None))
    view[a], view[b] = WOOD, METAL
    key[a], key[b] = (255, 0, 0), (0, 0, 255)
    key[b] = (key[b] * 0.8).astype(np.uint8)  # SketchUp face shading darkens the key colour
    return Image.fromarray(view), Image.fromarray(key)


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    (p / "input").mkdir(parents=True)
    (p / "project.yaml").write_text(PROJECT)
    for name, split in (("EXT-01 Front", "v"), ("EXT-02 Side", "h"), ("EXT-03 Corner", "v")):
        v, k = view_and_key(split)
        v.save(p / "input" / f"{name}.png")
        k.save(p / "input" / f"{name}.key.png")
    return p


class FakeFal(BaseHTTPRequestHandler):
    requests: list = []

    def log_message(self, *a):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["Authorization"] == "Key test-key"
        idx = len(self.requests)
        self.requests.append(body)
        base = f"http://{self.headers['Host']}"
        self._json({"request_id": str(idx), "status_url": f"{base}/status/{idx}", "response_url": f"{base}/result/{idx}"})

    def do_GET(self):
        if self.path.startswith("/status/"):
            return self._json({"status": "COMPLETED"})
        idx = int(self.path.rsplit("/", 1)[1])
        body = self.requests[idx]
        view = Image.open(BytesIO(base64.b64decode(body["image_urls"][0].split(",", 1)[1]))).convert("RGB")
        # Model drift: each later view comes back warmer/brighter, and at a slightly different aspect.
        arr = np.clip(np.asarray(view, np.int16) + np.array([25, 10, -10]) * idx, 0, 255).astype(np.uint8)
        out = Image.fromarray(arr).resize((320, 200))
        buf = BytesIO()
        out.save(buf, "PNG")
        self._json({"images": [{"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}]})


@pytest.fixture
def fal():
    FakeFal.requests = []
    server = HTTPServer(("127.0.0.1", 0), FakeFal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield FalClient(key="test-key", base_url=f"http://127.0.0.1:{server.server_port}")
    server.shutdown()


def test_key_files_are_not_views(project):
    assert [p.stem for p in find_inputs(project)] == ["EXT-01 Front", "EXT-02 Side", "EXT-03 Corner"]


def test_masks_absorb_face_shading(project):
    masks = material_masks(project / "input" / "EXT-02 Side.key.png",
                           {"#FF0000": "WOOD", "#0000FF": "METAL"}, (300, 200))
    assert masks["WOOD"][:100].all() and masks["METAL"][100:].all()
    assert not (masks["WOOD"] & masks["METAL"]).any()


def test_hero_first_and_references(project, fal):
    run = render_set_hosted(project, client=fal, log=lambda *_: None)
    reqs = FakeFal.requests
    assert len(reqs) == 3
    assert "Image 2 is a material map" in reqs[0]["prompt"] and "approved render" not in reqs[0]["prompt"]
    assert len(reqs[0]["image_urls"]) == 2 and len(reqs[1]["image_urls"]) == 3   # view, key (+ hero)
    assert "Image 3 is the approved render" in reqs[1]["prompt"]
    assert "red (#FF0000) areas are vertical cedar timber cladding" in reqs[1]["prompt"]
    assert reqs[0]["resolution"] == "2K" and "seed" not in reqs[0]
    logged = json.loads((run / "requests" / "EXT-02_Side.json").read_text())
    assert logged["image_urls"] == ["EXT-02 Side.png (view)", "EXT-02 Side.key.png (material key)",
                                    "EXT-01_Front.png (hero render)"]
    m = json.loads((run / "EXT-02_Side.json").read_text())
    assert m["shade_locked"] == ["METAL_STANDING_SEAM_CHARCOAL", "WOOD_CEDAR_CLADDING"]
    assert Image.open(run / "EXT-02_Side.png").size == (300, 200)    # back in the input frame


def test_shade_lock_makes_set_consistent(project, fal):
    locked = score_run(render_set_hosted(project, client=fal, log=lambda *_: None), project)
    assert locked["verdict"] == {"materials": "consistent", "geometry": "kept"}

    (project / "project.yaml").write_text(PROJECT + "  shade_lock: {enabled: false}\n  preset_overrides: {harmonize: {enabled: false}}\n")
    FakeFal.requests = []
    drifted = score_run(render_set_hosted(project, client=fal, log=lambda *_: None), project)
    assert drifted["verdict"]["materials"] == "inconsistent"
    assert drifted["max_material_delta_e"] > 5 * locked["max_material_delta_e"]


def test_reuse_approved_hero(project, fal):
    first = render_set_hosted(project, views=["EXT-01 Front"], client=fal, log=lambda *_: None)
    FakeFal.requests = []
    second = render_set_hosted(project, views=["EXT-02 Side"], hero_from=first, client=fal, log=lambda *_: None)
    assert len(FakeFal.requests) == 1                       # hero not re-rendered
    assert (second / "EXT-01_Front.png").exists()           # but included in the set
    assert score_run(second, project)["verdict"]["materials"] == "consistent"


def test_views_without_hero_need_hero_from(project, fal):
    from render_engine.config import ConfigError
    with pytest.raises(ConfigError, match="hero-from"):
        render_set_hosted(project, views=["EXT-02 Side"], client=fal, log=lambda *_: None)


def test_flux2_sends_seed(project, fal):
    render_set_hosted(project, engine="flux2_pro", views=["EXT-01 Front"], client=fal, log=lambda *_: None)
    assert FakeFal.requests[0]["seed"] == 20261022


def test_dry_run_needs_no_key(project, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    run = render_set_hosted(project, dry_run=True, log=lambda *_: None)
    assert len(list((run / "requests").glob("*.json"))) == 3
    with pytest.raises(FalError, match="FAL_KEY"):
        FalClient()
