"""Find, review and adopt openly licensed reference photos for a dataset.

Three steps:

    # 1. search Openverse + Wikimedia Commons per option, download candidates + credits
    python visual-brief/tools/source_images.py search erode-hacienda-kerala [--only roof]

    # 2. open visual-brief/candidates/<project>/<dimension>.html (contact sheet) and pick

    # 3. adopt a candidate into the dataset: copies the file into assets/, records
    #    source, credit and licence in the manifest, clears the placeholder flag
    python visual-brief/tools/source_images.py adopt erode-hacienda-kerala roof--kerala_steep_tile--1 ov-114463b9

Search terms live in datasets/<project>/sourcing.json (option id -> list of
queries), so the architect can tune them. Only licences that allow commercial
use are kept: CC0 / public domain, CC BY and CC BY-SA. Candidates are not
committed (visual-brief/candidates/ is git-ignored); only adopted photos are.

Set VB_CONTACT to an email or URL first: Wikimedia blocks automated clients
without a contact in the User-Agent (https://w.wiki/4wJS).

Network hosts used: api.openverse.org, commons.wikimedia.org,
upload.wikimedia.org, live.staticflickr.com.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Wikimedia's bot policy requires a contact in the User-Agent. It comes from the
# environment (VB_CONTACT=you@example.com), never from the repository.
UA = "visual-brief-sourcing/0.1 (architecture studio reference tool" + (
    f"; {os.environ['VB_CONTACT']})" if os.environ.get("VB_CONTACT") else ")")
OK_LICENCES = re.compile(r"^(cc0|pdm|public domain|cc[- ]by(-sa)?([- ][0-9.]+)?)", re.I)


REACHABLE = ("api.openverse.org", "commons.wikimedia.org", "upload.wikimedia.org", "live.staticflickr.com")


def get(url: str, timeout: int = 30, tries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network flakiness, retry with backoff
            if attempt == tries - 1:
                raise
            if getattr(e, "code", None) == 429:
                wait = int((getattr(e, "headers", None) or {}).get("Retry-After", 20) or 20)
                time.sleep(min(wait, 90) + 2)
            else:
                time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def short_creator(s: str) -> str:
    """Credit name only; some Commons authors put long usage notes in the Artist field."""
    s = re.split(r"\n|\s{2,}", (s or "").strip())[0]
    s = re.sub(r"^this photo was taken by\s+", "", s, flags=re.I).rstrip(". ")
    return s[:80] or "unknown"


# Author requests beyond the licence ("contact me before commercial use") are respected:
# such candidates are flagged and refused by `adopt` unless --force is given.
AUTHOR_RESTRICTIONS = re.compile(r"contact me before commercial|before (any )?commercial use|not for commercial", re.I)


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------------------------------------------------------------- sources
def openverse(query: str, n: int) -> list[dict]:
    q = urllib.parse.urlencode({"q": query, "page_size": n, "license_type": "commercial",
                                "mature": "false"})
    data = json.loads(get(f"https://api.openverse.org/v1/images/?{q}"))
    out = []
    for r in data.get("results", []):
        lic = f"cc {r.get('license', '')} {r.get('license_version', '')}".strip() if r.get("license") not in ("cc0", "pdm") else r.get("license")
        url = r.get("url") or ""
        if r.get("provider") == "wikimedia":
            continue  # searched directly on Commons, which gives standard-size thumbnails
        # Full-size files from hosts we can't reach fall back to Openverse's own thumbnail.
        if urllib.parse.urlparse(url).hostname not in REACHABLE:
            url = f"https://api.openverse.org/v1/images/{r['id']}/thumb/"
        out.append({
            "cid": "ov-" + r["id"][:8], "provider": f"Openverse/{r.get('provider', '')}", "title": r.get("title") or "",
            "image_url": url, "landing": r.get("foreign_landing_url") or "", "creator": r.get("creator") or "unknown",
            "license": lic.replace("by-sa", "BY-SA").replace("by", "BY").upper() if lic else "", "license_url": r.get("license_url") or "",
            "width": r.get("width"), "height": r.get("height"), "query": query,
        })
    return out


def commons(query: str, n: int) -> list[dict]:
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrsearch": query + " filetype:bitmap",
        "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 960,  # a standard thumbnail size; others are rate-limited
    })
    data = json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))
    out = []
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = (meta.get("LicenseShortName", {}) or {}).get("value", "")
        out.append({
            "cid": f"wc-{p['pageid']}", "provider": "Wikimedia Commons", "title": p.get("title", "").removeprefix("File:"),
            # Same file path is served by upload.wikimedia.org, the host this session may reach.
            "image_url": (ii.get("thumburl") or ii.get("url", "")).replace("//thumb.wikimedia.org/", "//upload.wikimedia.org/"),
            "landing": ii.get("descriptionurl", ""),
            "creator": short_creator(strip_tags((meta.get("Artist", {}) or {}).get("value", ""))),
            "author_note": strip_tags((meta.get("Artist", {}) or {}).get("value", ""))[:600],
            "license": lic, "license_url": (meta.get("LicenseUrl", {}) or {}).get("value", ""),
            "width": ii.get("width"), "height": ii.get("height"), "query": query,
        })
    return out


def acceptable(c: dict) -> bool:
    if not OK_LICENCES.match((c.get("license") or "").strip()):
        return False
    if "-nc" in c["license"].lower() or "-nd" in c["license"].lower():
        return False
    w, h = c.get("width") or 0, c.get("height") or 0
    return w >= 800 and h >= 500 and 0.6 <= (w / h if h else 0) <= 2.2


# ---------------------------------------------------------------- commands
def search(project: str, only: str | None, per_query: int, options: list[str] | None = None) -> None:
    base = ROOT / "datasets" / project
    terms = json.loads((base / "sourcing.json").read_text(encoding="utf-8"))["queries"]
    dataset = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    cand_root = ROOT / "candidates" / project
    for dim in dataset["dimensions"]:
        if only and dim["id"] != only:
            continue
        if options and not any(o.startswith(dim["id"] + "/") for o in options):
            continue
        sheet = []
        for opt in dim["options"]:
            if options and f"{dim['id']}/{opt['id']}" not in options:
                prev = cand_root / dim["id"] / opt["id"] / "candidates.json"
                if prev.exists():  # keep it on the contact sheet
                    sheet.append((opt, json.loads(prev.read_text(encoding="utf-8"))))
                continue
            folder = cand_root / dim["id"] / opt["id"]
            folder.mkdir(parents=True, exist_ok=True)
            found: dict[str, dict] = {}
            for query in terms.get(f"{dim['id']}/{opt['id']}", []):
                for fn in (openverse, commons):
                    try:
                        for c in fn(query, per_query):
                            if acceptable(c) and c["cid"] not in found:
                                found[c["cid"]] = c
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! {fn.__name__} {query!r}: {e}", file=sys.stderr)
                    time.sleep(4)  # be polite: Commons throttles bursts
            def fetch(c):
                dest = folder / f"{c['cid']}.jpg"
                if not dest.exists():
                    try:
                        dest.write_bytes(get(c["image_url"], timeout=20, tries=3))
                        time.sleep(1)
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! download {c['cid']}: {e}", file=sys.stderr)
                        return None
                c["file"] = dest.name
                return c
            with ThreadPoolExecutor(1) as pool:  # sequential: Wikimedia rate-limits bursts
                kept = [c for c in pool.map(fetch, found.values()) if c]
            (folder / "candidates.json").write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{dim['id']}/{opt['id']}: {len(kept)} candidates")
            sheet.append((opt, kept))
        write_sheet(cand_root / f"{dim['id']}.html", dim, sheet)


def write_sheet(path: Path, dim: dict, sheet: list) -> None:
    rows = []
    for opt, kept in sheet:
        cells = "".join(
            f'<figure><img src="{dim["id"]}/{opt["id"]}/{c["file"]}" loading="lazy"><figcaption><b>{c["cid"]}</b> '
            f'{html.escape(c["title"][:60])}<br>{html.escape(c["license"])} · {html.escape(c["creator"][:40])}</figcaption></figure>'
            for c in kept)
        rows.append(f'<h2>{html.escape(opt["label"])} <small>{opt["id"]} · {opt["origin"]}</small></h2><div class="g">{cells or "<p>none found</p>"}</div>')
    path.write_text(f"""<!doctype html><meta charset="utf-8"><title>{html.escape(dim['name'])} candidates</title>
