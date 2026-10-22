"""Build ComfyUI API-format workflows.

The graph for one view:

  input image -> resize (keeps aspect) -+-> depth (Depth Anything V2) -> ControlNet --+
                                        +-> edges (Canny) ------------> ControlNet --+-> sampler -> decode -> [upscale] -> save
                                        +-> VAE encode (img2img: keeps indicative     |
                                            textures, colours and layout) ------------+
  prompt (+ style reference via Redux) -----------------------------------------------+

Node class names and inputs follow ComfyUI core, plus DepthAnythingV2Preprocessor
from comfyui_controlnet_aux.
"""

from __future__ import annotations

from typing import Any


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}

    def add(self, class_type: str, **inputs: Any) -> str:
        node_id = str(len(self.nodes) + 1)
        self.nodes[node_id] = {"class_type": class_type, "inputs": inputs}
        return node_id


def out(node_id: str, index: int = 0) -> list:
    return [node_id, index]


def build_graph(
    settings: dict[str, Any],
    prompt: dict[str, str],
    image_name: str,
    size: tuple[int, int],
    filename_prefix: str,
) -> dict[str, dict[str, Any]]:
    eng = settings["engine"]
    fid = settings["fidelity"]
    smp = settings["sampler"]
    width, height = size
    g = Graph()

    # --- models ------------------------------------------------------------------
    if eng["family"] == "flux":
        model = out(g.add("UNETLoader", unet_name=eng["unet"], weight_dtype=eng.get("weight_dtype", "default")))
        clip = out(g.add("DualCLIPLoader", clip_name1=eng["t5"], clip_name2=eng["clip_l"], type="flux"))
        vae = out(g.add("VAELoader", vae_name=eng["vae"]))
    elif eng["family"] == "sdxl":
        ckpt = g.add("CheckpointLoaderSimple", ckpt_name=eng["checkpoint"])
        model, clip, vae = out(ckpt, 0), out(ckpt, 1), out(ckpt, 2)
    else:
        raise ValueError(f"unknown engine family {eng['family']}")

    # --- input image -------------------------------------------------------------
    loaded = g.add("LoadImage", image=image_name)
    image = out(g.add("ImageScale", image=out(loaded), upscale_method="lanczos",
                      width=width, height=height, crop="disabled"))

    # --- conditioning ------------------------------------------------------------
    positive = out(g.add("CLIPTextEncode", text=prompt["positive"], clip=clip))
    negative = out(g.add("CLIPTextEncode", text=prompt.get("negative", ""), clip=clip))
    if eng["family"] == "flux":
        positive = out(g.add("FluxGuidance", conditioning=positive, guidance=smp["guidance"]))

    ref = settings["preset"].get("style_reference")
    if ref and eng["family"] == "flux" and settings["preset"].get("style_strength", 0) > 0:
        vision = out(g.add("CLIPVisionLoader", clip_name=eng["clip_vision"]))
        ref_img = out(g.add("LoadImage", image=settings["_style_reference_name"]))
        encoded = out(g.add("CLIPVisionEncode", clip_vision=vision, image=ref_img, crop="center"))
        style = out(g.add("StyleModelLoader", style_model_name=eng["redux"]))
        positive = out(g.add("StyleModelApply", conditioning=positive, style_model=style,
                             clip_vision_output=encoded,
                             strength=float(settings["preset"]["style_strength"]), strength_type="multiply"))

    # --- structure controls ------------------------------------------------------
    controlnet = out(g.add("ControlNetLoader", control_net_name=eng["controlnet"]))
    controls = []
    if fid["depth"]["strength"] > 0:
        depth = out(g.add("DepthAnythingV2Preprocessor", image=image, ckpt_name=settings["engine"]["depth_model"],
                          resolution=max(512, min(2048, round(max(width, height) / 64) * 64))))
        controls.append(("depth", depth, fid["depth"]))
    if fid["edges"]["strength"] > 0:
        edges = out(g.add("Canny", image=image, low_threshold=fid["edges"]["low"], high_threshold=fid["edges"]["high"]))
        controls.append(("canny/lineart/anime_lineart/mlsd", edges, fid["edges"]))
    for union_type, hint, c in controls:
        net = controlnet
        if eng["family"] == "sdxl":
            # xinsir union needs the control type; FLUX Union Pro 2.0 infers it from the image.
            net = out(g.add("SetUnionControlNetType", control_net=controlnet, type=union_type))
        applied = g.add("ControlNetApplyAdvanced", positive=positive, negative=negative, control_net=net,
                        image=hint, strength=float(c["strength"]), start_percent=0.0,
                        end_percent=float(c["end"]), vae=vae)
        positive, negative = out(applied, 0), out(applied, 1)

    # --- sample ------------------------------------------------------------------
    latent = out(g.add("VAEEncode", pixels=image, vae=vae))
    sampled = out(g.add("KSampler", model=model, seed=int(settings["seed"]), steps=int(smp["steps"]),
                        cfg=float(smp["cfg"]), sampler_name=smp["sampler_name"], scheduler=smp["scheduler"],
                        positive=positive, negative=negative, latent_image=latent,
                        denoise=float(fid["denoise"])))
    result = out(g.add("VAEDecode", samples=sampled, vae=vae))

    up = settings.get("upscale")
    if up:
        upscaler = out(g.add("UpscaleModelLoader", model_name=eng["upscale_model"]))
        big = out(g.add("ImageUpscaleWithModel", upscale_model=upscaler, image=result))
        result = out(g.add("ImageScale", image=big, upscale_method="lanczos",
                           width=width * int(up["factor"]), height=height * int(up["factor"]), crop="disabled"))

    g.add("SaveImage", images=result, filename_prefix=filename_prefix)
    return g.nodes
