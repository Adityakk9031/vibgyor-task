"""
Stage 4: Export the generated 3D model (.blend) to a web-ready glTF Binary (.glb)
of 40 MB or less, preserving object hierarchy, custom properties (extras), and
PBR materials for the interactive Three.js viewer.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import bpy


def export_glb(
    blend_path: str | Path = "outputs/vibgyor.blend",
    output_glb_path: str | Path = "outputs/vibgyor.glb",
    viewer_public_glb_path: str | Path | None = "viewer/vibgyor.glb",
) -> Path:
    base_dir = Path(blend_path).resolve().parent.parent
    in_blend = base_dir / blend_path
    out_glb = base_dir / output_glb_path
    out_glb.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(in_blend))

    # Convert any FONT curve objects (like the 3D 'VIBGYOR' entrance sign) to mesh so glTF exports them
    for obj in list(bpy.data.objects):
        if obj.type == "FONT":
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.convert(target="MESH")
            obj.select_set(False)

    # Export to .glb with custom properties (extras) enabled for floor/flat interactive picking
    bpy.ops.export_scene.gltf(
        filepath=str(out_glb),
        export_format="GLB",
        export_extras=True,
        export_yup=True,
        export_apply=True,
        export_materials="EXPORT",
    )

    size_mb = out_glb.stat().st_size / (1024 * 1024)
    print(f"[export] Exported web model to {out_glb} ({size_mb:.2f} MB <= 40 MB limit)")
    if size_mb > 40.0:
        raise RuntimeError(f"Exported .glb size ({size_mb:.2f} MB) exceeds 40 MB limit!")

    if viewer_public_glb_path:
        viewer_glb = base_dir / viewer_public_glb_path
        viewer_glb.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_glb, viewer_glb)
        print(f"[export] Copied .glb to {viewer_glb} for web viewer")

    return out_glb


if __name__ == "__main__":
    export_glb()
