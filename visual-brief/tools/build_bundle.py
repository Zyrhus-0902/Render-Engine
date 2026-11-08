"""Bundle a visual-brief project into two self-contained HTML files.

    python visual-brief/tools/build_bundle.py erode-hacienda-kerala

Writes visual-brief/dist/<project>/brief.html (client) and architect.html.
Each file inlines the CSS, JS, dataset and every image (as data: URIs), so it
opens from a USB stick, WhatsApp/email attachment or any static host, even
from file:// and offline. Validation errors stop the build.
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import load, validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


MAX_WIDTH, QUALITY = 800, 72  # phone/tablet sized; keeps the single file small enough to send


def data_uri(path: Path) -> str:
    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        # Photos are resized for the bundle only; the dataset keeps the originals.
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > MAX_WIDTH:
            im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def page(title: str, script: str, bundle: dict) -> str:
    css = (APP / "css" / "style.css").read_text(encoding="utf-8")
    js = "\n".join((APP / "js" / f).read_text(encoding="utf-8") for f in ("scoring.js", "data.js", script))
    payload = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<div id="app"><p style="padding:24px">Loading…</p></div>
<script>window.VB_BUNDLE = {payload};</script>
<script>
{js.replace("</script", "<\\/script")}
</script>
</body>
</html>
"""


def build(project: str) -> Path:
    errors, warnings = validate(project)
    for w in warnings:
        print("warning:", w)
    if errors:
        for e in errors:
            print("ERROR:  ", e)
        raise SystemExit(f"{project}: {len(errors)} validation errors; not bundling")
    dataset, pairs, images, base = load(project)
    for img in images:
        f = img["file"]
        if not f.startswith(("http://", "https://", "data:")):
            img["data_uri"] = data_uri(base / "assets" / f)
    bundle = {"dataset": dataset, "pairs": pairs, "images": images}
    out = ROOT / "dist" / project
    out.mkdir(parents=True, exist_ok=True)
    name = dataset["project"]["name"]
    name = name if isinstance(name, str) else name.get("en", project)
    (out / "brief.html").write_text(page(name, "client.js", bundle), encoding="utf-8")
    (out / "architect.html").write_text(page("Architect view · " + name, "architect.js", bundle), encoding="utf-8")
    size = (out / "brief.html").stat().st_size / 1e6
    print(f"wrote {out}/brief.html ({size:.1f} MB) and architect.html")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "erode-hacienda-kerala")
