"""
Stage 3: Render photorealistic still images (>= 2560 px wide) and the bonus
4096 x 2048 360-degree equirectangular panorama of the Type A drawing room
using Blender Cycles.

Cameras and lighting are defined entirely in code:
  1. shot_1_eye_level_day.png      - Eye level from the main road (Day)
  2. shot_2_front_corner_dusk.png  - Front corner with interior & facade lights on (Dusk)
  3. shot_3_aerial_day.png         - Aerial, roughly 45 degrees showing building on plot (Day)
  4. shot_4_entrance_closeup.png   - Close-up of entrance canopy & VIBGYOR wall (Day)
  5. bonus_type_a_panorama_360.png - 360° equirectangular panorama (4096x2048) of Type A Drawing Room
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

from pipeline.assets import ensure_assets


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    loc = obj.location
    direction = Vector(target) - loc
    quat = direction.to_track_quat("-Z", "Y")
    obj.rotation_euler = quat.to_euler()


def setup_world_lighting(
    scene: bpy.types.Scene,
    mode: str,
    hdri_paths: dict[str, Path],
) -> None:
    """Sets up HDRI sky + Sun light + interior/facade point lights for Day, Dusk, or Interior mode."""
    if scene.world is None:
        scene.world = bpy.data.worlds.new("VibgyorWorld")
    world = scene.world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    out_node = nodes.new(type="ShaderNodeOutputWorld")
    bg_node = nodes.new(type="ShaderNodeBackground")
    links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])

    hdri_file = hdri_paths.get(mode) or hdri_paths.get("day")
    if hdri_file and hdri_file.exists():
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        mapping = nodes.new(type="ShaderNodeMapping")
        # Rotate HDRI slightly so sun direction aligns with camera highlights
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(45.0 if mode == "day" else 160.0))
        env_tex = nodes.new(type="ShaderNodeTexEnvironment")
        env_tex.image = bpy.data.images.load(str(hdri_file), check_existing=True)
        links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
        links.new(env_tex.outputs["Color"], bg_node.inputs["Color"])
        bg_node.inputs["Strength"].default_value = 1.15 if mode == "day" else (0.32 if mode == "dusk" else 1.4)
    else:
        sky_tex = nodes.new(type="ShaderNodeTexSky")
        sky_tex.sky_type = "NISHITA"
        sky_tex.sun_elevation = math.radians(38.0 if mode == "day" else 3.0)
        sky_tex.sun_rotation = math.radians(135.0)
        links.new(sky_tex.outputs["Color"], bg_node.inputs["Color"])
        bg_node.inputs["Strength"].default_value = 1.0 if mode == "day" else 0.25

    # Remove any old dynamic lights before adding mode-specific lights
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Light_Dynamic_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    # Add Sun lamp
    sun_data = bpy.data.lights.new(name="Light_Dynamic_Sun", type="SUN")
    sun_obj = bpy.data.objects.new(name="Light_Dynamic_Sun", object_data=sun_data)
    scene.collection.objects.link(sun_obj)
    if mode == "day":
        sun_data.energy = 3.8
        sun_data.color = (1.0, 0.96, 0.90)
        sun_data.angle = math.radians(1.5)  # soft sun shadows
        sun_obj.location = (25.0, -30.0, 40.0)
        look_at(sun_obj, (7.0, 15.0, 10.0))
    elif mode == "dusk":
        sun_data.energy = 0.45
        sun_data.color = (0.55, 0.68, 1.0)
        sun_data.angle = math.radians(5.0)
        sun_obj.location = (-25.0, -25.0, 18.0)
        look_at(sun_obj, (7.0, 15.0, 10.0))

    # Adjust emissive LED material strength & warm interior room lights for Dusk vs Day
    led_mat = bpy.data.materials.get("Mat_Warm_LED")
    sign_mat = bpy.data.materials.get("Mat_Sign_Glow")
    if led_mat and led_mat.use_nodes:
        bsdf = led_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 28.0 if mode in ("dusk", "interior") else 6.0
    if sign_mat and sign_mat.use_nodes:
        bsdf = sign_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 35.0 if mode == "dusk" else 14.0

    if mode == "dusk":
        # Add warm interior point lights on each residential floor & under the entrance canopy
        for fl in range(1, 8):
            zf = 3.30 + (fl - 1) * 3.05 + 2.35
            for idx, (lx, ly, power) in enumerate(
                [
                    (8.5, 4.5, 450.0),    # front right bedroom/balcony glow
                    (4.5, 6.2, 420.0),    # front left bedroom/balcony glow
                    (9.5, 14.0, 380.0),   # drawing room east balcony glow
                    (2.8, 16.5, 220.0),   # west utility/window glow
                    (1.5, 27.5, 350.0),   # Type B west balcony glow
                ]
            ):
                ldata = bpy.data.lights.new(name=f"Light_Dynamic_Fl{fl}_{idx}", type="POINT")
                ldata.energy = power
                ldata.color = (1.0, 0.78, 0.48)
                ldata.shadow_soft_size = 0.65
                lobj = bpy.data.objects.new(name=f"Light_Dynamic_Fl{fl}_{idx}", object_data=ldata)
                lobj.location = (lx, ly, zf)
                scene.collection.objects.link(lobj)

        # Warm ground entrance & sign uplights
        for idx, (lx, ly, lz, power) in enumerate(
            [
                (1.5, 0.5, 2.75, 650.0),   # entrance canopy glow
                (10.5, -6.2, 0.6, 380.0),  # VIBGYOR sign wall uplight
            ]
        ):
            ldata = bpy.data.lights.new(name=f"Light_Dynamic_Ground_{idx}", type="POINT")
            ldata.energy = power
            ldata.color = (1.0, 0.80, 0.52)
            ldata.shadow_soft_size = 0.80
            lobj = bpy.data.objects.new(name=f"Light_Dynamic_Ground_{idx}", object_data=ldata)
            lobj.location = (lx, ly, lz)
            scene.collection.objects.link(lobj)

    elif mode == "interior":
        # Warm soft area/point lights inside Floor 1 Type A Drawing & Dining Room (z_floor = 3.30m)
        for idx, (lx, ly, lz, power) in enumerate(
            [
                (8.5, 13.7, 5.85, 320.0),  # main drawing room ceiling fill
                (7.2, 10.6, 5.85, 260.0),  # dining room ceiling fill
                (4.6, 11.2, 5.85, 180.0),  # kitchen island pendant fill
            ]
        ):
            ldata = bpy.data.lights.new(name=f"Light_Dynamic_Int_{idx}", type="POINT")
            ldata.energy = power
            ldata.color = (1.0, 0.91, 0.78)
            ldata.shadow_soft_size = 1.1
            lobj = bpy.data.objects.new(name=f"Light_Dynamic_Int_{idx}", object_data=ldata)
            lobj.location = (lx, ly, lz)
            scene.collection.objects.link(lobj)


def configure_cycles(scene: bpy.types.Scene, samples: int = 18) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.05
    if hasattr(scene.cycles, "use_denoising"):
        scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3

    # Natural photographic tone mapping (AgX / Filmic)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = 0.15


SHOTS = [
    {
        "id": "shot_1_eye_level_day",
        "filename": "shot_1_eye_level_day.png",
        "description": "Shot 1: Eye level from the main road (Day) - front facade as a passer-by sees it",
        "mode": "day",
        "location": (0.5, -25.5, 1.75),
        "target": (6.2, 4.0, 11.2),
        "lens_mm": 18.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 18,
    },
    {
        "id": "shot_2_front_corner_dusk",
        "filename": "shot_2_front_corner_dusk.png",
        "description": "Shot 2: Front corner (Dusk) - interior and facade lights on",
        "mode": "dusk",
        "location": (-13.5, -21.0, 2.20),
        "target": (6.0, 7.5, 11.0),
        "lens_mm": 19.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 18,
    },
    {
        "id": "shot_3_aerial_day",
        "filename": "shot_3_aerial_day.png",
        "description": "Shot 3: Aerial, roughly 45 degrees (Day) - the building on its plot",
        "mode": "day",
        "location": (-23.0, -27.0, 35.0),
        "target": (6.5, 14.0, 9.5),
        "lens_mm": 26.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 18,
    },
    {
        "id": "shot_4_entrance_closeup",
        "filename": "shot_4_entrance_closeup.png",
        "description": "Shot 4: Close-up (Day) - the entrance canopy, gate and VIBGYOR signage",
        "mode": "day",
        "location": (3.0, -12.5, 1.65),
        "target": (4.8, -0.5, 2.15),
        "lens_mm": 28.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 18,
    },
]


def render_all(
    blend_path: str | Path = "outputs/vibgyor.blend",
    output_dir: str | Path = "outputs",
    render_bonus_panorama: bool = True,
    only_shot_id: str | None = None,
) -> list[Path]:
    base_dir = Path(blend_path).resolve().parent.parent
    in_blend = base_dir / blend_path
    out_dir = base_dir / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    hdri_paths = ensure_assets(base_dir / "assets")
    bpy.ops.wm.open_mainfile(filepath=str(in_blend))
    scene = bpy.context.scene

    # Ensure organic tree meshes use smooth shading
    for obj_name in ("Landscape_Tree_Canopies", "Landscape_Tree_Trunks"):
        obj = bpy.data.objects.get(obj_name)
        if obj and obj.data and hasattr(obj.data, "polygons"):
            for poly in obj.data.polygons:
                poly.use_smooth = True

    rendered_files: list[Path] = []

    for shot in SHOTS:
        if only_shot_id and shot["id"] != only_shot_id:
            continue
        print(f"[render] Rendering {shot['description']} -> {shot['filename']} ...")
        configure_cycles(scene, samples=shot["samples"])
        setup_world_lighting(scene, shot["mode"], hdri_paths)

        cam_data = bpy.data.cameras.new(name=f"Cam_{shot['id']}")
        cam_data.type = "PERSP"
        cam_data.lens = shot["lens_mm"]
        cam_data.shift_y = shot["shift_y"]
        cam_obj = bpy.data.objects.new(name=f"Cam_{shot['id']}", object_data=cam_data)
        scene.collection.objects.link(cam_obj)
        cam_obj.location = shot["location"]
        look_at(cam_obj, shot["target"])
        scene.camera = cam_obj

        scene.render.resolution_x = shot["resolution"][0]
        scene.render.resolution_y = shot["resolution"][1]
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"

        out_path = out_dir / shot["filename"]
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        print(f"[render] Saved {out_path} ({out_path.stat().st_size // 1024} KB)")
        rendered_files.append(out_path)

    # Bonus: 360° Equirectangular Panorama (4096 x 2048) of Type A Drawing Room on Floor 1
    if render_bonus_panorama and (only_shot_id is None or only_shot_id == "panorama"):
        pano_file = out_dir / "bonus_type_a_panorama_360.png"
        print(f"[render] Rendering Bonus 360° Equirectangular Panorama (4096x2048) -> {pano_file.name} ...")
        configure_cycles(scene, samples=18)
        setup_world_lighting(scene, "interior", hdri_paths)

        cam_data = bpy.data.cameras.new(name="Cam_TypeA_Panorama_360")
        cam_data.type = "PANO"
        if hasattr(cam_data, "panorama_type"):
            cam_data.panorama_type = "EQUIRECTANGULAR"
        elif hasattr(cam_data, "cycles") and hasattr(cam_data.cycles, "panorama_type"):
            cam_data.cycles.panorama_type = "EQUIRECTANGULAR"

        cam_obj = bpy.data.objects.new(name="Cam_TypeA_Panorama_360", object_data=cam_data)
        scene.collection.objects.link(cam_obj)
        # Center of Floor 1 Type A Drawing Room (x=8.2m, y=13.6m, eye height z = 3.30 + 1.50 = 4.80m)
        cam_obj.location = (8.20, 13.60, 4.80)
        cam_obj.rotation_euler = (math.pi * 0.5, 0.0, 0.0)
        scene.camera = cam_obj

        scene.render.resolution_x = 4096
        scene.render.resolution_y = 2048
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(pano_file)
        bpy.ops.render.render(write_still=True)
        print(f"[render] Saved {pano_file} ({pano_file.stat().st_size // 1024} KB)")
        rendered_files.append(pano_file)

    # Save the .blend file with all configured cameras and lighting included
    bpy.ops.wm.save_as_mainfile(filepath=str(in_blend))
    return rendered_files


if __name__ == "__main__":
    render_all()
