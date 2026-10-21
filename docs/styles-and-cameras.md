# Styles and camera standard

## Styles (`config/styles/*.yaml`)

A style is the whole look apart from geometry and materials:

| Section | Controls |
|---|---|
| `environment` | `sky` (physical sky model), `hdri` (image + rotation + strength) or flat `color`. `camera_background` changes only what the camera sees directly. |
| `sun` | `fixed` (same bearing and elevation on every project), `solar` (site lat/long + date/time), or `sketchup` (SketchUp's shadow settings). Plus strength, softness (`angle_deg`) and colour. |
| `ground` | infinite-looking ground plane and its material |
| `color` | AgX view transform, look, exposure and gamma. Fixed, never automatic. |
| `material_override` | e.g. turn everything white except glass (`massing_white`) |

Use one style for a whole presentation set. To tweak a style for a single
project, put only the changed keys under `style_settings:` in
`project.yaml`, or in `projects/<name>/styles/<style>.yaml`. The tweak changes
the `look_hash`, so the set stays traceable.

To add an HDRI style, put the `.hdr` or `.exr` in `environments/`:

```yaml
environment:
  type: hdri
  hdri: {path: environments/overcast_soft_4k.exr, strength: 1.0, rotation_deg: 120}
sun: {mode: fixed, azimuth_deg: 0, elevation_deg: 0, strength: 0}   # HDRI provides all light
```

## Camera standard (`config/defaults.yaml → camera`)

For each scene, the job builder:

1. Reads the view type from the scene-name prefix (`EXT`, `INT`, `AER`, `DET` or `ELV`).
2. **Locks eye height** (EXT): eye Z = `site.ground_z_m` + 1.6 m. The target
   moves by the same amount, so the viewing direction is kept.
3. **Sets the lens** from SketchUp's field of view on a 36 mm sensor, then
   applies the `lens_policy`:
   - `snap` (default): nearest allowed focal length for that view type
   - `fixed`: always the type's `lens_mm`
   - `sketchup`: exactly as composed (least consistent)
4. **Two-point perspective**: levels the camera and moves the image with
   vertical lens shift (`shift_y = f·tan(pitch) / sensor`). Verticals stay
   vertical and the subject stays where it was framed. Skipped above 25° of
   pitch, where it would distort.
5. **Orthographic** for `ELV`: SketchUp's parallel-projection height is used
   as the view height.

Every adjustment is printed by `render` and stored in each image's manifest
(`camera.notes`).

Per-view exceptions go in `project.yaml → scene_overrides`. Keep them rare,
because each one is a deliberate inconsistency.

## Presets

`draft`, `preview` and `final` differ only in quality: samples, noise
threshold, resolution percentage and bit depth. They share the aspect ratio,
cameras and look, and therefore the `look_hash`. A draft frames exactly like
the final.
