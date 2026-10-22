# Image track: SketchUp views to consistent renders

You export views from SketchUp as images. The pipeline turns every image in a
set into a photoreal render with the **same scene setting, materials and
colour grade**, and keeps each view's geometry and framing.

## How consistency is held

| What | How |
|---|---|
| Geometry, view range, focal point | Not re-imagined. A **depth map** and an **edge map** of your image steer the AI through ControlNet, and the image itself is the starting point (img2img). The output keeps your frame and aspect ratio. |
| Scene setting (light, sky, weather, mood) | A **preset** (`config/ai/presets/`) gives the same scene prompt, seed and optional **style reference photo** (FLUX Redux) to every view in a set. |
| Materials | The project's **material palette** (`project.yaml → ai.materials`, ids from `materials/library.yaml`) is written into every prompt. The indicative textures in your export show *where* each material goes. |
| Colour and white balance | After generation, every image is **colour-matched** to one anchor image (CIELAB statistics), which removes image-to-image drift. Raw outputs are kept in `raw/`. |
| Repeatability | Fixed seed, fixed models, and a `look_hash` in every image's manifest. `qa` fails if a set mixes looks. |

## Choices per run

```bash
python -m render_engine render projects/<name> --preset golden_hour --fidelity balanced --quality final
```

| Option | Values | Effect |
|---|---|---|
| `--preset` | `day_clear`, `overcast_soft`, `golden_hour`, `blue_hour`, `night`, `monsoon`, `interior_daylight`, `interior_evening` | Scene setting. Add your own in `config/ai/presets/`. |
| `--fidelity` | `strict`, `balanced`, `concept` | How tightly the output follows your image (`config/ai/fidelity.yaml`). |
| `--quality` | `draft`, `final` | Speed only: fewer steps and lower resolution for drafts, plus a 2x upscale for finals. Same look hash. |
| `--engine` | `flux_dev`, `sdxl` | `flux_dev` is best but **non-commercial**. `sdxl` is cleared for client work. |
| `--views` | file names | Render only some views. |
| `--dry-run` | | Writes the ComfyUI workflows to `graphs/` without rendering. Open one in ComfyUI to inspect or tweak it. |

## Exporting from SketchUp

- Name one scene per view: `EXT-01 Entrance`, `INT-02 Living`, `AER-01 Site`, `DET-01 …`.
  The prefix picks the camera wording in the prompt (`config/ai/views.yaml`).
- Use one SketchUp **style** for all exports: textures on, shadows on, thin or
  no edges, no sketchy lines. Save it as e.g. *Render Export* and reuse it.
- **File › Export › 2D Graphic** as PNG, about 2000 px wide, into
  `projects/<name>/input/` with the scene name as the file name.
- The textures only need to be indicative, but keep each material visibly
  distinct: the AI uses them to tell where each material goes.

## Setting up the render PC (Windows + NVIDIA, 24 GB)

1. **ComfyUI**: download the Windows portable build from
   <https://github.com/comfyanonymous/ComfyUI/releases>, unzip it, and run
   `run_nvidia_gpu.bat`. It serves on <http://127.0.0.1:8188>.
2. **ComfyUI-Manager** (custom node manager), then install the custom node
   **comfyui_controlnet_aux**. It provides the depth estimator (Depth Anything V2
   downloads itself on first use).
3. **Models** go into `ComfyUI/models/…`. The file names must match `config/ai/engines.yaml`:

   | File | Folder | Source (Hugging Face) |
   |---|---|---|
   | `flux1-dev.safetensors` | `diffusion_models/` | black-forest-labs/FLUX.1-dev (accept the licence first) |
   | `ae.safetensors` | `vae/` | black-forest-labs/FLUX.1-dev |
   | `clip_l.safetensors`, `t5xxl_fp16.safetensors` | `text_encoders/` | comfyanonymous/flux_text_encoders |
   | `FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors` | `controlnet/` | Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0 (rename `diffusion_pytorch_model.safetensors`) |
   | `flux1-redux-dev.safetensors` | `style_models/` | black-forest-labs/FLUX.1-Redux-dev (only for style references) |
   | `sigclip_vision_patch14_384.safetensors` | `clip_vision/` | Comfy-Org/sigclip_vision_384 (only for style references) |
   | `RealESRGAN_x4plus.pth` | `upscale_models/` | github.com/xinntao/Real-ESRGAN releases (final quality) |

   For client work with `--engine sdxl`, add `sd_xl_base_1.0.safetensors` (or
   a photoreal SDXL fine-tune) to `checkpoints/`, and xinsir's
   `controlnet-union-sdxl-1.0` *promax* file, renamed to
   `controlnet-union-sdxl-1.0-promax.safetensors`, to `controlnet/`.
4. **This repo** on the same PC: install Python 3.11+, run
   `pip install -r requirements.txt`, then run commands from `pipeline/`. To
   use ComfyUI on another machine, pass `--comfy http://<pc>:8188` or set
   `COMFYUI_URL`.

If a model file is missing, the error names the node and the file it expected.

## Making a new preset

```yaml
# config/ai/presets/harsh_noon.yaml
extends: _base
description: Midday sun. Short hard shadows, high contrast.
scene: "harsh midday sun, short hard shadows, deep blue sky, high contrast"
style_reference: noon_reference.jpg   # optional photo in config/ai/references/
style_strength: 0.3
harmonize: {anchor: style_reference, strength: 0.8}
```

Then render one view at `--quality draft` and compare it with an existing
preset. Once the studio likes the preset, don't edit it: copy it to a new
name. That way older sets stay reproducible.

## Limits to know

- Generative models invent small things: planting, people, fixtures, and at
  `balanced` sometimes window divisions. Use `strict` for submissions where
  every opening matters, and check `qa/*_overlay.jpg` (the render blended over
  your export).
- Text, signage and exact patterns (brick bonds, tile joints) aren't reliable.
- The same seed doesn't make different views *identical*. It makes them
  consistent: harmonisation plus the shared preset carry the look.
