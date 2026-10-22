"""Image-to-image track: SketchUp view exports in, consistent photoreal renders out.

settings.py  resolves engine + fidelity + quality + scene preset + project into one dict
graph.py     turns settings + one input image into a ComfyUI API workflow
comfy.py     minimal ComfyUI HTTP client (upload, queue, wait, download)
harmonize.py colour-matches every image in a set to one anchor
run.py       orchestrates a set and writes manifests
"""
