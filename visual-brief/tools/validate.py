"""Check a visual-brief dataset before sending it to a client.

    python visual-brief/tools/validate.py erode-hacienda-kerala

Errors stop the run (broken references, a pair that mixes dimensions, a pair
that compares an option with itself, excluded images used in pairs). Warnings
flag curation problems the handoff calls out: rounds outside 6-10 pairs,
pairs at different scales, images missing a source or credit, origin tags that
disagree with the manifest, placeholders still in place.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(project: str) -> tuple[dict, list, list, Path]:
    base = ROOT / "datasets" / project
    dataset = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    pairs = json.loads((base / "pairs.json").read_text(encoding="utf-8"))["pairs"]
    images = json.loads((base / "assets" / "manifest.json").read_text(encoding="utf-8"))["images"]
    return dataset, pairs, images, base


def validate(project: str) -> tuple[list[str], list[str]]:
    dataset, pairs, images, base = load(project)
    errors: list[str] = []
    warnings: list[str] = []

    origins = {o["id"] for o in dataset.get("origins", [])}
    dims = {d["id"]: d for d in dataset.get("dimensions", [])}
    options = {(d["id"], o["id"]): o for d in dims.values() for o in d["options"]}
    if not dims:
        errors.append("dataset.json has no dimensions")
    for (did, oid), o in options.items():
        if o.get("origin") not in origins:
            errors.append(f"option {did}/{oid}: unknown origin {o.get('origin')!r}")

    imgs: dict[str, dict] = {}
    for img in images:
        iid = img.get("id")
        if iid in imgs:
            errors.append(f"image {iid}: duplicate id")
        imgs[iid] = img
        if (img.get("dimension_id"), img.get("option_id")) not in options:
            errors.append(f"image {iid}: unknown dimension/option {img.get('dimension_id')}/{img.get('option_id')}")
        weights = img.get("origin_weights") or {img.get("origin"): 1}
        for o in weights:
            if o not in origins:
                errors.append(f"image {iid}: unknown origin {o!r}")
        f = img.get("file", "")
        if not f.startswith(("http://", "https://", "data:")) and not (base / "assets" / f).is_file():
            errors.append(f"image {iid}: file not found assets/{f}")
        if not img.get("placeholder") and not (img.get("source") and img.get("credit")):
            warnings.append(f"image {iid}: missing source or credit")
        status = (img.get("climate") or {}).get("status", "ok")
        if status not in ("ok", "review", "exclude"):
            errors.append(f"image {iid}: climate.status must be ok, review or exclude")
        if status == "review" and not (img.get("climate") or {}).get("note"):
            warnings.append(f"image {iid}: climate review without a note")

    catalog = {a["id"]: set(a.get("values", {})) for a in dataset.get("attributes", [])}
    for img in images:
        for key, val in (img.get("attributes") or {}).items():
            if key not in catalog:
                errors.append(f"image {img.get('id')}: attribute {key!r} not in dataset attributes")
            elif val not in catalog[key]:
                errors.append(f"image {img.get('id')}: attribute {key}={val!r} not a listed value")
        if catalog and not img.get("attributes"):
            warnings.append(f"image {img.get('id')}: no attributes; it adds nothing to the cross-set reading")

    # Partial tagging inside one set: a key on some options but not others means
    # those comparisons are skipped. Usually a forgotten tag ("none" is a value).
    for did, d in dims.items():
        dim_imgs = [i for i in images if i.get("dimension_id") == did]
        keys = set().union(*[set(i.get("attributes") or {}) for i in dim_imgs]) if dim_imgs else set()
        for key in sorted(keys):
            missing = sorted({i["option_id"] for i in dim_imgs if key not in (i.get("attributes") or {})})
            if missing:
                warnings.append(f"dimension {did}: attribute {key!r} missing on {', '.join(missing)} (those comparisons are skipped)")

    placeholders = sum(1 for i in images if i.get("placeholder"))
    if placeholders:
        warnings.append(f"{placeholders} of {len(images)} images are still placeholders")
    reviews = [i["id"] for i in images if (i.get("climate") or {}).get("status") == "review"]
    if reviews:
        warnings.append(f"{len(reviews)} images flagged for climate review: {', '.join(reviews)}")

    per_dim: Counter = Counter()
    mixed: list[str] = []
    seen_ids: set = set()
    for p in pairs:
        pid = p.get("id")
        if pid in seen_ids:
            errors.append(f"pair {pid}: duplicate id")
        seen_ids.add(pid)
        did = p.get("dimension_id")
        if did not in dims:
            errors.append(f"pair {pid}: unknown dimension {did!r}")
            continue
        a, b = imgs.get(p.get("image_a")), imgs.get(p.get("image_b"))
        if not a or not b:
            errors.append(f"pair {pid}: unknown image {p.get('image_a') if not a else p.get('image_b')}")
            continue
        for side, img in (("a", a), ("b", b)):
            if img["dimension_id"] != did:
                errors.append(f"pair {pid}: image_{side} {img['id']} belongs to dimension {img['dimension_id']}, not {did}")
            if (img.get("climate") or {}).get("status") == "exclude":
                errors.append(f"pair {pid}: image_{side} {img['id']} is climate-excluded; remove the pair or the exclusion")
            tagged = p.get(f"origin_{side}")
            if tagged and tagged != img.get("origin"):
                warnings.append(f"pair {pid}: origin_{side}={tagged} but manifest says {img.get('origin')}")
        if a["option_id"] == b["option_id"]:
            errors.append(f"pair {pid}: both images are option {a['option_id']}; a pair must test two options")
        if a is b:
            errors.append(f"pair {pid}: same image on both sides")
        if bool(a.get("placeholder")) != bool(b.get("placeholder")):
            mixed.append(pid)
        if a.get("scale") != b.get("scale"):
            warnings.append(f"pair {pid}: scale differs ({a.get('scale')} vs {b.get('scale')})")
        per_dim[did] += 1

    if mixed and not dataset.get("settings", {}).get("allow_mixed_pairs"):
        warnings.append(f"{len(mixed)} pairs mix a sketch with a photo and are hidden from clients until both sides are photos: {', '.join(mixed)}")
    for did, d in dims.items():
        n = per_dim[did]
        if not 6 <= n <= 10:
            warnings.append(f"dimension {did}: {n} pairs (aim for 6-10)")
        shown = {imgs[p[k]]["option_id"] for p in pairs if p.get("dimension_id") == did for k in ("image_a", "image_b") if p.get(k) in imgs}
        for o in d["options"]:
            if o["id"] not in shown:
                warnings.append(f"option {did}/{o['id']} never appears in a pair")
            if not o.get("why_prompt"):
                warnings.append(f"option {did}/{o['id']}: no why_prompt")

    for t in dataset.get("tensions", []):
        for c in t.get("when", []):
            if (c.get("dimension"), c.get("option")) not in options:
                errors.append(f"tension {t.get('id')}: unknown {c.get('dimension')}/{c.get('option')}")

    langs = dataset.get("languages", ["en"])
    for lang in langs:
        if lang not in dataset.get("copy", {}):
            errors.append(f"language {lang!r} listed but copy.{lang} missing")
    return errors, warnings


def main(argv: list[str]) -> int:
    project = argv[1] if len(argv) > 1 else "erode-hacienda-kerala"
    errors, warnings = validate(project)
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("ERROR:  ", e)
    print(f"{project}: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
