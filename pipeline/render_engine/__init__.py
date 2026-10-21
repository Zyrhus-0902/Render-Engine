"""Render Engine: consistent architectural renders from SketchUp scenes.

Pure-Python modules (config, cameras, sun, materials, job) resolve every
decision ahead of time into a single job JSON. The Blender side
(pipeline/blender/render_job.py) only applies that job, so every render in a
set is built from exactly the same resolved numbers.
"""

__version__ = "0.1.0"
