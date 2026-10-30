# Superseded: prompt-only image scripts

These scripts produced the earlier "photoreal" stills and are **not part of the pipeline**. They send a text
prompt to a public image service (FLUX.1-schnell Space, Stable Horde) and save whatever comes back, so the
images have no link to the CAD drawing or the 3D model. `build_photoreal_panoramas.py` stretched two of those
stills around a sphere. `ai_render.py` uploads renders to a public temporary file host.

The delivered images now come from `pipeline/render_ai_bases.py` → `pipeline/finish_ai.py` →
`pipeline/import_ai_results.py` (see the README). Kept only as a record; safe to delete.
