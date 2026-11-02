# Recommended workflow: hosted engine + material colour key

The default system. It needs no GPU, renders in about a minute per view, and is
built for one goal: **all views of a building agree with each other.**

## How a set is made consistent

1. **Hero first.** One view (`ai.hero`) is rendered first, from your SketchUp
   view, its material colour key, and optional texture swatches.
2. **Hero as reference.** Every other view is sent together with the hero
   render and the instruction "same building: use exactly the same materials,
   colours, textures, lighting, sky".
3. **Shade lock.** The colour key tells the script exactly which pixels are
   which material. Each material is pulled to the hero's colour for that
   material in every view, so the cedar is the same cedar everywhere.
4. **Scorecard.** Per material, the largest colour difference between views
   (ΔE: under 3 reads as identical), plus how much of each SketchUp view's
   linework survived (geometry kept or changed).

## One-time setup

1. Create an account at **fal.ai**, then go to *Dashboard › Keys*, create a key,
   and add about $5 of credit.
2. Make the key available as the environment variable `FAL_KEY`. In a Claude
   cloud session, add it as an environment secret. On your PC, run
   `setx FAL_KEY "<key>"` and open a new terminal.
3. If you run in a Claude cloud session, allow `fal.run`, `queue.fal.run` and
   `fal.media` (plus subdomains) under the environment's Network access.
4. `pip install -r requirements.txt`

## Exporting from SketchUp (per view)

| File in `projects/<name>/input/` | SketchUp style |
|---|---|
| `EXT-01 Entrance.png` | Your normal presentation style: textures and shadows on, one fixed shadow date/time for all views, about 2000 px wide |
| `EXT-01 Entrance.key.png` | **Material key**: textures off, edges and profiles off, shadows off, sky and ground off. Each material painted in its own pure colour. Same camera, same size |

To make the key style, duplicate the model's materials as flat colours (or use
the *Shaded* face style with textures off) and pick clearly different colours:
red, blue, yellow, green, magenta, cyan, orange, purple. Then map them in
`project.yaml`:

```yaml
ai:
  engine: nano_banana_pro
  hero: "EXT-01 Entrance"
  color_key:
    "#FF0000": WOOD_CEDAR_CLADDING
    "#0000FF": GLASS_CLEAR
    "#FFFF00": METAL_STANDING_SEAM_CHARCOAL
```

The key is optional: without it the materials are described in words and each
view is colour-matched as a whole. With it, consistency is per material and
measurable.

## Rendering

```bash
cd pipeline
python -m render_engine render ../projects/<name> --dry-run          # check prompts, no cost
python -m render_engine render ../projects/<name> --views "EXT-01 Entrance"   # hero only
# happy with the hero? render the rest against it:
python -m render_engine render ../projects/<name> --views "EXT-02 Side" "EXT-03 Corner" \
       --hero-from ../projects/<name>/renders/<hero run folder>
python -m render_engine score ../projects/<name>/renders/<run folder>
```

Each run folder holds the final images, `raw/` (before the shade lock),
`requests/` (the exact prompts and the reference images sent), the
manifests, `qa/scorecard.json`, a contact sheet, and overlays on your SketchUp
views.

## Engines

| `--engine` | Model | Notes |
|---|---|---|
| `nano_banana_pro` (default) | Google Gemini 3 Pro Image | Best at following "keep the geometry" and multi-image instructions. No seed, so reruns vary. |
| `flux2_pro` | Black Forest Labs FLUX.2 [pro] | Fixed seed, so reruns repeat. Try it if the default drifts. |

Model names and parameters live in `config/ai/engines.yaml`. If fal renames a
parameter, fix it there without touching the code.

## Texture swatches (optional)

To pin a specific product (a particular brick, a cladding sample), add a photo
to `materials/swatches/` and reference it in the library:

```yaml
  BRICK_WIRECUT_RED:
    swatch: swatches/brick_wirecut_red.jpg
```

It's sent along with the views that contain that material.
