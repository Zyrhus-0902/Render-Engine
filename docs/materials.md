# Material library

`materials/library.yaml` is the only place a material's appearance is defined.
SketchUp names select a definition, and the definition decides the look.

## How a SketchUp material is resolved

1. `<project>/materials.yaml → overrides`
2. exact library id (after normalising case, spaces, dashes and `#1` / `.001` suffixes)
3. `aliases` in `materials/mapping.yaml` and `<project>/materials.yaml`
4. `patterns` (glob, first match wins), e.g. `*glass*` → `GLASS_CLEAR`
5. otherwise **unmapped**: magenta in draft and preview, an error in final

Run `python -m render_engine validate projects/<name>` to see each mapping and why it was chosen.

## Adding a material

```yaml
  STONE_JAISALMER:
    base_color: "#C8A96E"        # used when no texture, and as a sanity reference
    roughness: 0.7
    textures:                    # optional, paths relative to materials/
      base_color: textures/stone_jaisalmer/albedo.jpg
      roughness:  textures/stone_jaisalmer/roughness.jpg
      normal:     textures/stone_jaisalmer/normal.png
    size_m: [0.6, 0.3]           # real-world size of one texture tile
    projection: box              # world-space: no stretched or misaligned UVs
```

Rules that keep materials consistent:

- **Real-world scale.** `size_m` is the physical tile size. Box projection uses
  world coordinates, so a wall and the column next to it share the same
  texture scale and continuity.
- **Plausible albedo.** Keep base colours at or below about `#F0F0F0` (fresh
  snow), and keep dark materials above about `#1A1A1A`. Exposure is fixed per
  style, so a too-bright material will blow out in every view.
- **CC0 sources.** [Poly Haven](https://polyhaven.com/textures) and
  [ambientCG](https://ambientcg.com) provide free PBR sets. Put them in
  `materials/textures/<id>/` (stored with Git LFS).
- **Change with care.** Changing a definition changes every project's
  `look_hash`. That's intended: old renders keep their manifests, which record
  the old values.

## Types

- `principled` (default): opaque surfaces. Supports `metallic`, `coat` and
  `specular`, plus `emission_*` for light panels.
- `glass`: transmissive. Set `tint`, `roughness` (0 for clear, 0.3 or more for
  frosted) and `ior`. Water uses this type with `ior: 1.33`.
