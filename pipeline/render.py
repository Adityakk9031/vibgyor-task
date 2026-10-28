"""
Stage 3: Render all Level 1 & Level 2 photorealistic still images (>= 2560 px wide)
and all 16 equirectangular 360-degree panoramas (>= 6144 x 3072 px) using Blender Cycles.

Cameras and lighting are defined entirely in code:
  A. Exterior Stills (2560 x 1440, outputs/):
     1. shot_1_eye_level_day.png
     2. shot_2_front_corner_dusk.png
     3. shot_3_aerial_day.png
     4. shot_4_entrance_closeup.png

  B. Amenity Stills (5 stills @ 2560 x 1440, outputs/amenities/):
     1. amenity_1_basement_parking.png  - Basement parking bays, two-wheelers, columns & ramp
     2. amenity_2_stilt_parking.png     - Ground-level stilt parking bays, cars, columns & soffit lights
     3. amenity_3_entrance_lobby.png    - Ground-floor entrance lobby with lifts, travertine & fluted wood
     4. amenity_4_landscape_drive.png   - Garden planter beds, wooden deck benches, trees & entrance drive
     5. amenity_5_terrace_amenities.png - Terrace pergola lounge, kids' play area & glass fitness gym

  C. Interior Stills (8 stills @ 2560 x 1440, outputs/interiors/):
     Type A (Front 4BHK, 160.05 sq.m):
       1. type_a_1_drawing_room.png
       2. type_a_2_kitchen_dining.png
       3. type_a_3_master_bedroom.png
       4. type_a_4_second_bedroom.png
     Type B (Rear 4BHK, 143.18 sq.m):
       5. type_b_1_drawing_room.png
       6. type_b_2_kitchen_dining.png
       7. type_b_3_master_bedroom.png
       8. type_b_4_second_bedroom.png

  D. 360° Equirectangular Panoramas (16 panoramas @ 6144 x 3072, outputs/panoramas/):
     Building & Amenities (6 panoramas):
       1. pano_bldg_1_entrance_gate.png
       2. pano_bldg_2_entrance_lobby.png
       3. pano_bldg_3_basement_parking.png
       4. pano_bldg_4_garden_stilt.png
       5. pano_bldg_5_terrace_pergola_kids.png
       6. pano_bldg_6_terrace_gym.png
     Type A Interior (5 panoramas):
       7. pano_type_a_1_drawing_room.png
       8. pano_type_a_2_dining_kitchen.png
       9. pano_type_a_3_master_bedroom.png
       10. pano_type_a_4_second_bedroom.png
       11. pano_type_a_5_balcony_deck.png
     Type B Interior (5 panoramas):
       12. pano_type_b_1_drawing_room.png
       13. pano_type_b_2_dining_kitchen.png
       14. pano_type_b_3_master_bedroom.png
       15. pano_type_b_4_second_bedroom.png
       16. pano_type_b_5_balcony_deck.png
"""

from __future__ import annotations

