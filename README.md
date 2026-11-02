# Render Engine

**Consistent architectural renders from SketchUp views.**

Export your views from SketchUp as images. The pipeline turns a whole set into
photoreal renders that share **one scene setting, one material palette and one
colour grade**, while keeping each view's geometry, framing and focal point.

**Recommended setup: [docs/hosted.md](docs/hosted.md).** It runs on a
hosted model (fal.ai), needs no GPU, and every view of a building is held to
the same materials and light:

```
input/EXT-01 Entrance.png      ┐
input/EXT-01 Entrance.key.png  ┘ material colour key (red = cedar, blue = glass, ...)
        │
        ▼ 1. hero view rendered first (view + key + swatches)
        ▼ 2. other views rendered with the hero as reference ("same building, same materials")
        ▼ 3. shade lock: each material pulled to the hero's colour in every view (via the key)
        ▼ 4. scorecard: colour difference per material across views + geometry kept
renders/<run>/  images, raw/, requests/, qa/scorecard.json, qa/contact_sheet.jpg
```

The same project also renders on your own GPU through ComfyUI (`--engine
flux_dev` or `sdxl`, see [docs/image-track.md](docs/image-track.md)), or as a
fully physical Blender render (the 3D track below).

## Why this design

- **Image in, no software link.** Any SketchUp image export works (and Revit
  or hand-drawn views later). There's no plugin and no model export.
- **AI rendering, held on a short leash.** Free text-to-image would redesign
  your building. Here a depth map and an edge map of *your* image steer the
  model, and your image is the starting point. Geometry, view range and focal
  point come from your export.
- **Consistency comes from config, not clicks.** Scene, materials, seed,
  models and grading are files in this repo. Every image records a `look_hash`
  of all of them, and `qa` flags a set that mixes looks.
- **Runs locally** on the studio's 24 GB NVIDIA PC through ComfyUI (free,
  scriptable, no per-image fees).

## Quick start

```bash
pip install -r requirements.txt              # PyYAML, Pillow, numpy (no GPU needed)
cd pipeline
python -m render_engine presets              # list scene presets
python -m render_engine render ../projects/courtyard-house --dry-run   # shows the prompts, no cost
python -m render_engine render ../projects/courtyard-house             # needs FAL_KEY (docs/hosted.md)
```

Setup: **[docs/hosted.md](docs/hosted.md)** (hosted, default) or [docs/image-track.md](docs/image-track.md) (own GPU).

To start a new project, copy `projects/_template` to `projects/<name>`, set
`ai.context` and `ai.materials` in `project.yaml`, and drop the SketchUp
exports into `input/`.

## The presets system

A render is three choices plus a project:

| Choice | Options | Lives in |
|---|---|---|
| **Scene preset** | `day_clear`, `overcast_soft`, `golden_hour`, `blue_hour`, `night`, `monsoon`, `interior_daylight`, `interior_evening` (add your own) | `config/ai/presets/` |
| **Fidelity** | `strict`, `balanced` (default), `concept` | `config/ai/fidelity.yaml` |
| **Quality** | `draft`, `final` (same look, different speed) | `config/ai/quality.yaml` |
| **Project** | site context, material palette, per-view notes | `projects/<name>/project.yaml` |

The same SketchUp exports can be rendered in several presets, e.g. a day set
and a dusk set, and each set stays internally consistent.

## Licensing note

The hosted engines (`nano_banana_pro`, `flux2_pro`) are used through their
providers' APIs, whose terms allow commercial use of outputs; check the current
terms before client delivery. On your own GPU, `flux_dev` is **non-commercial
only**, while `sdxl` allows commercial use.

## Repository layout

```
config/ai/            engines, fidelity, quality, view-type wording, scene presets, style references
materials/library.yaml  studio materials: a prompt description (image track) + PBR values (3D track)
pipeline/render_engine/
  ai/                 image track: settings, ComfyUI graph builder, client, colour harmonisation, runner
  qa.py, cli.py       shared QA (look-hash check, contact sheet, overlays) and command line
projects/_template/   copy per architecture project (input/ for view images)
projects/demo/        small pavilion with SketchUp-style inputs, to try everything
docs/                 image-track setup and guides
tests/                unit and end-to-end tests (a fake ComfyUI server stands in for the GPU)
```

### Optional: 3D track

The repo also contains a fully deterministic 3D path: a SketchUp exporter
(`sketchup/`) plus Blender Cycles (`render3d`, `config/styles/`,
`pipeline/blender/`). It needs a model export instead of an image, but gives
physically exact light and materials. Use it if a project ever needs exact
material or daylight studies. See [docs/sketchup-standards.md](docs/sketchup-standards.md)
and [docs/styles-and-cameras.md](docs/styles-and-cameras.md).

## Roadmap

1. **Now**: image track with presets, fidelity levels, material palette and colour harmonisation.
2. **Calibrate on a real project**: render one real SketchUp set in 2–3
   presets, tune the fidelity values and preset wording, and choose a style
   reference photo per preset.
3. **Per-region materials**: an optional second export per view with flat
   material colours (a SketchUp style with textures off) used as masks, so
   each material is prompted only where it is. This is the strongest material
   control.
4. **Entourage**: consistent people, cars and planting via prompt fragments
   per site type.
5. **Commercial path**: FLUX licence or tuned SDXL, before client use.
