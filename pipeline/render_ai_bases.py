"""
Render the layout-accurate base images for the AI finishing pass (pipeline/render_ai_bases.py).

For every tour spot (PANORAMA_SHOTS, equirectangular) and still camera (SHOTS, perspective)
this renders, from outputs/vibgyor.blend (the model built from the CAD drawing):
  * <id>.png        - Cycles beauty render
  * <id>_depth.png  - exact camera distance, 16-bit PNG in centimetres (0 = sky / no geometry)

pipeline/finish_ai.py repaints materials and lighting on top of these, with the depth and
edges locking the geometry, so every photoreal output keeps the real room layout.

Usage:
    python -m pipeline.render_ai_bases all
    python -m pipeline.render_ai_bases pano_type_a_1_drawing_room type_a_1_drawing_room
    python -m pipeline.render_ai_bases all --stills-only --force
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import bpy

from pipeline.assets import ensure_assets
from pipeline.render import PANORAMA_SHOTS, SHOTS, configure_cycles, look_at, setup_world_lighting

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "outputs" / "ai_bases"
DEPTH_RANGE_M = 655.35  # full-scale 16-bit value, so one PNG step = 1 cm
# Glazing is skipped in the depth pass so the AI sees the balcony / sky behind it. Kept solid, it reads as a
# wall and gets painted as opaque panels; the beauty render's edges still mark the frames.
SEE_THROUGH_MATERIALS = {"Mat_Window_Glass", "Mat_Railing_Glass"}


def _camera(item: dict, kind: str, scene: bpy.types.Scene) -> bpy.types.Object:
    cam_data = bpy.data.cameras.new(name=f"AIBase_{item['id']}")
    cam_obj = bpy.data.objects.new(name=f"AIBase_{item['id']}", object_data=cam_data)
    scene.collection.objects.link(cam_obj)
    cam_obj.location = item["location"]
    if kind == "pano":
        cam_data.type = "PANO"
        if hasattr(cam_data, "panorama_type"):
            cam_data.panorama_type = "EQUIRECTANGULAR"
        else:
            cam_data.cycles.panorama_type = "EQUIRECTANGULAR"
        cam_obj.rotation_euler = (math.pi * 0.5, 0.0, math.radians(item.get("yaw_deg", 0.0)))
    else:
        cam_data.type = "PERSP"
        cam_data.lens = item["lens_mm"]
        cam_data.shift_y = item["shift_y"]
        look_at(cam_obj, item["target"])
    return cam_obj


def _use_depth_override(scene: bpy.types.Scene) -> None:
    """Every surface emits its camera distance / DEPTH_RANGE_M; the sky is black."""
    mat = bpy.data.materials.new("AIBase_DepthOverride")
    nt = mat.node_tree
    nt.nodes.clear()
    cam = nt.nodes.new("ShaderNodeCameraData")
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "DIVIDE"
    scale.inputs[1].default_value = DEPTH_RANGE_M
    emit = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(cam.outputs["View Distance"], scale.inputs[0])
    nt.links.new(scale.outputs[0], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    scene.view_layers[0].material_override = mat
    for obj in scene.objects:
        mats = {slot.material.name for slot in getattr(obj, "material_slots", []) if slot.material}
        if mats and mats <= SEE_THROUGH_MATERIALS:
            obj.visible_camera = False

    world = bpy.data.worlds.new("AIBase_DepthWorld")
    wn = world.node_tree
    wn.nodes.clear()
    bg = wn.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.0
    wn.links.new(bg.outputs["Background"], wn.nodes.new("ShaderNodeOutputWorld").inputs["Surface"])
    scene.world = world

    scene.cycles.samples = 4
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.dither_intensity = 0.0
    scene.render.image_settings.color_mode = "BW"
    scene.render.image_settings.color_depth = "16"


def _render(scene: bpy.types.Scene, cam: bpy.types.Object, size: tuple[int, int], out_path: Path) -> None:
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)


def render_ai_bases(ids: list[str], *, panos: bool = True, stills: bool = True, pano_width: int = 3072,
                    still_width: int = 1600, samples: int = 8, force: bool = False,
                    depth_only: bool = False) -> list[Path]:
    wanted = lambda item: ids == ["all"] or item["id"] in ids  # noqa: E731
    jobs = ([("pano", p) for p in PANORAMA_SHOTS if panos and wanted(p)]
            + [("still", s) for s in SHOTS if stills and wanted(s)])
    if not jobs:
        raise SystemExit(f"No spots or stills match {ids}")
    for sub in ("panos", "stills"):
        (OUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    def paths(kind: str, item: dict) -> tuple[Path, Path, tuple[int, int]]:
        folder = OUT_DIR / ("panos" if kind == "pano" else "stills")
        size = (pano_width, pano_width // 2) if kind == "pano" else (still_width, round(still_width * 9 / 16))
        return folder / f"{item['id']}.png", folder / f"{item['id']}_depth.png", size

    hdri_paths = ensure_assets(BASE_DIR / "assets")
    bpy.ops.wm.open_mainfile(filepath=str(BASE_DIR / "outputs" / "vibgyor.blend"))
    scene = bpy.context.scene
    cams = {item["id"]: _camera(item, kind, scene) for kind, item in jobs}
    written: list[Path] = []

    # Beauty renders, grouped by lighting mode
    current_mode: str | None = None
    for kind, item in sorted(jobs, key=lambda j: j[1]["mode"]):
        beauty, _, size = paths(kind, item)
        if depth_only or (beauty.exists() and not force):
            print(f"[ai-base] keep {beauty.name}", flush=True)
            continue
        t0 = time.time()
        exposure = 0.22 if item["mode"] in ("interior", "basement") else 0.16
        configure_cycles(scene, samples=samples, exposure=exposure)
        if current_mode != item["mode"]:
            setup_world_lighting(scene, item["mode"], hdri_paths)
            current_mode = item["mode"]
        _render(scene, cams[item["id"]], size, beauty)
        written.append(beauty)
        print(f"[ai-base] {beauty.name} {size[0]}x{size[1]} in {time.time() - t0:.0f}s", flush=True)

    # Depth renders (fast: one emission shader, no bounces)
    _use_depth_override(scene)
    for kind, item in jobs:
        _, depth, size = paths(kind, item)
        if depth.exists() and not (force or depth_only):
            continue
        t0 = time.time()
        _render(scene, cams[item["id"]], size, depth)
        written.append(depth)
        print(f"[ai-base] {depth.name} in {time.time() - t0:.0f}s", flush=True)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Blender base + depth images for the AI finishing pass.")
    parser.add_argument("ids", nargs="+", help="Spot / still ids, or 'all'")
    parser.add_argument("--panos-only", action="store_true")
    parser.add_argument("--stills-only", action="store_true")
    parser.add_argument("--pano-width", type=int, default=3072)
    parser.add_argument("--still-width", type=int, default=1600)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="Re-render files that already exist")
    parser.add_argument("--depth-only", action="store_true", help="Redo only the depth maps, keep beauty renders")
    args = parser.parse_args()
    render_ai_bases(args.ids, panos=not args.stills_only, stills=not args.panos_only,
                    pano_width=args.pano_width, still_width=args.still_width,
                    samples=args.samples, force=args.force, depth_only=args.depth_only)


if __name__ == "__main__":
    main()