import math
import shutil
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
    """Sets up HDRI sky + Sun light + balanced interior/amenity point lights."""
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

    hdri_key = "dusk" if mode == "dusk" else "day"
    hdri_file = hdri_paths.get(hdri_key) or hdri_paths.get("day")
    if hdri_file and hdri_file.exists():
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value = (
            0.0,
            0.0,
            math.radians(45.0 if mode != "dusk" else 160.0),
        )
        env_tex = nodes.new(type="ShaderNodeTexEnvironment")
        env_tex.image = bpy.data.images.load(str(hdri_file), check_existing=True)
        links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
        links.new(env_tex.outputs["Color"], bg_node.inputs["Color"])
        # Keep exterior HDRI moderate during interior renders so windows don't blow out!
        bg_strength = {
            "day": 1.15,
            "dusk": 0.35,
            "interior": 0.85,
            "basement": 0.45,
        }.get(mode, 1.0)
        bg_node.inputs["Strength"].default_value = bg_strength
    else:
        sky_tex = nodes.new(type="ShaderNodeTexSky")
        sky_tex.sky_type = "NISHITA"
        sky_tex.sun_elevation = math.radians(38.0 if mode != "dusk" else 3.0)
        sky_tex.sun_rotation = math.radians(135.0)
        links.new(sky_tex.outputs["Color"], bg_node.inputs["Color"])
        bg_node.inputs["Strength"].default_value = 1.0 if mode != "dusk" else 0.28

    # Remove old dynamic lights
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Light_Dynamic_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    # Add Sun lamp
    sun_data = bpy.data.lights.new(name="Light_Dynamic_Sun", type="SUN")
    sun_obj = bpy.data.objects.new(name="Light_Dynamic_Sun", object_data=sun_data)
    scene.collection.objects.link(sun_obj)
    if mode in ("day", "interior", "basement"):
        sun_data.energy = 3.6 if mode == "day" else 2.2
        sun_data.color = (1.0, 0.96, 0.90)
        sun_data.angle = math.radians(2.0)
        sun_obj.location = (25.0, -30.0, 40.0)
        look_at(sun_obj, (7.0, 15.0, 10.0))
    elif mode == "dusk":
        sun_data.energy = 0.48
        sun_data.color = (0.58, 0.70, 1.0)
        sun_data.angle = math.radians(5.0)
        sun_obj.location = (-25.0, -25.0, 18.0)
        look_at(sun_obj, (7.0, 15.0, 10.0))

    # Adjust emissive LED materials
    led_mat = bpy.data.materials.get("Mat_Warm_LED")
    cool_mat = bpy.data.materials.get("Mat_Cool_LED")
    sign_mat = bpy.data.materials.get("Mat_Sign_Glow")
    if led_mat and led_mat.use_nodes:
        bsdf = led_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 24.0 if mode in ("dusk", "interior") else 10.0
    if cool_mat and cool_mat.use_nodes:
        bsdf = cool_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 22.0
    if sign_mat and sign_mat.use_nodes:
        bsdf = sign_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 35.0 if mode == "dusk" else 14.0

    def add_point_light(name: str, loc: tuple[float, float, float], power: float, color=(1.0, 0.91, 0.78), radius=0.95):
        ldata = bpy.data.lights.new(name=name, type="POINT")
        ldata.energy = power
        ldata.color = color
        ldata.shadow_soft_size = radius
        lobj = bpy.data.objects.new(name=name, object_data=ldata)
        lobj.location = loc
        scene.collection.objects.link(lobj)

    if mode == "dusk":
        for fl in range(1, 8):
            zf = 3.30 + (fl - 1) * 3.05 + 2.35
            for idx, (lx, ly, power) in enumerate(
                [
                    (8.5, 4.5, 420.0),
                    (4.5, 6.2, 400.0),
                    (9.5, 14.0, 360.0),
                    (2.8, 16.5, 220.0),
                    (1.5, 27.5, 340.0),
                ]
            ):
                add_point_light(f"Light_Dynamic_Fl{fl}_{idx}", (lx, ly, zf), power, (1.0, 0.78, 0.48), 0.65)
        for idx, (lx, ly, lz, power) in enumerate(
            [
                (1.5, 0.5, 2.75, 650.0),
                (10.5, -6.2, 0.6, 380.0),
                (5.2, 16.0, 27.2, 320.0),
                (9.2, 16.0, 27.2, 320.0),
            ]
        ):
            add_point_light(f"Light_Dynamic_Ground_{idx}", (lx, ly, lz), power, (1.0, 0.80, 0.52), 0.80)

    elif mode == "interior":
        # Balanced warm interior lighting across all rooms in Floor 1 (Type A & Type B),
        # Ground Floor Entrance Lobby & Stilt Parking, and Terrace Gym & Pergola
        interior_lights = [
            # Floor 1 Type A (z_ceil = 6.20m, lights at z = 5.78m)
            (8.2, 13.3, 5.78, 280.0),   # Type A Drawing Room
            (5.5, 10.2, 5.78, 260.0),   # Type A Kitchen & Dining
            (2.8, 10.2, 5.78, 160.0),   # Type A Kitchen Counter fill
            (10.8, 3.8, 5.78, 240.0),   # Type A Master Bedroom (SE)
            (5.1, 6.3, 5.78, 220.0),    # Type A Second Bedroom (SW)
            (10.6, 10.2, 5.78, 210.0),  # Type A Third Bedroom (Mid-East)
            (9.5, 17.3, 5.78, 190.0),   # Type A Fourth Bedroom (NE)
            (12.2, 14.3, 5.78, 140.0),  # Type A East Balcony Deck
            (6.8, 17.2, 5.78, 150.0),   # Type A Vestibule
            # Floor 1 Type B (z_ceil = 6.20m, lights at z = 5.78m)
            (4.8, 28.1, 5.78, 280.0),   # Type B Drawing Room
            (6.8, 31.6, 5.78, 260.0),   # Type B Kitchen & Dining
            (9.2, 31.6, 5.78, 160.0),   # Type B Kitchen Counter fill
            (7.5, 36.8, 5.78, 240.0),   # Type B Master Bedroom (NE)
            (2.5, 35.0, 5.78, 220.0),   # Type B Second Bedroom (NW)
            (2.1, 31.6, 5.78, 210.0),   # Type B Third Bedroom (Mid-West)
            (3.8, 24.6, 5.78, 190.0),   # Type B Fourth Bedroom (SW)
            (0.9, 27.3, 5.78, 140.0),   # Type B West Balcony Deck
            # Ground Floor Lobby & Stilt (z_ceil = 3.15m, lights at z = 2.85m)
            (6.5, 21.0, 2.82, 280.0),   # Entrance Lobby center
            (5.2, 20.2, 2.82, 180.0),   # Lift foyer fill
            (6.0, 8.5, 2.85, 240.0),    # Stilt parking south
            (6.0, 14.5, 2.85, 220.0),   # Stilt parking mid
            (5.0, 28.0, 2.85, 240.0),   # Stilt parking north
            # Terrace Gym & Pergola (z_terrace = 24.70m, lights at z = 27.20m)
            (5.8, 30.5, 27.25, 280.0),  # Terrace Gym south
            (5.8, 34.0, 27.25, 280.0),  # Terrace Gym north
            (4.8, 16.0, 27.15, 220.0),  # Terrace Pergola west bay
            (9.8, 16.0, 27.15, 220.0),  # Terrace Pergola east bay
        ]
        for idx, (lx, ly, lz, power) in enumerate(interior_lights):
            add_point_light(f"Light_Dynamic_Int_{idx}", (lx, ly, lz), power, (1.0, 0.92, 0.80), 1.05)

    elif mode == "basement":
        # Bright, even industrial LED lighting across Basement Parking (z_bsm = -3.15m, ceiling = -0.15m)
        bsm_lights = [
            (3.5, 6.0, -0.45, 320.0),
            (9.5, 6.0, -0.45, 320.0),
            (3.5, 13.0, -0.45, 320.0),
            (9.5, 13.0, -0.45, 320.0),
            (6.5, 20.5, -0.45, 340.0),
            (3.5, 26.5, -0.45, 340.0),
            (9.5, 26.5, -0.45, 340.0),
            (2.5, 34.0, -0.45, 360.0),
            (6.8, 34.0, -0.45, 360.0),
            (-1.5, 34.0, -0.45, 300.0),
        ]
        for idx, (lx, ly, lz, power) in enumerate(bsm_lights):
            add_point_light(f"Light_Dynamic_Bsm_{idx}", (lx, ly, lz), power, (0.94, 0.97, 1.0), 1.15)


