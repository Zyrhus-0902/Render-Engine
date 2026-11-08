"""Visual-brief dataset and bundle checks (the scoring logic is tested in
visual-brief/tests/scoring.test.js with `node --test`)."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

VB = Path(__file__).resolve().parents[1] / "visual-brief"
sys.path.insert(0, str(VB / "tools"))
import validate  # noqa: E402


def test_erode_dataset_has_no_errors():
    errors, _ = validate.validate("erode-hacienda-kerala")
    assert errors == []


def test_every_pair_isolates_one_dimension():
    dataset, pairs, images, _ = validate.load("erode-hacienda-kerala")
    imgs = {i["id"]: i for i in images}
    for p in pairs:
        a, b = imgs[p["image_a"]], imgs[p["image_b"]]
        assert a["dimension_id"] == b["dimension_id"] == p["dimension_id"]
        assert a["option_id"] != b["option_id"]
    per_dim = {d["id"]: sum(p["dimension_id"] == d["id"] for p in pairs) for d in dataset["dimensions"]}
    assert all(6 <= n <= 10 for n in per_dim.values()), per_dim


def test_validator_catches_a_cross_dimension_pair(tmp_path, monkeypatch):
    src = VB / "datasets" / "erode-hacienda-kerala"
    dst = tmp_path / "datasets" / "broken"
    shutil.copytree(src, dst)
    pairs = json.loads((dst / "pairs.json").read_text())
    pairs["pairs"][0]["image_b"] = "palette--wood_whitewash--1"
    (dst / "pairs.json").write_text(json.dumps(pairs))
    monkeypatch.setattr(validate, "ROOT", tmp_path)
    errors, _ = validate.validate("broken")
    assert any("belongs to dimension palette" in e for e in errors)


def test_bundle_is_self_contained(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_bundle", VB / "tools" / "build_bundle.py")
    bb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bb)
    monkeypatch.setattr(bb, "ROOT", tmp_path)
    monkeypatch.setattr(bb, "APP", VB / "app")
    out = bb.build("erode-hacienda-kerala")
    html = (out / "brief.html").read_text()
    assert "window.VB_BUNDLE" in html and "data:image/svg+xml;base64," in html
    assert 'src="js/' not in html and 'href="css/' not in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_scoring_js():
    r = subprocess.run(["node", "--test", str(VB / "tests" / "scoring.test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
