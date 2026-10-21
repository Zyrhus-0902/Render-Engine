# SketchUp modelling standards

The renderer can only be consistent if the models it receives are. These rules
are what the exporter's **Check scenes** command looks for.

## Scenes = render views

- One SketchUp scene per render view. Scenes that are not views (working
  scenes) can be deleted from a copy before export, or rendered with `--views`.
- Start the name with the view type, a dash, and a number, then a description:

  | Prefix | Use | Camera rule |
  |---|---|---|
  | `EXT-` | exterior, eye level | eye locked to 1.6 m, two-point, 24/28/35 mm |
  | `INT-` | interior, eye level | two-point, 18/24 mm, eye height as modelled |
  | `AER-` | aerial / bird's eye | true perspective, 35/50 mm |
  | `DET-` | detail / close-up | two-point, 50 mm |
  | `ELV-` | elevation / section | orthographic (set Camera › Parallel Projection) |

  Example: `EXT-01 Entrance`, `INT-03 Living to garden`, `AER-01 Site`.
- Run **Lock scenes to render frame** once. Every scene then shows the 3:2
  render frame (grey bars), so you compose exactly what will be rendered.
- Use **Camera › Field of View** freely. The pipeline snaps it to the nearest
  studio lens, so a 40° SketchUp view becomes 28 mm or 35 mm. The CLI prints
  every change it makes.
- Don't tilt eye-level cameras to fix verticals. The pipeline levels the camera
  and uses lens shift. Use SketchUp's *Two-Point Perspective* only for previewing.

## Materials

- Name every material after an id in `materials/library.yaml`, e.g.
  `CONC_BOARDFORM`, `GLASS_CLEAR`, `WOOD_TEAK`. Case, spaces and dashes don't
  matter (`Conc Boardform` works).
- In SketchUp the material only needs to be *recognisable*. Its colour and
  texture are replaced at render time.
- If the right material doesn't exist, add it to the library (see
  [materials.md](materials.md)). Don't invent a one-off name in the model.
- Paint faces, not groups, wherever it matters. Faces with the Default material
  render as `PLASTER_WHITE`.
- Glass must be a single face or a thin solid. Both work, but be consistent
  within a project.

## Geometry hygiene

- Model in real units, with the ground at Z = 0 or the level set in
  `project.yaml → site.ground_z_m`.
- Front faces (white) out. Reversed faces can lose their material in FBX export.
- Hide or delete construction geometry, guides and 2D entourage before export.
  The exporter takes the model *as visible*.
- Set **Window › Model Info › Geo-location** so `solar` and `sketchup` sun modes are correct.
- Keep each project in its own `.skp` and commit it with Git LFS if you want
  renders to be fully reproducible from the repo.