def configure_cycles(scene: bpy.types.Scene, samples: int = 4, exposure: float = 0.25) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.08
    if hasattr(scene.cycles, "use_denoising"):
        scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    scene.cycles.transparent_max_bounces = 4
    if hasattr(scene.cycles, "caustics_reflective"):
        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False

    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = exposure


# =============================================================================
# Shot Definitions: 4 Exterior + 5 Amenity + 8 Interior + 16 360° Panoramas
# =============================================================================

EXTERIOR_SHOTS = [
    {
        "id": "shot_1_eye_level_day",
        "filename": "shot_1_eye_level_day.png",
        "description": "Exterior 1: Eye level from the main road (Day)",
        "mode": "day",
        "location": (0.5, -25.5, 1.75),
        "target": (6.2, 4.0, 11.2),
        "lens_mm": 18.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 10,
    },
    {
        "id": "shot_2_front_corner_dusk",
        "filename": "shot_2_front_corner_dusk.png",
        "description": "Exterior 2: Front corner (Dusk) - interior and facade lights on",
        "mode": "dusk",
        "location": (-13.5, -21.0, 2.20),
        "target": (6.0, 7.5, 11.0),
        "lens_mm": 19.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 10,
    },
    {
        "id": "shot_3_aerial_day",
        "filename": "shot_3_aerial_day.png",
        "description": "Exterior 3: Aerial 45 degrees (Day) - building on plot",
        "mode": "day",
        "location": (-23.0, -27.0, 35.0),
        "target": (6.5, 14.0, 9.5),
        "lens_mm": 26.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 10,
    },
    {
        "id": "shot_4_entrance_closeup",
        "filename": "shot_4_entrance_closeup.png",
        "description": "Exterior 4: Close-up of entrance canopy & VIBGYOR signage (Day)",
        "mode": "day",
        "location": (3.0, -12.5, 1.65),
        "target": (4.8, -0.5, 2.15),
        "lens_mm": 28.0,
        "shift_y": 0.02,
        "resolution": (2560, 1440),
        "samples": 10,
    },
]