<style>body{{font:13px system-ui;margin:16px;background:#f6f4ef}}.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}}
figure{{margin:0;background:#fff;padding:4px}}img{{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}}figcaption{{font-size:11px;padding:4px 2px}}</style>
<h1>{html.escape(dim['name'])}</h1>{''.join(rows)}""", encoding="utf-8")


def adopt(project: str, image_id: str, cid: str, force: bool = False) -> None:
    base = ROOT / "datasets" / project
    man_path = base / "assets" / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    img = next((i for i in manifest["images"] if i["id"] == image_id), None)
    if not img:
        raise SystemExit(f"no image {image_id} in manifest")
    folder = ROOT / "candidates" / project / img["dimension_id"] / img["option_id"]
    cands = {c["cid"]: c for c in json.loads((folder / "candidates.json").read_text(encoding="utf-8"))}
    if cid not in cands:
        # allow adopting a candidate found under another option of the same dimension
        for other in (ROOT / "candidates" / project / img["dimension_id"]).glob("*/candidates.json"):
            for c in json.loads(other.read_text(encoding="utf-8")):
                if c["cid"] == cid:
                    cands[cid], folder = c, other.parent
    c = cands.get(cid) or sys.exit(f"candidate {cid} not found for {image_id}")
    if AUTHOR_RESTRICTIONS.search(c.get("author_note", "") or c.get("creator", "")) and not force:
        sys.exit(f"{cid}: the author asks to be contacted before commercial use; ask them first, then adopt with --force")
    new_file = f"{image_id}.jpg"
    shutil.copyfile(folder / c["file"], base / "assets" / new_file)
    old = img.get("file", "")
    if old.endswith(".svg") and old != new_file and (base / "assets" / old).exists():
        (base / "assets" / old).unlink()
    img.update({"file": new_file, "source": c["landing"], "credit": f"{short_creator(c['creator'])} / {c['provider']}",
                "license": c["license"], "license_url": c["license_url"], "title": c["title"], "placeholder": False})
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{image_id} <- {cid} ({c['license']}, {c['creator']})")


def unadopt(project: str, image_id: str) -> None:
    """Put an image slot back to its sketch placeholder."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sketches import sketch_svg
    base = ROOT / "datasets" / project
    man_path = base / "assets" / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    img = next((i for i in manifest["images"] if i["id"] == image_id), None) or sys.exit(f"no image {image_id}")
    if img.get("file", "").endswith(".jpg") and (base / "assets" / img["file"]).exists():
        (base / "assets" / img["file"]).unlink()
    n = int(image_id.rsplit("--", 1)[1])
    img["file"] = f"{image_id}.svg"
    (base / "assets" / img["file"]).write_text(sketch_svg(img["dimension_id"], img["option_id"], n, img.get("code", "")), encoding="utf-8")
    for k in ("license", "license_url", "title"):
        img.pop(k, None)
    img.update({"source": "placeholder", "credit": "", "placeholder": True})
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{image_id} -> sketch placeholder")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("project"); s.add_argument("--only"); s.add_argument("--per-query", type=int, default=12)
    s.add_argument("--options", nargs="*", help="limit to dimension/option ids, e.g. roof/hacienda_low_hip")
    a = sub.add_parser("adopt"); a.add_argument("project"); a.add_argument("image_id"); a.add_argument("cid"); a.add_argument("--force", action="store_true")
    u = sub.add_parser("unadopt"); u.add_argument("project"); u.add_argument("image_id")
    args = ap.parse_args()
    if args.cmd == "search":
        search(args.project, args.only, args.per_query, args.options)
    elif args.cmd == "adopt":
        adopt(args.project, args.image_id, args.cid, args.force)
    else:
        unadopt(args.project, args.image_id)
