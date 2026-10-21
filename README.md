# Render Engine

**Consistent architectural renders from SketchUp scenes.**

You model and compose views in SketchUp. A one-click exporter writes the model,
every scene camera, the sun and the material list. A headless **Blender
Cycles** pipeline then rebuilds the scene from version-controlled settings and
renders every view. Because no setting is clicked by hand, every image in a set
shares the same environment, camera standard, materials and colour grading.

```
 SketchUp (Pro)                         this repo                                 output
┌──────────────────┐   export/   ┌───────────────────────────────┐   renders/<run>/
│ scenes = views   │──model.fbx─▶│ job builder (Python)          │   EXT-01_Approach.png
│ materials named  │──scenes.json│  + config/defaults.yaml       │──▶EXT-01_Approach.json  (manifest)
│ after library ids│──materials. │  + config/styles/<style>.yaml │   qa/contact_sheet.jpg
│ Render Engine    │  json       │  + materials/library.yaml     │   qa/*_overlay.jpg
│ exporter (Ruby)  │──reference/ │  = job.json  ──▶ Blender 5.2  │
└──────────────────┘   *.png     └───────────────────────────────┘
```

---

## 1. The decision: which engine?

| Option | Consistency | Automation | Cost | Verdict |
|---|---|---|---|---|
| **Blender + Cycles (chosen)** | Every setting is code. Fixed seed, pinned version, path-traced | Full Python API, headless CLI, runs on any machine or in the cloud | Free, open source | **Core engine** |
| V-Ray for SketchUp | Very good (`.vrmat` library, `.vrscene`) | Ruby API + V-Ray Standalone | Per-seat and per-render-node licences | Upgrade path if you need V-Ray specifically |
| Enscape / D5 / Lumion / Twinmotion | Depends on someone clicking the same presets every time | Little or no headless or scripted rendering | Subscription | Good for live client walkthroughs, weak for a repeatable pipeline |

Real-time engines look great, but consistency in them comes from discipline:
someone has to reapply the same sky, exposure and materials in a GUI for every
view. With Blender, the settings live in this repository, rendering runs from
the command line, and a view rendered today can be re-rendered pixel-identical
next month. Blender also runs headless, so views you send in can be rendered
by an automated job, including by Claude in a cloud session.

## 2. How each kind of consistency is enforced