AMENITY_SHOTS = [
    {
        "id": "amenity_1_basement_parking",
        "filename": "amenities/amenity_1_basement_parking.png",
        "description": "Amenity 1: Basement parking (car bays, two-wheelers, ramp, columns & ceiling LEDs)",
        "mode": "basement",
        "location": (4.80, 26.50, -1.65),
        "target": (4.20, 35.50, -1.75),
        "lens_mm": 18.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 8,
    },
    {
        "id": "amenity_2_stilt_parking",
        "filename": "amenities/amenity_2_stilt_parking.png",
        "description": "Amenity 2: Ground-level stilt parking (bays, cars, columns & lighting)",
        "mode": "interior",
        "location": (5.80, 23.80, 1.55),
        "target": (3.50, 30.80, 1.35),
        "lens_mm": 18.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 8,
    },
    {
        "id": "amenity_3_entrance_lobby",
        "filename": "amenities/amenity_3_entrance_lobby.png",
        "description": "Amenity 3: Ground-floor entrance lobby (lifts, travertine, fluted wood, seating & chandelier)",
        "mode": "interior",
        "location": (8.55, 20.65, 1.50),
        "target": (4.50, 21.10, 1.55),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 10,
    },
    {
        "id": "amenity_4_landscape_drive",
        "filename": "amenities/amenity_4_landscape_drive.png",
        "description": "Amenity 4: Landscape garden beds, wooden deck benches, trees & entrance drive",
        "mode": "day",
        "location": (-1.45, 5.20, 1.55),
        "target": (-1.75, 16.50, 1.45),
        "lens_mm": 19.0,
        "shift_y": 0.01,
        "resolution": (2560, 1440),
        "samples": 8,
    },
    {
        "id": "amenity_5_terrace_amenities",
        "filename": "amenities/amenity_5_terrace_amenities.png",
        "description": "Amenity 5: Terrace pergola seating, kids' play area & fitness gym",
        "mode": "day",
        "location": (11.60, 17.80, 26.35),
        "target": (5.50, 8.50, 25.85),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 8,
    },
]

