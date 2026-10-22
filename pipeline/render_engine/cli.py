"""Command line entry point.

Image track (SketchUp view images -> ComfyUI):
    python -m render_engine render   projects/my-house --preset day_clear --fidelity balanced --quality final
    python -m render_engine presets

3D track (SketchUp model export -> Blender Cycles):
    python -m render_engine validate projects/my-house
    python -m render_engine render3d projects/my-house --style exterior_day --preset final
    python -m render_engine styles

Both:
    python -m render_engine qa       projects/my-house/renders/<run_id>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import REPO_ROOT, ConfigError, available_styles
from .job import build_job, validate_project

BLENDER_SCRIPT = REPO_ROOT / "pipeline" / "blender" / "render_job.py"


def find_blender(explicit: str | None) -> str | None:
    return explicit or os.environ.get("BLENDER") or shutil.which("blender")


def cmd_validate(args) -> int:
    report = validate_project(Path(args.project))
    print(f"Scenes ({len(report['scenes'])}):")
    for s in report["scenes"]:
        print(f"  - {s}")
    print("Materials:")
    for r in report["materials"].values():
        print(f"  {r['sketchup_name']:<36} -> {r['id']:<24} [{r['source']}]")
    if report["unmapped"]:
        print(f"\n{len(report['unmapped'])} UNMAPPED material(s). Final renders will refuse to run until fixed.")
        return 1
    print("\nAll materials mapped.")
    return 0


def cmd_render(args) -> int:
    from .ai.comfy import ComfyError
    from .ai.run import render_set

    try:
        run_dir = render_set(Path(args.project), args.preset, args.fidelity, args.quality, args.engine,
                             args.views or None, args.comfy, args.dry_run)
    except ComfyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(f"dry run: ComfyUI workflows written to {run_dir / 'graphs'}")
        return 0
    return cmd_qa(argparse.Namespace(run_dir=str(run_dir), project=args.project))


def cmd_presets(args) -> int:
    from .ai.settings import available_presets, load_preset

    for name in available_presets():
        print(f"{name:<20} {load_preset(name).get('description', '')}")
    return 0


def cmd_render3d(args) -> int:
    job = build_job(Path(args.project), args.style, args.preset, args.views or None)
    for w in job["warnings"]:
        print(f"warning: {w}")
    for cam in job["cameras"]:
        for note in cam["notes"]:
            print(f"camera {cam['name']}: {note}")
    out_dir = Path(job["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    job_path = out_dir / "job.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(f"job: {job_path}  (look {job['look_hash']})")
    if args.dry_run:
        return 0

    if args.in_process:
        sys.path.insert(0, str(BLENDER_SCRIPT.parent))
        import render_job  # requires the `bpy` module

        render_job.run(job)
    else:
        blender = find_blender(args.blender)
        if not blender:
            print("Blender not found: pass --blender PATH, set $BLENDER, or use --in-process with the bpy module.")
            return 2
        cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1",
               "-P", str(BLENDER_SCRIPT), "--", str(job_path)]
        result = subprocess.run(cmd)
        if result.returncode:
            return result.returncode

    if not args.no_qa:
        return cmd_qa(argparse.Namespace(run_dir=str(out_dir), project=args.project))
    return 0


def cmd_qa(args) -> int:
    from .qa import alignment_overlays, check_run, contact_sheet

    run_dir = Path(args.run_dir)
    report = check_run(run_dir)
    print(json.dumps(report, indent=2))
    project = Path(args.project) if getattr(args, "project", None) else run_dir.parents[1]
    try:
        overlays = alignment_overlays(run_dir, project)
        sheet = contact_sheet(run_dir)
        print(f"alignment overlays: {len(overlays)}; contact sheet: {sheet}")
    except ImportError:
        print("Pillow not installed - skipped overlays and contact sheet")
    return 0 if report["consistent"] else 1


def cmd_styles(args) -> int:
    for s in available_styles(Path(args.project) if args.project else None):
        print(s)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="render_engine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="3D track: check a project's model export and material mapping")
    v.add_argument("project")
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("render", help="image track: render the project's input images through ComfyUI")
    a.add_argument("project")
    a.add_argument("--preset", help="scene preset, see `presets` (default: project ai.preset)")
    a.add_argument("--fidelity", help="strict | balanced | concept (default: project ai.fidelity)")
    a.add_argument("--quality", default="draft", help="draft | final")
    a.add_argument("--engine", help="flux_dev | sdxl (default: project ai.engine)")
    a.add_argument("--views", nargs="*", help="input image names without extension (default: all)")
    a.add_argument("--comfy", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"), help="ComfyUI address")
    a.add_argument("--dry-run", action="store_true", help="write the ComfyUI workflows only")
    a.set_defaults(func=cmd_render)

    pr = sub.add_parser("presets", help="list scene presets for the image track")
    pr.set_defaults(func=cmd_presets)

    r = sub.add_parser("render3d", help="3D track: render a SketchUp model export with Blender")
    r.add_argument("project")
    r.add_argument("--style")
    r.add_argument("--preset", help="draft | preview | final (see config/defaults.yaml)")
    r.add_argument("--views", nargs="*", help="scene names to render (default: all)")
    r.add_argument("--blender", help="path to the Blender executable")
    r.add_argument("--in-process", action="store_true", help="use the installed bpy module instead of a Blender binary")
    r.add_argument("--dry-run", action="store_true", help="write job.json only")
    r.add_argument("--no-qa", action="store_true")
    r.set_defaults(func=cmd_render3d)

    q = sub.add_parser("qa", help="consistency report, contact sheet and SketchUp overlays for a run")
    q.add_argument("run_dir")
    q.add_argument("--project")
    q.set_defaults(func=cmd_qa)

    s = sub.add_parser("styles", help="3D track: list Blender lighting styles")
    s.add_argument("project", nargs="?")
    s.set_defaults(func=cmd_styles)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
