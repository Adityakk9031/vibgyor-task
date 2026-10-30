"""
Batch renderer for remaining interior stills with updated 2K PBR materials and 22mm lenses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import bpy
from pipeline.assets import ensure_assets
from pipeline.render import SHOTS, configure_cycles, look_at, setup_world_lighting


def main():
    base = Path(__file__).resolve().parent.parent
    hdri_paths = ensure_assets(base / "assets")
    bpy.ops.wm.open_mainfile(filepath=str(base / "outputs/vibgyor.blend"))
    scene = bpy.context.scene

    configure_cycles(scene, samples=4, exposure=0.18)
    setup_world_lighting(scene, "interior", hdri_paths)

    target_ids = [
        "type_a_4_second_bedroom",
        "type_b_1_drawing_room",
        "type_b_2_kitchen_dining",
        "type_b_3_master_bedroom",
        "type_b_4_second_bedroom",
    ]

    for s_id in target_ids:
        shot = next(s for s in SHOTS if s["id"] == s_id)
        print(f"\n[batch] Rendering {shot['id']} ...")
        cam_data = bpy.data.cameras.new(name=f"Cam_{shot['id']}")
        cam_data.type = "PERSP"
        cam_data.lens = 22.0
        cam_obj = bpy.data.objects.new(name=f"Cam_{shot['id']}", object_data=cam_data)
        scene.collection.objects.link(cam_obj)
        cam_obj.location = shot["location"]
        look_at(cam_obj, shot["target"])
        scene.camera = cam_obj

        scene.render.resolution_x = 2560
        scene.render.resolution_y = 1440
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"

        out_path = base / "outputs" / shot["filename"]
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        print(f"[batch] Saved {out_path} ({out_path.stat().st_size // 1024} KB)")

        viewer_path = base / "viewer" / shot["filename"]
        shutil.copy2(out_path, viewer_path)
        print(f"[batch] Synced to {viewer_path}")


if __name__ == "__main__":
    main()