INTERIOR_SHOTS = [
    # --- TYPE A (Front 4BHK, Floor 1: z_floor = 3.30m, eye height z = 4.72m) ---
    {
        "id": "type_a_1_drawing_room",
        "filename": "interiors/type_a_1_drawing_room.png",
        "description": "Type A Interior 1: Drawing Room (L-sofa, coffee tables, fluted wall & balcony light)",
        "mode": "interior",
        "location": (5.35, 12.15, 4.72),
        "target": (9.45, 14.35, 4.68),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    {
        "id": "type_a_2_kitchen_dining",
        "filename": "interiors/type_a_2_kitchen_dining.png",
        "description": "Type A Interior 2: Kitchen & 6-Seater Dining Area",
        "mode": "interior",
        "location": (7.45, 10.85, 4.65),
        "target": (3.20, 9.85, 4.45),
        "lens_mm": 24.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 8,
    },
    {
        "id": "type_a_3_master_bedroom",
        "filename": "interiors/type_a_3_master_bedroom.png",
        "description": "Type A Interior 3: Master Bedroom (3.96 x 5.02 m, South-East front)",
        "mode": "interior",
        "location": (9.65, 5.20, 4.72),
        "target": (11.85, 3.35, 4.52),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    {
        "id": "type_a_4_second_bedroom",
        "filename": "interiors/type_a_4_second_bedroom.png",
        "description": "Type A Interior 4: Second Bedroom (4.56 x 3.20 m, Middle-East)",
        "mode": "interior",
        "location": (9.45, 9.05, 4.72),
        "target": (11.35, 10.95, 4.55),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    # --- TYPE B (Rear 4BHK, Floor 1: z_floor = 3.30m, eye height z = 4.72m) ---
    {
        "id": "type_b_1_drawing_room",
        "filename": "interiors/type_b_1_drawing_room.png",
        "description": "Type B Interior 1: Drawing Room (6.31 x 3.65 m, opening to West balcony)",
        "mode": "interior",
        "location": (7.55, 29.35, 4.72),
        "target": (3.25, 27.25, 4.65),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    {
        "id": "type_b_2_kitchen_dining",
        "filename": "interiors/type_b_2_kitchen_dining.png",
        "description": "Type B Interior 2: Kitchen & Dining Area (6.11 x 3.20 m)",
        "mode": "interior",
        "location": (4.55, 30.55, 4.72),
        "target": (8.85, 32.10, 4.62),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    {
        "id": "type_b_3_master_bedroom",
        "filename": "interiors/type_b_3_master_bedroom.png",
        "description": "Type B Interior 3: Master Bedroom (5.34 x 3.65 m, North-East)",
        "mode": "interior",
        "location": (5.40, 35.40, 4.72),
        "target": (8.25, 37.55, 4.58),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
    {
        "id": "type_b_4_second_bedroom",
        "filename": "interiors/type_b_4_second_bedroom.png",
        "description": "Type B Interior 4: Second Bedroom (4.73 x 3.35 m, North-West)",
        "mode": "interior",
        "location": (3.75, 33.85, 4.72),
        "target": (2.15, 35.85, 4.55),
        "lens_mm": 17.0,
        "shift_y": 0.0,
        "resolution": (2560, 1440),
        "samples": 5,
    },
]

# 16 Equirectangular 360° Panoramas (6144 x 3072 px, eye height 1.50m above floor, level horizon)
PANORAMA_SHOTS = [
    # --- Building & Amenities (6 panoramas) ---
    {
        "id": "pano_bldg_1_entrance_gate",
        "filename": "panoramas/pano_bldg_1_entrance_gate.png",
        "title": "1 · Entrance Gate & Canopy Drive",
        "category": "Building & Amenities",
        "mode": "day",
        "location": (1.20, -2.50, 1.50),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_bldg_2_entrance_lobby",
        "filename": "panoramas/pano_bldg_2_entrance_lobby.png",
        "title": "2 · Ground Floor Entrance Lobby & Lifts",
        "category": "Building & Amenities",
        "mode": "interior",
        "location": (6.60, 21.10, 1.56),
        "yaw_deg": 90.0,
    },
    {
        "id": "pano_bldg_3_basement_parking",
        "filename": "panoramas/pano_bldg_3_basement_parking.png",
        "title": "3 · Basement Parking & Curved Ramp",
        "category": "Building & Amenities",
        "mode": "basement",
        "location": (6.20, 26.80, -1.65),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_bldg_4_garden_stilt",
        "filename": "panoramas/pano_bldg_4_garden_stilt.png",
        "title": "4 · Landscape Garden Deck & Stilt Parking",
        "category": "Building & Amenities",
        "mode": "day",
        "location": (5.20, 13.50, 1.55),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_bldg_5_terrace_pergola_kids",
        "filename": "panoramas/pano_bldg_5_terrace_pergola_kids.png",
        "title": "5 · Terrace Pergola Lounge & Kids' Play Area",
        "category": "Building & Amenities",
        "mode": "day",
        "location": (7.35, 11.80, 26.28),
        "yaw_deg": 180.0,
    },
    {
        "id": "pano_bldg_6_terrace_gym",
        "filename": "panoramas/pano_bldg_6_terrace_gym.png",
        "title": "6 · Terrace Fitness Gym & Yoga Deck",
        "category": "Building & Amenities",
        "mode": "interior",
        "location": (5.80, 30.80, 26.28),
        "yaw_deg": 0.0,
    },
    # --- Type A Interior (5 panoramas on Floor 1, z_floor = 3.30m, eye height z = 4.80m) ---
    {
        "id": "pano_type_a_1_drawing_room",
        "filename": "panoramas/pano_type_a_1_drawing_room.png",
        "title": "7 · Type A — Drawing Room",
        "category": "Type A (Front 4BHK)",
        "mode": "interior",
        "location": (8.10, 13.25, 4.80),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_type_a_2_dining_kitchen",
        "filename": "panoramas/pano_type_a_2_dining_kitchen.png",
        "title": "8 · Type A — Kitchen & Dining",
        "category": "Type A (Front 4BHK)",
        "mode": "interior",
        "location": (5.85, 10.15, 4.80),
        "yaw_deg": 90.0,
    },
    {
        "id": "pano_type_a_3_master_bedroom",
        "filename": "panoramas/pano_type_a_3_master_bedroom.png",
        "title": "9 · Type A — Master Bedroom (SE)",
        "category": "Type A (Front 4BHK)",
        "mode": "interior",
        "location": (10.55, 3.85, 4.80),
        "yaw_deg": -90.0,
    },
    {
        "id": "pano_type_a_4_second_bedroom",
        "filename": "panoramas/pano_type_a_4_second_bedroom.png",
        "title": "10 · Type A — Second Bedroom (Mid-East)",
        "category": "Type A (Front 4BHK)",
        "mode": "interior",
        "location": (10.45, 9.85, 4.80),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_type_a_5_balcony_deck",
        "filename": "panoramas/pano_type_a_5_balcony_deck.png",
        "title": "11 · Type A — Third Bedroom (SW) & Balcony View",
        "category": "Type A (Front 4BHK)",
        "mode": "interior",
        "location": (4.85, 6.35, 4.80),
        "yaw_deg": -90.0,
    },
    # --- Type B Interior (5 panoramas on Floor 1, z_floor = 3.30m, eye height z = 4.80m) ---
    {
        "id": "pano_type_b_1_drawing_room",
        "filename": "panoramas/pano_type_b_1_drawing_room.png",
        "title": "12 · Type B — Drawing Room",
        "category": "Type B (Rear 4BHK)",
        "mode": "interior",
        "location": (4.85, 28.15, 4.80),
        "yaw_deg": 180.0,
    },
    {
        "id": "pano_type_b_2_dining_kitchen",
        "filename": "panoramas/pano_type_b_2_dining_kitchen.png",
        "title": "13 · Type B — Kitchen & Dining",
        "category": "Type B (Rear 4BHK)",
        "mode": "interior",
        "location": (6.65, 31.55, 4.80),
        "yaw_deg": -90.0,
    },
    {
        "id": "pano_type_b_3_master_bedroom",
        "filename": "panoramas/pano_type_b_3_master_bedroom.png",
        "title": "14 · Type B — Master Bedroom (NE)",
        "category": "Type B (Rear 4BHK)",
        "mode": "interior",
        "location": (7.45, 36.25, 4.80),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_type_b_4_second_bedroom",
        "filename": "panoramas/pano_type_b_4_second_bedroom.png",
        "title": "15 · Type B — Second Bedroom (NW)",
        "category": "Type B (Rear 4BHK)",
        "mode": "interior",
        "location": (2.65, 34.65, 4.80),
        "yaw_deg": 0.0,
    },
    {
        "id": "pano_type_b_5_balcony_deck",
        "filename": "panoramas/pano_type_b_5_balcony_deck.png",
        "title": "16 · Type B — Third Bedroom (Mid-West)",
        "category": "Type B (Rear 4BHK)",
        "mode": "interior",
        "location": (2.35, 31.65, 4.80),
        "yaw_deg": 90.0,
    },
]

SHOTS = EXTERIOR_SHOTS + AMENITY_SHOTS + INTERIOR_SHOTS


def render_all(
    blend_path: str | Path = "outputs/vibgyor.blend",
    output_dir: str | Path = "outputs",
    render_bonus_panorama: bool = True,
    only_shot_id: str | None = None,
    pano_resolution: tuple[int, int] = (6144, 3072),
    copy_panos_to_viewer: bool = True,
) -> list[Path]:
    base_dir = Path(blend_path).resolve().parent.parent
    in_blend = base_dir / blend_path
    out_dir = base_dir / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "amenities").mkdir(parents=True, exist_ok=True)
    (out_dir / "interiors").mkdir(parents=True, exist_ok=True)
    (out_dir / "panoramas").mkdir(parents=True, exist_ok=True)

    hdri_paths = ensure_assets(base_dir / "assets")
    bpy.ops.wm.open_mainfile(filepath=str(in_blend))
    scene = bpy.context.scene

    for obj_name in ("Landscape_Tree_Canopies", "Landscape_Tree_Trunks"):
        obj = bpy.data.objects.get(obj_name)
        if obj and obj.data and hasattr(obj.data, "polygons"):
            for poly in obj.data.polygons:
                poly.use_smooth = True

    rendered_files: list[Path] = []
    current_mode: str | None = None

    # 1. Render Still Shots (4 Exterior + 5 Amenity + 8 Interior = 17 Stills @ 2560x1440)
    viewer_dir = base_dir / "viewer"
    (viewer_dir / "amenities").mkdir(parents=True, exist_ok=True)
    (viewer_dir / "interiors").mkdir(parents=True, exist_ok=True)
    (viewer_dir / "exteriors").mkdir(parents=True, exist_ok=True)

    for shot in SHOTS:
        if only_shot_id:
            if only_shot_id == "stills":
                pass
            elif only_shot_id == "amenities" and not shot["filename"].startswith("amenities/"):
                continue
            elif only_shot_id == "interiors" and not shot["filename"].startswith("interiors/"):
                continue
            elif only_shot_id == "exteriors" and ("/" in shot["filename"]):
                continue
            elif only_shot_id not in ("stills", "amenities", "interiors", "exteriors") and shot["id"] != only_shot_id:
                continue
        print(f"[render] Rendering {shot['description']} -> {shot['filename']} ...")
        configure_cycles(scene, samples=shot["samples"], exposure=0.18 if shot["mode"] in ("interior", "basement") else 0.15)
        if current_mode != shot["mode"]:
            setup_world_lighting(scene, shot["mode"], hdri_paths)
            current_mode = shot["mode"]

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
        out_path.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        print(f"[render] Saved {out_path} ({out_path.stat().st_size // 1024} KB)")
        rendered_files.append(out_path)
        if copy_panos_to_viewer:
            if "/" in shot["filename"]:
                shutil.copy2(out_path, viewer_dir / shot["filename"])
            else:
                shutil.copy2(out_path, viewer_dir / "exteriors" / shot["filename"])

    # 2. Render 16 Equirectangular 360° Panoramas (6144 x 3072 px)
    if render_bonus_panorama:
        viewer_pano_dir = base_dir / "viewer" / "panoramas"
        if copy_panos_to_viewer:
            viewer_pano_dir.mkdir(parents=True, exist_ok=True)

        for pano in PANORAMA_SHOTS:
            if only_shot_id and pano["id"] != only_shot_id and only_shot_id != "panoramas":
                continue
            out_path = out_dir / pano["filename"]
            if only_shot_id == "panoramas" and out_path.exists() and out_path.stat().st_size > 500_000:
                print(f"[render] Skipping already-rendered 360° Panorama: {pano['filename']} ({out_path.stat().st_size // 1024} KB)")
                rendered_files.append(out_path)
                if copy_panos_to_viewer:
                    shutil.copy2(out_path, viewer_pano_dir / out_path.name)
                if pano["id"] == "pano_type_a_1_drawing_room":
                    shutil.copy2(out_path, out_dir / "bonus_type_a_panorama_360.png")
                continue
            print(f"[render] Rendering 360° Panorama ({pano_resolution[0]}x{pano_resolution[1]}): {pano['title']} -> {pano['filename']} ...")
            configure_cycles(scene, samples=2, exposure=0.22 if pano["mode"] in ("interior", "basement") else 0.16)
            scene.cycles.max_bounces = 1
            scene.cycles.diffuse_bounces = 1
            scene.cycles.glossy_bounces = 1
            scene.cycles.transmission_bounces = 1
            scene.cycles.transparent_max_bounces = 2
            if current_mode != pano["mode"]:
                setup_world_lighting(scene, pano["mode"], hdri_paths)
                current_mode = pano["mode"]

            cam_data = bpy.data.cameras.new(name=f"Cam_{pano['id']}")
            cam_data.type = "PANO"
            if hasattr(cam_data, "panorama_type"):
                cam_data.panorama_type = "EQUIRECTANGULAR"
            elif hasattr(cam_data, "cycles") and hasattr(cam_data.cycles, "panorama_type"):
                cam_data.cycles.panorama_type = "EQUIRECTANGULAR"

            cam_obj = bpy.data.objects.new(name=f"Cam_{pano['id']}", object_data=cam_data)
            scene.collection.objects.link(cam_obj)
            cam_obj.location = pano["location"]
            # Perfectly level horizon: X rotation = 90 deg (pi/2), Y = 0, Z = yaw
            cam_obj.rotation_euler = (math.pi * 0.5, 0.0, math.radians(pano.get("yaw_deg", 0.0)))
            scene.camera = cam_obj

            scene.render.resolution_x = pano_resolution[0]
            scene.render.resolution_y = pano_resolution[1]
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = "PNG"
            scene.render.filepath = str(out_path)
            bpy.ops.render.render(write_still=True)
            print(f"[render] Saved {out_path} ({out_path.stat().st_size // 1024} KB)")
            rendered_files.append(out_path)

            if copy_panos_to_viewer:
                shutil.copy2(out_path, viewer_pano_dir / out_path.name)

            # Also keep backwards-compatible bonus_type_a_panorama_360.png from Level 1
            if pano["id"] == "pano_type_a_1_drawing_room":
                shutil.copy2(out_path, out_dir / "bonus_type_a_panorama_360.png")

    bpy.ops.wm.save_as_mainfile(filepath=str(in_blend))
    return rendered_files


if __name__ == "__main__":
    render_all()