| What must match | Where it is fixed | Mechanism |
|---|---|---|
| **Scene setting / environment** | `config/styles/*.yaml` | Physical sky model, a sun lamp from a fixed bearing/elevation (or real solar position, or SketchUp's shadow settings), a ground plane, and AgX colour grading with a fixed exposure. One style = one look. |
| **View range** | `config/defaults.yaml → camera` | 36 mm full-frame sensor. Focal lengths are snapped to an allowed set per view type (EXT 24/28/35, INT 18/24, AER 35/50, DET 50). One aspect ratio (3:2) for every preset, and SketchUp scenes are locked to the same 3:2 frame. |
| **Focal point / eye level** | same | Exterior eye height locked to 1.6 m above ground. Two-point perspective (levelled camera plus lens shift) keeps verticals vertical while keeping the framing. Orthographic for elevations. |
| **Materials** | `materials/library.yaml` + `mapping.yaml` | SketchUp materials are *named* after library ids. At render time every SketchUp material is replaced by its library definition: one PBR definition, real-world texture scale, world-space box mapping. Unknown materials render magenta in drafts and **block** final renders. |
| **Repeatability** | job + manifest | Fixed sampling seed, pinned Blender version (warns on mismatch), and a `look_hash` over every look setting. Every image gets a JSON manifest, and `qa` fails if a set mixes looks or Blender versions. |

## 3. Workflow

1. **Model in SketchUp** following [docs/sketchup-standards.md](docs/sketchup-standards.md):
   name materials after library ids, and create one scene per view named `EXT-01 …`, `INT-02 …`, `AER-01 …`.
2. **Extensions › Render Engine › Lock scenes to render frame** (once), then compose inside the 3:2 frame.
3. **Extensions › Render Engine › Export for rendering…** and select `projects/<name>/`.
4. **Validate**: `python -m render_engine validate projects/<name>` lists every view and every material mapping.
5. **Draft**: `python -m render_engine render projects/<name> --preset draft`. This is fast. Check the contact sheet and the SketchUp overlays in `renders/<run>/qa/`.
6. **Final**: `python -m render_engine render projects/<name> --preset final`. It refuses to run while any material is unmapped.
7. Keep the run folder: `job.json` plus the manifests reproduce it exactly.

## 4. Quick start

```bash
pip install -r requirements.txt          # PyYAML, Pillow
# Install Blender 5.2 LTS (https://www.blender.org/download/lts/) and put it on PATH or set $BLENDER.

cd pipeline
python -m render_engine validate ../projects/demo
python -m render_engine render   ../projects/demo --style exterior_day --preset draft
python -m render_engine styles                       # exterior_day, exterior_dusk, interior_day, massing_white
```

No Blender binary? `pip install bpy==5.2.2` (Blender as a Python module, Python 3.13) and add `--in-process`.

To create a new project, copy `projects/_template` to `projects/<name>`, set the site location, and export from SketchUp into it.

Install the SketchUp exporter by copying `sketchup/render_engine_exporter.rb` and the
`sketchup/render_engine_exporter/` folder into SketchUp's Plugins folder. It needs SketchUp Pro, for FBX export.

## 5. Repository layout

```
config/
  defaults.yaml          camera standard, render presets (draft/preview/final), pinned Blender version
  styles/*.yaml          the looks: exterior_day, exterior_dusk, interior_day, massing_white
materials/
  library.yaml           studio PBR material library (source of truth)
  mapping.yaml           aliases + glob rules for legacy SketchUp names
  textures/              texture maps (Git LFS)
sketchup/                SketchUp extension: lock frame, check scenes, export
pipeline/
  render_engine/         pure-Python job builder: config, cameras, sun, materials, QA, CLI
  blender/render_job.py  applies a job inside Blender and renders. Makes no decisions of its own
projects/
  _template/             copy per architecture project
  demo/                  synthetic pavilion to try the pipeline without SketchUp
tests/                   unit tests for the camera, sun, material and job logic
tools/make_demo_project.py
docs/                    standards and how-tos
```

## 6. Roadmap

- **Phase 1: pipeline (this repo).** Exporter, camera standard, material library, four styles, QA.
- **Phase 2: calibrate on a real project.** Export a real SketchUp model, check the `qa/*_overlay.jpg` alignment, and confirm FBX scale/axes and the north-angle direction (see *Assumptions* below). Tune the styles until the studio likes them, then freeze them.
- **Phase 3: build out the material library.** Add CC0 PBR textures (Poly Haven, ambientCG) for the most used materials, and make a material preview sheet (one sphere/swatch per material, rendered with the same style).
- **Phase 4: entourage and planting.** Asset library linked by SketchUp proxy component names (`ENT_TREE_NEEM_8M` → Blender asset).
- **Phase 5: automation.** Render on push (CI with a GPU runner), and per-scene tag visibility.

## 7. Assumptions to check on the first real export

These could not be tested without SketchUp:

- **FBX scale and axes.** The exporter writes metres with Z up, and Blender's FBX importer reads the file's axis header. If the overlay is off, set `model: {scale, axis_forward, axis_up}` in `project.yaml`.
- **North angle.** The code treats SketchUp's `NorthAngle` as clockwise from the green axis. Sun mode `sketchup` sidesteps this by using SketchUp's own sun vector. For `fixed` and `solar` modes, check one shadow against SketchUp.
- **SketchUp FBX option keys** (`units`, `triangulated_faces`, …) follow the Ruby API `Model#export` documentation. If an option is ignored, export by hand once with the same settings.
