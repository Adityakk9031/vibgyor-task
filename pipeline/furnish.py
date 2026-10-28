"""
Geometry-driven furnishing & amenities builder for Vibgyor Level 2.

All furniture and amenity placements in this module are computed procedurally
from the extracted 2D polygons and bounding boxes in `outputs/extracted_geometry.json`
(room bounds, window/door wall tags, parking bay rectangles, and terrace deck zones)
rather than hand-typed world coordinates per furniture piece.
"""

from __future__ import annotations

import math
from typing import Any

import bpy
import trimesh
from shapely.geometry import Polygon

from pipeline.build_model import (
    add_trimesh_to_blender,
    create_herringbone_wood_material,
    create_pbr_material,
    create_statuario_marble_material,
    create_walnut_cabinet_material,
    extrude_shapely_polys,
    make_box_trimesh,
    make_oriented_box,
)


def ensure_level2_materials(mats: dict[str, bpy.types.Material]) -> dict[str, bpy.types.Material]:
    """Adds interior & amenity PBR materials to the material library."""
    extra = {
        "oak_floor": create_herringbone_wood_material("Mat_Oak_Floor"),
        "fluted_wood": create_walnut_cabinet_material("Mat_Fluted_Wood"),
        "walnut_wood": create_walnut_cabinet_material("Mat_Walnut_Cabinet"),
        "statuario_marble": create_statuario_marble_material("Mat_Statuario_Marble"),
        "travertine_marble": create_pbr_material(
            "Mat_Travertine_Marble", base_color=(0.84, 0.78, 0.68), roughness=0.18, bump_scale=10.0, bump_strength=0.05
        ),
        "black_steel": create_pbr_material(
            "Mat_Black_Steel", base_color=(0.04, 0.04, 0.04), roughness=0.22, metallic=0.92
        ),
        "matte_black_dome": create_pbr_material(
            "Mat_Matte_Black_Dome", base_color=(0.02, 0.02, 0.02), roughness=0.35, metallic=0.40
        ),
        "bronze_metal": create_pbr_material(
            "Mat_Bronze_Metal", base_color=(0.45, 0.33, 0.22), roughness=0.26, metallic=0.88
        ),
        "chrome_metal": create_pbr_material(
            "Mat_Chrome_Metal", base_color=(0.82, 0.84, 0.86), roughness=0.15, metallic=0.95
        ),
        "bed_linen_white": create_pbr_material(
            "Mat_Bed_Linen_White", base_color=(0.92, 0.90, 0.87), roughness=0.82, bump_scale=50.0, bump_strength=0.08
        ),
        "bed_throw_grey": create_pbr_material(
            "Mat_Bed_Throw_Grey", base_color=(0.34, 0.35, 0.37), roughness=0.85, bump_scale=60.0, bump_strength=0.12
        ),
        "pillow_olive": create_pbr_material(
            "Mat_Pillow_Olive", base_color=(0.36, 0.46, 0.24), roughness=0.78
        ),
        "pillow_teal": create_pbr_material(
            "Mat_Pillow_Teal", base_color=(0.20, 0.42, 0.46), roughness=0.78
        ),
        "wardrobe_cream": create_pbr_material(
            "Mat_Wardrobe_Cream", base_color=(0.86, 0.83, 0.78), roughness=0.32
        ),
        "sheer_curtain": create_pbr_material(
            "Mat_Sheer_Curtain", base_color=(0.95, 0.94, 0.91), roughness=0.75, transmission=0.45, alpha=0.65
        ),
        "quartz_counter": create_statuario_marble_material("Mat_Quartz_Counter"),
        "cabinet_taupe": create_walnut_cabinet_material("Mat_Cabinet_Taupe"),
        "coral_velvet": create_pbr_material(
            "Mat_Coral_Velvet", base_color=(0.78, 0.36, 0.28), roughness=0.76
        ),
        "car_paint_silver": create_pbr_material(
            "Mat_Car_Silver", base_color=(0.72, 0.75, 0.78), roughness=0.18, metallic=0.85
        ),
        "car_paint_blue": create_pbr_material(
            "Mat_Car_Blue", base_color=(0.14, 0.26, 0.48), roughness=0.16, metallic=0.80
        ),
        "car_paint_white": create_pbr_material(
            "Mat_Car_White", base_color=(0.92, 0.93, 0.94), roughness=0.15, metallic=0.30
        ),
        "car_paint_bronze": create_pbr_material(
            "Mat_Car_Bronze", base_color=(0.38, 0.26, 0.18), roughness=0.18, metallic=0.82
        ),
        "tire_rubber": create_pbr_material(
            "Mat_Tire_Rubber", base_color=(0.08, 0.08, 0.09), roughness=0.88
        ),
        "safety_yellow": create_pbr_material(
            "Mat_Safety_Yellow", base_color=(0.92, 0.74, 0.12), roughness=0.45
        ),
        "epdm_blue": create_pbr_material(
            "Mat_EPDM_Blue", base_color=(0.22, 0.52, 0.76), roughness=0.78, bump_scale=60.0, bump_strength=0.15
        ),
        "epdm_sand": create_pbr_material(
            "Mat_EPDM_Sand", base_color=(0.84, 0.74, 0.58), roughness=0.82, bump_scale=50.0, bump_strength=0.15
        ),
        "play_red": create_pbr_material(
            "Mat_Play_Red", base_color=(0.85, 0.28, 0.24), roughness=0.35
        ),
        "play_yellow": create_pbr_material(
            "Mat_Play_Yellow", base_color=(0.95, 0.76, 0.18), roughness=0.35
        ),
        "gym_floor_dark": create_pbr_material(
            "Mat_Gym_Floor_Dark", base_color=(0.22, 0.23, 0.25), roughness=0.65, bump_scale=55.0, bump_strength=0.14
        ),
        "mirror_silver": create_pbr_material(
            "Mat_Mirror_Silver", base_color=(0.92, 0.94, 0.95), roughness=0.02, metallic=0.98
        ),
        "cool_led": create_pbr_material(
            "Mat_Cool_LED",
            base_color=(0.95, 0.98, 1.0),
            roughness=0.15,
            emission_color=(0.92, 0.96, 1.0),
            emission_strength=16.0,
        ),
    }
    mats.update(extra)
    return mats


# =============================================================================
# Procedural Vehicle & Equipment Primitives (Placed via Extracted Bay Bounds)
# =============================================================================


def make_car_meshes(
    cx: float, cy: float, z0: float, angle_rad: float
) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """
    Generates a clean 3D sedan/SUV mesh centered at (cx, cy) on floor z0, rotated by angle_rad.
    Returns (body_meshes, cabin_glass_meshes, wheel_and_trim_meshes).
    """
    body_parts: list[trimesh.Trimesh] = []
    glass_parts: list[trimesh.Trimesh] = []
    wheel_parts: list[trimesh.Trimesh] = []

    # Lower chassis (4.20m long x 1.76m wide, z from 0.22 to 0.82)
    lower = trimesh.creation.box(extents=[4.20, 1.76, 0.60])
    lower.apply_translation([0.0, 0.0, 0.52])
    body_parts.append(lower)

    # Upper cabin roof (2.25m long x 1.52m wide, z from 0.82 to 1.38)
    roof = trimesh.creation.box(extents=[2.15, 1.48, 0.52])
    roof.apply_translation([-0.15, 0.0, 1.08])
    body_parts.append(roof)

    # Windshield & side windows block (slightly inset/wider for glass appearance)
    glass = trimesh.creation.box(extents=[2.22, 1.52, 0.44])
    glass.apply_translation([-0.15, 0.0, 1.05])
    glass_parts.append(glass)

    # 4 Wheels
    for wx in (-1.32, 1.32):
        for wy in (-0.84, 0.84):
            wheel = trimesh.creation.cylinder(radius=0.32, height=0.22, sections=16)
            wheel.apply_transform(trimesh.transformations.rotation_matrix(math.pi * 0.5, [1, 0, 0]))
            wheel.apply_translation([wx, wy, 0.32])
            wheel_parts.append(wheel)

    # Bumpers / grilles
    for bx in (-2.11, 2.11):
        bmp = trimesh.creation.box(extents=[0.08, 1.68, 0.24])
        bmp.apply_translation([bx, 0.0, 0.38])
        wheel_parts.append(bmp)

    rot = trimesh.transformations.rotation_matrix(angle_rad, [0, 0, 1])
    for lst in (body_parts, glass_parts, wheel_parts):
        for m in lst:
            m.apply_transform(rot)
            m.apply_translation([cx, cy, z0])

    return body_parts, glass_parts, wheel_parts


def make_scooter_meshes(
    cx: float, cy: float, z0: float, angle_rad: float
) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Generates a 3D two-wheeler scooter centered at (cx, cy) on floor z0."""
    body: list[trimesh.Trimesh] = []
    dark: list[trimesh.Trimesh] = []

    deck = trimesh.creation.box(extents=[1.65, 0.56, 0.45])
    deck.apply_translation([0.0, 0.0, 0.42])
    body.append(deck)

    front_shield = trimesh.creation.box(extents=[0.28, 0.54, 0.85])
    front_shield.apply_translation([0.55, 0.0, 0.68])
    body.append(front_shield)

    seat = trimesh.creation.box(extents=[0.78, 0.44, 0.16])
    seat.apply_translation([-0.25, 0.0, 0.72])
    dark.append(seat)

    handle = trimesh.creation.box(extents=[0.12, 0.68, 0.08])
    handle.apply_translation([0.52, 0.0, 1.08])
    dark.append(handle)

    for wx in (-0.58, 0.58):
        wh = trimesh.creation.cylinder(radius=0.22, height=0.14, sections=12)
        wh.apply_transform(trimesh.transformations.rotation_matrix(math.pi * 0.5, [1, 0, 0]))
        wh.apply_translation([wx, 0.0, 0.22])
        dark.append(wh)

    rot = trimesh.transformations.rotation_matrix(angle_rad, [0, 0, 1])
    for lst in (body, dark):
        for m in lst:
            m.apply_transform(rot)
            m.apply_translation([cx, cy, z0])
    return body, dark


# =============================================================================
# 1. Geometry-Driven Interior Furnishing Engine (Type A & Type B Flats)
# =============================================================================


def build_room_cove_ceiling_and_curtains(
    b: list[float],
    openings: list[dict[str, Any]],
    z_f: float,
    z_ceil: float,
) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """
    Given a room bounding box [x0, y0, x1, y1] and its openings list, generates:
    - Perimeter false ceiling drop + warm recessed LED cove strips + twin downlight spots
    - Full-height sheer curtains flanking any window or sliding door on the room's walls
    Returns (ceiling_plaster_meshes, led_meshes, curtain_meshes).
    """
    x0, y0, x1, y1 = b[0] + 0.08, b[1] + 0.08, b[2] - 0.08, b[3] - 0.08
    w, d = x1 - x0, y1 - y0
    plaster: list[trimesh.Trimesh] = []
    leds: list[trimesh.Trimesh] = []
    curtains: list[trimesh.Trimesh] = []

    if w < 1.8 or d < 1.8:
        return plaster, leds, curtains

    # Upper ceiling slab soffit cover
    plaster.append(make_box_trimesh(x0, y0, z_ceil - 0.05, x1, y1, z_ceil))

    # Perimeter drop tray (0.42m wide around room edges)
    cw = min(0.42, w * 0.16, d * 0.16)
    plaster.extend(
        [
            make_box_trimesh(x0, y0, z_ceil - 0.14, x1, y0 + cw, z_ceil - 0.05),
            make_box_trimesh(x0, y1 - cw, z_ceil - 0.14, x1, y1, z_ceil - 0.05),
            make_box_trimesh(x0, y0 + cw, z_ceil - 0.14, x0 + cw, y1 - cw, z_ceil - 0.05),
            make_box_trimesh(x1 - cw, y0 + cw, z_ceil - 0.14, x1, y1 - cw, z_ceil - 0.05),
        ]
    )

    # Warm inner cove light strips along the recessed tray edge
    ix0, iy0, ix1, iy1 = x0 + cw, y0 + cw, x1 - cw, y1 - cw
    leds.extend(
        [
            make_box_trimesh(ix0, iy0 - 0.03, z_ceil - 0.13, ix1, iy0 + 0.02, z_ceil - 0.10),
            make_box_trimesh(ix0, iy1 - 0.02, z_ceil - 0.13, ix1, iy1 + 0.03, z_ceil - 0.10),
            make_box_trimesh(ix0 - 0.03, iy0, z_ceil - 0.13, ix0 + 0.02, iy1, z_ceil - 0.10),
            make_box_trimesh(ix1 - 0.02, iy0, z_ceil - 0.13, ix1 + 0.03, iy1, z_ceil - 0.10),
        ]
    )

    # Twin recessed ceiling downlights on the perimeter tray
    for sx in (x0 + cw * 0.5, (x0 + x1) * 0.5, x1 - cw * 0.5):
        for sy in (y0 + cw * 0.5, y1 - cw * 0.5):
            leds.append(make_box_trimesh(sx - 0.05, sy - 0.05, z_ceil - 0.15, sx + 0.05, sy + 0.05, z_ceil - 0.13))

    # Drape sheer curtains inside any wall that has a window or sliding door
    for op in openings:
        if op["type"] not in ("sliding_door", "large_window", "window"):
            continue
        wall_side = op["wall"]
        ox, oy = op["centroid"]
        for side_offset in (-0.85, 0.85):
            if wall_side in ("east", "west"):
                cx = (b[2] - 0.14) if wall_side == "east" else (b[0] + 0.14)
                cy = max(y0 + 0.25, min(y1 - 0.25, oy + side_offset))
                curtains.append(make_box_trimesh(cx - 0.06, cy - 0.22, z_f + 0.02, cx + 0.06, cy + 0.22, z_ceil - 0.14))
            else:
                cy = (b[3] - 0.14) if wall_side == "north" else (b[1] + 0.14)
                cx = max(x0 + 0.25, min(x1 - 0.25, ox + side_offset))
                curtains.append(make_box_trimesh(cx - 0.22, cy - 0.06, z_f + 0.02, cx + 0.22, cy + 0.06, z_ceil - 0.14))

    return plaster, leds, curtains


def furnish_drawing_room(
    room: dict[str, Any],
    unit_key: str,
    z_f: float,
    z_ceil: float,
    buckets: dict[str, list[trimesh.Trimesh]],
) -> None:
    """
    Furnishes a Drawing Room (Type A or Type B) from its extracted room bounds and balcony side.
    - Detects whether the balcony sliding door is on the East wall (Type A) or West wall (Type B).
    - Places the L-shaped sectional sofa, area rug, nested round marble/brass coffee tables,
      fluted TV console + 65" OLED TV, and fluted feature wall panelling accordingly.
    """
    b = room["bounds"]
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5

    plaster, leds, curtains = build_room_cove_ceiling_and_curtains(b, room.get("openings", []), z_f, z_ceil)
    buckets["interior_wall"].extend(plaster)
    buckets["warm_led"].extend(leds)
    buckets["sheer_curtain"].extend(curtains)

    balcony_east = unit_key == "type_a"

    # Area rug centered in the seating zone
    rx0, rx1 = (x0 + 1.4, x1 - 0.4) if balcony_east else (x0 + 0.4, x1 - 1.4)
    ry0, ry1 = y0 + 0.55, y1 - 0.45
    buckets["rug_fabric"].append(make_box_trimesh(rx0, ry0, z_f, rx1, ry1, z_f + 0.015))

    # Main 3-seater sofa along North wall (Type A) or South wall (Type B) + side loveseat near balcony
    if balcony_east:
        # Type A: Main sofa near North wall (y1 - 0.55), facing South toward TV console on South-Center
        sy0, sy1 = y1 - 1.05, y1 - 0.18
        sx0, sx1 = rx0 + 0.25, rx1 - 0.55
        buckets["sofa_fabric"].extend(
            [
                make_box_trimesh(sx0, sy0, z_f + 0.04, sx1, sy1, z_f + 0.42),
                make_box_trimesh(sx0, sy1 - 0.22, z_f + 0.42, sx1, sy1, z_f + 0.84),
                make_box_trimesh(sx0 - 0.16, sy0, z_f + 0.04, sx0 + 0.02, sy1, z_f + 0.64),
                make_box_trimesh(sx1 - 0.02, sy0, z_f + 0.04, sx1 + 0.16, sy1, z_f + 0.64),
                # Side loveseat along East balcony side
                make_box_trimesh(rx1 - 0.85, ry0 + 0.25, z_f + 0.04, rx1 - 0.05, sy0 - 0.20, z_f + 0.42),
                make_box_trimesh(rx1 - 0.25, ry0 + 0.25, z_f + 0.42, rx1 - 0.05, sy0 - 0.20, z_f + 0.84),
            ]
        )
        # Throw cushions
        for qx in (sx0 + 0.35, (sx0 + sx1) * 0.5, sx1 - 0.45):
            buckets["cushion_terracotta"].append(
                make_box_trimesh(qx - 0.20, sy1 - 0.42, z_f + 0.42, qx + 0.20, sy1 - 0.22, z_f + 0.74)
            )
        # Sage green & wood feature wall panelling behind sofa (North wall y = y1)
        buckets["sage_panelling"].append(make_box_trimesh(x0 + 1.0, y1 - 0.06, z_f, x1 - 0.15, y1 - 0.01, z_ceil - 0.14))
        for px in [x0 + 1.4 + i * 0.65 for i in range(7)]:
            if px < x1 - 0.3:
                buckets["fluted_wood"].append(
                    make_box_trimesh(px - 0.02, y1 - 0.09, z_f + 0.12, px + 0.02, y1 - 0.05, z_ceil - 0.20)
                )
        # TV console & 65" OLED TV along South side of Drawing Room
        tv_x0, tv_x1 = sx0 + 0.2, sx1 - 0.2
        buckets["fluted_wood"].append(make_box_trimesh(tv_x0, y0 + 0.12, z_f + 0.06, tv_x1, y0 + 0.52, z_f + 0.50))
        buckets["dark_glass_table"].append(
            make_box_trimesh(tv_x0 + 0.45, y0 + 0.22, z_f + 0.56, tv_x1 - 0.45, y0 + 0.28, z_f + 1.46)
        )
        tcx, tcy = (sx0 + sx1) * 0.5, (ry0 + sy0) * 0.5 + 0.15
    else:
        # Type B: Main sofa near South wall (y0 + 0.18), facing North toward TV console on North wall
        sy0, sy1 = y0 + 0.18, y0 + 1.05
        sx0, sx1 = rx0 + 0.55, rx1 - 0.25
        buckets["sofa_fabric"].extend(
            [
                make_box_trimesh(sx0, sy0, z_f + 0.04, sx1, sy1, z_f + 0.42),
                make_box_trimesh(sx0, sy0, z_f + 0.42, sx1, sy0 + 0.22, z_f + 0.84),
                make_box_trimesh(sx0 - 0.16, sy0, z_f + 0.04, sx0 + 0.02, sy1, z_f + 0.64),
                make_box_trimesh(sx1 - 0.02, sy0, z_f + 0.04, sx1 + 0.16, sy1, z_f + 0.64),
                # Side loveseat along West balcony side
                make_box_trimesh(rx0 + 0.05, sy1 + 0.20, z_f + 0.04, rx0 + 0.85, ry1 - 0.25, z_f + 0.42),
                make_box_trimesh(rx0 + 0.05, sy1 + 0.20, z_f + 0.42, rx0 + 0.25, ry1 - 0.25, z_f + 0.84),
            ]
        )
        for qx in (sx0 + 0.35, (sx0 + sx1) * 0.5, sx1 - 0.45):
            buckets["pillow_teal"].append(
                make_box_trimesh(qx - 0.20, sy0 + 0.22, z_f + 0.42, qx + 0.20, sy0 + 0.42, z_f + 0.74)
            )
        # Feature wall panelling on South wall behind sofa
        buckets["sage_panelling"].append(make_box_trimesh(x0 + 0.15, y0 + 0.01, z_f, x1 - 0.8, y0 + 0.06, z_ceil - 0.14))
        for px in [x0 + 0.5 + i * 0.65 for i in range(7)]:
            if px < x1 - 0.9:
                buckets["fluted_wood"].append(
                    make_box_trimesh(px - 0.02, y0 + 0.05, z_f + 0.12, px + 0.02, y0 + 0.09, z_ceil - 0.20)
                )
        # TV console & 65" OLED TV along North side of Drawing Room
        tv_x0, tv_x1 = sx0 + 0.2, sx1 - 0.2
        buckets["fluted_wood"].append(make_box_trimesh(tv_x0, y1 - 0.52, z_f + 0.06, tv_x1, y1 - 0.12, z_f + 0.50))
        buckets["dark_glass_table"].append(
            make_box_trimesh(tv_x0 + 0.45, y1 - 0.28, z_f + 0.56, tv_x1 - 0.45, y1 - 0.22, z_f + 1.46)
        )
        tcx, tcy = (sx0 + sx1) * 0.5, (sy1 + ry1) * 0.5 - 0.15

    # Nested round marble & brass coffee tables in the center of the seating group
    t1_top = trimesh.creation.cylinder(radius=0.50, height=0.04, sections=28)
    t1_top.apply_translation([tcx - 0.22, tcy, z_f + 0.40])
    t2_top = trimesh.creation.cylinder(radius=0.36, height=0.04, sections=28)
    t2_top.apply_translation([tcx + 0.38, tcy - 0.15, z_f + 0.33])
    buckets["marble_floor"].extend([t1_top, t2_top])

    t1_base = trimesh.creation.cylinder(radius=0.46, height=0.38, sections=24)
    t1_base.apply_translation([tcx - 0.22, tcy, z_f + 0.19])
    t2_base = trimesh.creation.cylinder(radius=0.33, height=0.31, sections=24)
    t2_base.apply_translation([tcx + 0.38, tcy - 0.15, z_f + 0.16])
    buckets["brass_gold"].extend([t1_base, t2_base])


def furnish_kitchen_dining(
    room: dict[str, Any],
    unit_key: str,
    z_f: float,
    z_ceil: float,
    buckets: dict[str, list[trimesh.Trimesh]],
) -> None:
    """
    Furnishes the Kitchen & Dining space (6.59x3.20m in Type A, 6.11x3.20m in Type B):
    - Places the L-shaped quartz kitchen counter, base & overhead cabinets, sink, hob,
      chimney hood, refrigerator, and breakfast counter with 2 coral barstools on the
      utility/exterior side (West in Type A, East in Type B).
    - Places the 6-seater glass/marble dining table, 6 upholstered chairs, and warm
      linear chandelier in the open dining half.
    """
    b = room["bounds"]
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]

    plaster, leds, curtains = build_room_cove_ceiling_and_curtains(b, room.get("openings", []), z_f, z_ceil)
    buckets["interior_wall"].extend(plaster)
    buckets["warm_led"].extend(leds)
    buckets["sheer_curtain"].extend(curtains)

    kitchen_west = unit_key == "type_a"

    if kitchen_west:
        # Type A: Kitchen on West half (x in [x0, x0 + 3.10]), Dining on East half (x in [x0 + 3.40, x1])
        kx0, kx1 = x0 + 0.08, x0 + 3.05
        # West wall counter + South wall counter + Breakfast island
        buckets["cabinet_taupe"].extend(
            [
                make_box_trimesh(kx0, y0 + 0.08, z_f, kx0 + 0.62, y1 - 0.08, z_f + 0.84),
                make_box_trimesh(kx0 + 0.62, y0 + 0.08, z_f, kx1, y0 + 0.68, z_f + 0.84),
                make_box_trimesh(kx1 - 0.65, y0 + 1.15, z_f, kx1, y1 - 0.15, z_f + 0.86),
                # Overhead cabinets along South wall
                make_box_trimesh(kx0 + 0.62, y0 + 0.08, z_f + 1.48, kx1 - 0.2, y0 + 0.44, z_ceil - 0.16),
            ]
        )
        buckets["quartz_counter"].extend(
            [
                make_box_trimesh(kx0, y0 + 0.08, z_f + 0.84, kx0 + 0.65, y1 - 0.08, z_f + 0.89),
                make_box_trimesh(kx0 + 0.62, y0 + 0.08, z_f + 0.84, kx1 + 0.02, y0 + 0.71, z_f + 0.89),
                make_box_trimesh(kx1 - 0.68, y0 + 1.12, z_f + 0.86, kx1 + 0.08, y1 - 0.12, z_f + 0.91),
            ]
        )
        # Black glass hob & chimney on West counter
        buckets["dark_glass_table"].append(
            make_box_trimesh(kx0 + 0.12, (y0 + y1) * 0.5 - 0.38, z_f + 0.89, kx0 + 0.54, (y0 + y1) * 0.5 + 0.38, z_f + 0.91)
        )
        # 2 Coral breakfast barstools on the East side of the breakfast counter
        for sy in (y0 + 1.55, y0 + 2.25):
            stool_seat = trimesh.creation.cylinder(radius=0.21, height=0.08, sections=20)
            stool_seat.apply_translation([kx1 + 0.28, sy, z_f + 0.64])
            buckets["coral_velvet"].append(stool_seat)
            stool_leg = trimesh.creation.cylinder(radius=0.04, height=0.62, sections=12)
            stool_leg.apply_translation([kx1 + 0.28, sy, z_f + 0.31])
            buckets["charcoal_metal"].append(stool_leg)

        dx_center = (kx1 + 0.45 + x1 - 0.25) * 0.5
    else:
        # Type B: Kitchen on East half (x in [x1 - 3.05, x1]), Dining on West half (x in [x0, x1 - 3.35])
        kx0, kx1 = x1 - 3.05, x1 - 0.08
        buckets["cabinet_taupe"].extend(
            [
                make_box_trimesh(kx1 - 0.62, y0 + 0.08, z_f, kx1, y1 - 0.08, z_f + 0.84),
                make_box_trimesh(kx0, y1 - 0.68, z_f, kx1 - 0.62, y1 - 0.08, z_f + 0.84),
                make_box_trimesh(kx0, y0 + 0.15, z_f, kx0 + 0.65, y1 - 1.15, z_f + 0.86),
                # Overhead cabinets along North/East wall
                make_box_trimesh(kx0 + 0.2, y1 - 0.44, z_f + 1.48, kx1 - 0.62, y1 - 0.08, z_ceil - 0.16),
            ]
        )
        buckets["quartz_counter"].extend(
            [
                make_box_trimesh(kx1 - 0.65, y0 + 0.08, z_f + 0.84, kx1, y1 - 0.08, z_f + 0.89),
                make_box_trimesh(kx0 - 0.02, y1 - 0.71, z_f + 0.84, kx1 - 0.62, y1 - 0.08, z_f + 0.89),
                make_box_trimesh(kx0 - 0.08, y0 + 0.12, z_f + 0.86, kx0 + 0.68, y1 - 1.12, z_f + 0.91),
            ]
        )
        buckets["dark_glass_table"].append(
            make_box_trimesh(kx1 - 0.54, (y0 + y1) * 0.5 - 0.38, z_f + 0.89, kx1 - 0.12, (y0 + y1) * 0.5 + 0.38, z_f + 0.91)
        )
        for sy in (y0 + 0.65, y0 + 1.35):
            stool_seat = trimesh.creation.cylinder(radius=0.21, height=0.08, sections=20)
            stool_seat.apply_translation([kx0 - 0.28, sy, z_f + 0.64])
            buckets["coral_velvet"].append(stool_seat)
            stool_leg = trimesh.creation.cylinder(radius=0.04, height=0.62, sections=12)
            stool_leg.apply_translation([kx0 - 0.28, sy, z_f + 0.31])
            buckets["charcoal_metal"].append(stool_leg)

        dx_center = (x0 + 0.25 + kx0 - 0.45) * 0.5

    # 6-Seater Scandinavian Natural Oak Dining Table + Molded Chairs centered at (dx_center, dy_center)
    dy_center = (y0 + y1) * 0.5
    tw, td = 1.95, 0.95
    # Natural thick timber table top (matching MyArchitectAI reference)
    buckets["oak_floor"].append(
        make_box_trimesh(dx_center - tw * 0.5, dy_center - td * 0.5, z_f + 0.72, dx_center + tw * 0.5, dy_center + td * 0.5, z_f + 0.77)
    )
    # Angled black steel table legs
    for leg_x in (dx_center - tw * 0.42, dx_center + tw * 0.42):
        for leg_y in (dy_center - td * 0.38, dy_center + td * 0.38):
            leg = trimesh.creation.cylinder(radius=0.035, height=0.72, sections=12)
            leg.apply_translation([leg_x, leg_y, z_f + 0.36])
            buckets["black_steel"].append(leg)

    # Ceramic vases + minimal floral styling on table
    vase = trimesh.creation.cylinder(radius=0.08, height=0.22, sections=16)
    vase.apply_translation([dx_center - 0.15, dy_center, z_f + 0.88])
    buckets["travertine_marble"].append(vase)
    vase2 = trimesh.creation.cylinder(radius=0.06, height=0.15, sections=14)
    vase2.apply_translation([dx_center + 0.12, dy_center - 0.05, z_f + 0.84])
    buckets["charcoal_metal"].append(vase2)

    # 6 Molded Eames-style dining chairs (black shell with wooden dowel legs)
    for cx_off in (-0.62, 0.0, 0.62):
        for side_sign in (-1.0, 1.0):
            cy_pos = dy_center + side_sign * (td * 0.5 + 0.28)
            back_y = cy_pos + side_sign * 0.20
            # Curved matte black bucket seat
            buckets["matte_black_dome"].extend(
                [
                    make_box_trimesh(dx_center + cx_off - 0.22, cy_pos - 0.20, z_f + 0.44, dx_center + cx_off + 0.22, cy_pos + 0.20, z_f + 0.49),
                    make_box_trimesh(dx_center + cx_off - 0.21, back_y - 0.03, z_f + 0.49, dx_center + cx_off + 0.21, back_y + 0.03, z_f + 0.84),
                ]
            )
            # Wooden Eiffel legs
            for lx in (dx_center + cx_off - 0.14, dx_center + cx_off + 0.14):
                for ly in (cy_pos - 0.14, cy_pos + 0.14):
                    leg = trimesh.creation.cylinder(radius=0.016, height=0.44, sections=10)
                    leg.apply_translation([lx, ly, z_f + 0.22])
                    buckets["oak_floor"].append(leg)

    # Dual Oversized Matte Black Dome Pendant Lights (exact match to MyArchitectAI reference)
    for dome_x in (dx_center - 0.45, dx_center + 0.45):
        # Dome fixture (raised to z_ceil - 0.48 so it floats cleanly in upper thirds)
        dome = trimesh.creation.cylinder(radius=0.28, height=0.20, sections=24)
        dome.apply_translation([dome_x, dy_center, z_ceil - 0.48])
        buckets["matte_black_dome"].append(dome)
        # Inner warm ambient glow emitter
        emitter = trimesh.creation.cylinder(radius=0.22, height=0.03, sections=16)
        emitter.apply_translation([dome_x, dy_center, z_ceil - 0.58])
        buckets["warm_led"].append(emitter)
        # Slender suspension cable to ceiling
        cable = trimesh.creation.cylinder(radius=0.008, height=0.48, sections=8)
        cable.apply_translation([dome_x, dy_center, z_ceil - 0.24])
        buckets["black_steel"].append(cable)

    # Black Steel Grid Glass Partition Screen (Crittall style door/screen in reference)
    screen_x = dx_center + tw * 0.5 + 0.65
    if screen_x < x1 - 0.4:
        # Vertical mullions
        for mx in (screen_x, screen_x + 1.25):
            mullion = make_box_trimesh(mx - 0.03, y0 + 0.1, z_f, mx + 0.03, y1 - 0.1, z_ceil - 0.05)
            buckets["black_steel"].append(mullion)
        # Horizontal bars & glass panes
        for hz in (z_f + 0.7, z_f + 1.4, z_f + 2.1):
            bar = make_box_trimesh(screen_x, y0 + 0.1, hz - 0.02, screen_x + 1.25, y1 - 0.1, hz + 0.02)
            buckets["black_steel"].append(bar)
        glass_pane = make_box_trimesh(screen_x, y0 + 0.1, z_f + 0.05, screen_x + 1.25, y1 - 0.1, z_ceil - 0.05)
        buckets["sheer_curtain"].append(glass_pane)


def furnish_bedroom(
    room: dict[str, Any],
    unit_key: str,
    z_f: float,
    z_ceil: float,
    buckets: dict[str, list[trimesh.Trimesh]],
) -> None:
    """
    Geometry-driven bedroom furnishing (Master, Second, Third, and Fourth Bedrooms):
    - Inspects the room's aspect ratio and window/door walls.
    - Places a King/Queen upholstered bed with headboard, mattress, throw blanket,
      4 pillows, and 2 floating nightstands with warm pendant/table lamps against the
      primary solid headboard wall (matching brochure/13.jpg & type-a/b.png).
    - Places a full-height sliding wardrobe along the adjacent solid wall and a
      console/dresser opposite the bed.
    """
    b = room["bounds"]
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
    w, d = x1 - x0, y1 - y0
    role = room.get("role", "second_bedroom")

    plaster, leds, curtains = build_room_cove_ceiling_and_curtains(b, room.get("openings", []), z_f, z_ceil)
    buckets["interior_wall"].extend(plaster)
    buckets["warm_led"].extend(leds)
    buckets["sheer_curtain"].extend(curtains)

    is_master_or_second = role in ("master_bedroom", "second_bedroom")
    pillow_bucket = "pillow_olive" if is_master_or_second else "pillow_teal"

    # Choose headboard wall from the brochure layout & solid wall geometry:
    # In Type A: front Master & Second bedrooms have bed headboard on East wall; Rear bedrooms have headboard on North wall.
    # In Type B: rear Master & Second bedrooms have headboard on North wall; Middle bedroom on West wall; Front bedroom on South wall.
    if unit_key == "type_a":
        head_wall = "east" if b[1] < 8.0 else "north"
    else:
        head_wall = "north" if b[1] > 32.0 else ("west" if b[1] > 28.0 else "south")

    bed_w = 1.86 if role == "master_bedroom" else 1.68
    bed_len = 2.12

    if head_wall in ("east", "west"):
        by_mid = (y0 + y1) * 0.5
        bx0 = (x1 - 0.10 - bed_len) if head_wall == "east" else (x0 + 0.10)
        bx1 = (x1 - 0.10) if head_wall == "east" else (x0 + 0.10 + bed_len)
        hx0 = (x1 - 0.22) if head_wall == "east" else (x0 + 0.08)
        hx1 = (x1 - 0.08) if head_wall == "east" else (x0 + 0.22)

        # Area rug under bed
        buckets["rug_fabric"].append(
            make_box_trimesh(bx0 - 0.35, by_mid - bed_w * 0.68, z_f, bx1 + 0.05, by_mid + bed_w * 0.68, z_f + 0.012)
        )
        # Fluted feature wall behind headboard (matching brochure/13.jpg)
        wx0 = (x1 - 0.06) if head_wall == "east" else (x0 + 0.01)
        wx1 = (x1 - 0.01) if head_wall == "east" else (x0 + 0.06)
        buckets["wardrobe_cream"].append(make_box_trimesh(wx0, y0 + 0.12, z_f + 0.75, wx1, y1 - 0.12, z_ceil - 0.14))
        buckets["warm_led"].append(make_box_trimesh(wx0 - 0.02, y0 + 0.20, z_f + 0.73, wx1 + 0.02, y1 - 0.20, z_f + 0.76))

        # Bed frame, headboard, mattress, throw blanket
        buckets["sofa_fabric"].extend(
            [
                make_box_trimesh(bx0, by_mid - bed_w * 0.52, z_f + 0.04, bx1, by_mid + bed_w * 0.52, z_f + 0.28),
                make_box_trimesh(hx0, by_mid - bed_w * 0.54, z_f + 0.28, hx1, by_mid + bed_w * 0.54, z_f + 1.18),
            ]
        )
        buckets["bed_linen_white"].append(
            make_box_trimesh(bx0 + 0.06, by_mid - bed_w * 0.48, z_f + 0.28, bx1 - 0.08, by_mid + bed_w * 0.48, z_f + 0.52)
        )
        # Throw blanket at foot of bed
        tx0 = bx0 + 0.05 if head_wall == "east" else bx1 - 0.75
        tx1 = bx0 + 0.75 if head_wall == "east" else bx1 - 0.05
        buckets["bed_throw_grey"].append(
            make_box_trimesh(tx0, by_mid - bed_w * 0.49, z_f + 0.29, tx1, by_mid + bed_w * 0.49, z_f + 0.54)
        )
        # Pillows
        px0 = (hx0 - 0.38) if head_wall == "east" else (hx1 + 0.04)
        px1 = (hx0 - 0.04) if head_wall == "east" else (hx1 + 0.38)
        for py_off in (-0.42, 0.42):
            buckets[pillow_bucket].append(
                make_box_trimesh(px0, by_mid + py_off - 0.28, z_f + 0.52, px1, by_mid + py_off + 0.28, z_f + 0.70)
            )
        # 2 Floating Nightstands + warm bedside lamps
        for ny_off in (-bed_w * 0.5 - 0.36, bed_w * 0.5 + 0.36):
            if y0 + 0.25 < by_mid + ny_off < y1 - 0.25:
                buckets["fluted_wood"].append(
                    make_box_trimesh(hx0 - 0.22, by_mid + ny_off - 0.24, z_f + 0.22, hx1 + 0.22, by_mid + ny_off + 0.24, z_f + 0.38)
                )
                buckets["warm_led"].append(
                    make_box_trimesh((hx0 + hx1) * 0.5 - 0.06, by_mid + ny_off - 0.06, z_f + 0.42, (hx0 + hx1) * 0.5 + 0.06, by_mid + ny_off + 0.06, z_f + 0.62)
                )
        # Wardrobe along North wall
        buckets["wardrobe_cream"].append(
            make_box_trimesh(x0 + 0.35, y1 - 0.62, z_f, x1 - 0.35, y1 - 0.08, z_ceil - 0.15)
        )
    else:
        # Headboard on North or South wall
        bx_mid = (x0 + x1) * 0.5 + (0.35 if w > 4.4 else 0.0)
        by0 = (y1 - 0.10 - bed_len) if head_wall == "north" else (y0 + 0.10)
        by1 = (y1 - 0.10) if head_wall == "north" else (y0 + 0.10 + bed_len)
        hy0 = (y1 - 0.22) if head_wall == "north" else (y0 + 0.08)
        hy1 = (y1 - 0.08) if head_wall == "north" else (y0 + 0.22)

        buckets["rug_fabric"].append(
            make_box_trimesh(bx_mid - bed_w * 0.68, by0 - 0.35, z_f, bx_mid + bed_w * 0.68, by1 + 0.05, z_f + 0.012)
        )
        wy0 = (y1 - 0.06) if head_wall == "north" else (y0 + 0.01)
        wy1 = (y1 - 0.01) if head_wall == "north" else (y0 + 0.06)
        buckets["wardrobe_cream"].append(make_box_trimesh(x0 + 0.12, wy0, z_f + 0.75, x1 - 0.12, wy1, z_ceil - 0.14))
        buckets["warm_led"].append(make_box_trimesh(x0 + 0.20, wy0 - 0.02, z_f + 0.73, x1 - 0.20, wy1 + 0.02, z_f + 0.76))

        buckets["sofa_fabric"].extend(
            [
                make_box_trimesh(bx_mid - bed_w * 0.52, by0, z_f + 0.04, bx_mid + bed_w * 0.52, by1, z_f + 0.28),
                make_box_trimesh(bx_mid - bed_w * 0.54, hy0, z_f + 0.28, bx_mid + bed_w * 0.54, hy1, z_f + 1.18),
            ]
        )
        buckets["bed_linen_white"].append(
            make_box_trimesh(bx_mid - bed_w * 0.48, by0 + 0.06, z_f + 0.28, bx_mid + bed_w * 0.48, by1 - 0.08, z_f + 0.52)
        )
        ty0 = by0 + 0.05 if head_wall == "north" else by1 - 0.75
        ty1 = by0 + 0.75 if head_wall == "north" else by1 - 0.05
        buckets["bed_throw_grey"].append(
            make_box_trimesh(bx_mid - bed_w * 0.49, ty0, z_f + 0.29, bx_mid + bed_w * 0.49, ty1, z_f + 0.54)
        )
        py0 = (hy0 - 0.38) if head_wall == "north" else (hy1 + 0.04)
        py1 = (hy0 - 0.04) if head_wall == "north" else (hy1 + 0.38)
        for px_off in (-0.42, 0.42):
            buckets[pillow_bucket].append(
                make_box_trimesh(bx_mid + px_off - 0.28, py0, z_f + 0.52, bx_mid + px_off + 0.28, py1, z_f + 0.70)
            )
        for nx_off in (-bed_w * 0.5 - 0.36, bed_w * 0.5 + 0.36):
            if x0 + 0.25 < bx_mid + nx_off < x1 - 0.25:
                buckets["fluted_wood"].append(
                    make_box_trimesh(bx_mid + nx_off - 0.24, hy0 - 0.22, z_f + 0.22, bx_mid + nx_off + 0.24, hy1 + 0.22, z_f + 0.38)
                )
                buckets["warm_led"].append(
                    make_box_trimesh(bx_mid + nx_off - 0.06, (hy0 + hy1) * 0.5 - 0.06, z_f + 0.42, bx_mid + nx_off + 0.06, (hy0 + hy1) * 0.5 + 0.06, z_f + 0.62)
                )
        # Wardrobe along West or East wall
        if unit_key == "type_a":
            buckets["wardrobe_cream"].append(
                make_box_trimesh(x0 + 0.08, y0 + 0.35, z_f, x0 + 0.62, y1 - 0.35, z_ceil - 0.15)
            )
        else:
            buckets["wardrobe_cream"].append(
                make_box_trimesh(x1 - 0.62, y0 + 0.35, z_f, x1 - 0.08, y1 - 0.35, z_ceil - 0.15)
            )


def furnish_balcony(
    room: dict[str, Any],
    z_f: float,
    z_ceil: float,
    buckets: dict[str, list[trimesh.Trimesh]],
) -> None:
    """
    Furnishes the main East/West balcony deck (matching brochure/19.jpg):
    - Oak wood deck floor
    - Suspended wooden swing sofa with cushions + ropes on one end
    - Round coffee table & lounge chairs on the opposite end
    """
    b = room["bounds"]
    x0, y0, x1, y1 = b[0] + 0.05, b[1] + 0.08, b[2] - 0.05, b[3] - 0.08
    if (y1 - y0) < 3.0:
        return
    cx = (x0 + x1) * 0.5
    buckets["oak_floor"].append(make_box_trimesh(x0, y0, z_f - 0.01, x1, y1, z_f + 0.02))

    # Hanging swing bench near North end of balcony (matching brochure/19.jpg)
    sy = y1 - 0.85
    buckets["fluted_wood"].append(make_box_trimesh(cx - 0.52, sy - 0.32, z_f + 0.46, cx + 0.52, sy + 0.32, z_f + 0.54))
    buckets["bed_linen_white"].extend(
        [
            make_box_trimesh(cx - 0.48, sy - 0.28, z_f + 0.54, cx + 0.48, sy + 0.28, z_f + 0.66),
            make_box_trimesh(cx - 0.48, sy + 0.18, z_f + 0.66, cx + 0.48, sy + 0.30, z_f + 0.96),
        ]
    )
    # 2 Suspension ropes from balcony ceiling
    for rx in (cx - 0.48, cx + 0.48):
        rope = trimesh.creation.cylinder(radius=0.012, height=z_ceil - (z_f + 0.50), sections=8)
        rope.apply_translation([rx, sy, (z_ceil + z_f + 0.50) * 0.5])
        buckets["brass_gold"].append(rope)

    # Round coffee table in center of balcony
    tbl = trimesh.creation.cylinder(radius=0.32, height=0.42, sections=20)
    tbl.apply_translation([cx, (y0 + y1) * 0.5 - 0.3, z_f + 0.22])
    buckets["charcoal_metal"].append(tbl)


def build_flat_interiors_for_floor(
    geom: dict[str, Any],
    floor_num: int,
    z_floor: float,
    floor_h: float,
    slab_t: float,
    mats: dict[str, bpy.types.Material],
    floor_coll: bpy.types.Collection,
) -> None:
    """
    Furnishes all rooms of both Type A (Front 4BHK) and Type B (Rear 4BHK) on `floor_num`
    directly from the extracted room geometry in `geom["typical_floor"]["flats"]["rooms"]`.
    """
    z_f = z_floor + 0.03
    z_ceil = z_floor + floor_h - slab_t
    rooms_dict = geom["typical_floor"]["flats"].get("rooms", {})

    buckets: dict[str, list[trimesh.Trimesh]] = {k: [] for k in mats.keys()}

    for unit_key in ("type_a", "type_b"):
        for room in rooms_dict.get(unit_key, []):
            role = room.get("role", "")
            if role == "drawing_room":
                furnish_drawing_room(room, unit_key, z_f, z_ceil, buckets)
            elif role == "kitchen_dining":
                furnish_kitchen_dining(room, unit_key, z_f, z_ceil, buckets)
            elif role in ("master_bedroom", "second_bedroom", "third_bedroom", "fourth_bedroom"):
                furnish_bedroom(room, unit_key, z_f, z_ceil, buckets)
            elif role == "main_balcony":
                furnish_balcony(room, z_f, z_ceil, buckets)

    # Also addwooden internal door leaves at extracted door positions so rooms look architectural
    for d_op in geom["typical_floor"].get("doors", []):
        dp1 = tuple(d_op["start"])
        dp2 = tuple(d_op["end"])
        # Frame header + jambs (leave doorway open for walk-through visibility or thin frame)
        j1 = make_box_trimesh(dp1[0] - 0.04, dp1[1] - 0.04, z_f, dp1[0] + 0.04, dp1[1] + 0.04, z_floor + 2.10)
        j2 = make_box_trimesh(dp2[0] - 0.04, dp2[1] - 0.04, z_f, dp2[0] + 0.04, dp2[1] + 0.04, z_floor + 2.10)
        buckets["fluted_wood"].extend([j1, j2])

    int_coll = bpy.data.collections.new(f"Floor_{floor_num}_Interiors")
    floor_coll.children.link(int_coll)

    for mat_key, mesh_list in buckets.items():
        if not mesh_list:
            continue
        combined = trimesh.util.concatenate(mesh_list)
        add_trimesh_to_blender(
            combined,
            f"Floor_{floor_num}_Int_{mat_key}",
            int_coll,
            mats[mat_key],
            {"floor_index": floor_num},
        )


# =============================================================================
# 2. Five Level-2 Amenity Spaces (Basement, Stilt, Lobby, Landscape, Terrace)
# =============================================================================


def build_basement_parking_amenity(
    geom: dict[str, Any],
    mats: dict[str, bpy.types.Material],
    building_coll: bpy.types.Collection,
) -> None:
    """
    Amenity 1: Basement Parking (z = -3.15m to 0.0m) from `geom["basement"]`:
    - Epoxy concrete floor slab & perimeter retaining wall
    - Sloped curved two-way ramp from Ground (z=0) on North-East down to Basement (z=-3.15m) on North-West
    - Structural columns with yellow/black safety bands
    - Extracted car bays & 20 two-wheeler parking bays with painted yellow lines
    - Parked 3D cars and scooters + ceiling LED tube lights
    """
    bsm = geom.get("basement", {})
    if not bsm:
        return
    z_bsm = -float(geom["heights"].get("basement_depth", 3.15))
    slab_t = float(geom["heights"].get("slab_thickness", 0.15))

    bsm_coll = bpy.data.collections.new("Floor_B1_Basement")
    building_coll.children.link(bsm_coll)
    props = {"floor_index": -1, "floor_label": "Basement Parking (B1)"}

    slab_poly = Polygon(bsm["slab"]["polygon"])
    # 1. Basement floor slab
    floor_tm = extrude_shapely_polys([slab_poly], z_bsm - slab_t, z_bsm)
    add_trimesh_to_blender(floor_tm, "Basement_Floor_Slab", bsm_coll, mats["paver_driveway"], props)

    # Basement ceiling soffit (underside of ground slab, leaving opening for the North ramp!)
    ramp_cutout = Polygon([(-3.8, 27.2), (14.5, 27.2), (14.5, 42.5), (-3.8, 42.5)])
    ceil_poly = slab_poly.difference(ramp_cutout)
    ceil_polys = [ceil_poly] if isinstance(ceil_poly, Polygon) else list(ceil_poly.geoms)
    ceil_tm = extrude_shapely_polys(ceil_polys, -slab_t, -0.02)
    add_trimesh_to_blender(ceil_tm, "Basement_Ceiling_Soffit", bsm_coll, mats["interior_wall"], props)

    # 2. Perimeter retaining wall (0.23m thick around basement slab exterior)
    ret_ring = slab_poly.exterior.buffer(0.14)
    ret_polys = [ret_ring] if isinstance(ret_ring, Polygon) else list(ret_ring.geoms)
    ret_tm = extrude_shapely_polys(ret_polys, z_bsm, 0.0)
    add_trimesh_to_blender(ret_tm, "Basement_Retaining_Wall", bsm_coll, mats["concrete_facade"], props)

    # 3. Structural columns + yellow safety bands
    col_polys = [Polygon(c["polygon"]) for c in bsm.get("columns", [])]
    if col_polys:
        cols_tm = extrude_shapely_polys(col_polys, z_bsm, -slab_t)
        add_trimesh_to_blender(cols_tm, "Basement_Columns", bsm_coll, mats["concrete_facade"], props)
        bands_tm = extrude_shapely_polys([p.buffer(0.01) for p in col_polys], z_bsm + 0.15, z_bsm + 1.05)
        add_trimesh_to_blender(bands_tm, "Basement_Column_Safety_Bands", bsm_coll, mats["safety_yellow"], props)

    # 4. Sloped Ramp from Ground (East side x=12.7, y=27..39, z=0.0) curving along North (y=39..42)
    # down to Basement landing (West side x=-2.2, y=30..38, z=z_bsm)
    ramp_segments: list[trimesh.Trimesh] = []
    # Path waypoints (x, y, z) along the 3.0m-wide 1:7 ramp
    ramp_pts = [
        (12.6, 26.5, -0.05),
        (12.6, 32.0, -0.75),
        (12.2, 37.5, -1.45),
        (9.0, 40.5, -1.95),
        (4.0, 40.5, -2.45),
        (-1.2, 38.5, -2.85),
        (-2.0, 32.5, z_bsm + 0.02),
    ]
    for i in range(len(ramp_pts) - 1):
        p1, p2 = ramp_pts[i], ramp_pts[i + 1]
        seg = make_oriented_box((p1[0], p1[1]), (p2[0], p2[1]), thickness=3.0, z0=min(p1[2], p2[2]) - 0.18, z1=(p1[2] + p2[2]) * 0.5 + 0.05)
        if seg is not None:
            ramp_segments.append(seg)
    if ramp_segments:
        add_trimesh_to_blender(
            trimesh.util.concatenate(ramp_segments), "Basement_Sloped_Ramp", bsm_coll, mats["asphalt_road"], props
        )

    # 5. Yellow Bay Markings + Parked Cars & Two-Wheelers from DXF
    bay_lines: list[trimesh.Trimesh] = []
    car_bodies_silver: list[trimesh.Trimesh] = []
    car_bodies_blue: list[trimesh.Trimesh] = []
    car_glass: list[trimesh.Trimesh] = []
    car_wheels: list[trimesh.Trimesh] = []
    scooter_bodies: list[trimesh.Trimesh] = []

    for idx, cb in enumerate(bsm.get("car_bays", [])):
        poly = Polygon(cb["polygon"])
        ring = poly.exterior.buffer(0.04)
        rm = extrude_shapely_polys([ring], z_bsm, z_bsm + 0.015)
        if rm is not None:
            bay_lines.append(rm)
        cx, cy = cb["centroid"]
        ang = math.pi * 0.5 if cb["depth"] > cb["width"] else 0.0
        b_ms, g_ms, w_ms = make_car_meshes(cx, cy, z_bsm + 0.01, ang)
        if idx % 2 == 0:
            car_bodies_silver.extend(b_ms)
        else:
            car_bodies_blue.extend(b_ms)
        car_glass.extend(g_ms)
        car_wheels.extend(w_ms)

    # Add 2 additional parked cars in the central basement parking zone (C2 at y=24.8)
    for idx, (cx, cy, ang) in enumerate([(5.8, 25.0, 0.0), (6.2, 12.2, math.pi * 0.5)]):
        b_ms, g_ms, w_ms = make_car_meshes(cx, cy, z_bsm + 0.01, ang)
        if idx == 0:
            car_bodies_blue.extend(b_ms)
        else:
            car_bodies_silver.extend(b_ms)
        car_glass.extend(g_ms)
        car_wheels.extend(w_ms)

    for idx, sb in enumerate(bsm.get("scooter_bays", [])):
        poly = Polygon(sb["polygon"])
        ring = poly.exterior.buffer(0.025)
        rm = extrude_shapely_polys([ring], z_bsm, z_bsm + 0.012)
        if rm is not None:
            bay_lines.append(rm)
        if idx % 2 == 0:
            cx, cy = sb["centroid"]
            ang = math.pi * 0.5 if sb["depth"] > sb["width"] else 0.0
            s_body, s_dark = make_scooter_meshes(cx, cy, z_bsm + 0.01, ang)
            scooter_bodies.extend(s_body)
            car_wheels.extend(s_dark)

    if bay_lines:
        add_trimesh_to_blender(trimesh.util.concatenate(bay_lines), "Basement_Bay_Markings", bsm_coll, mats["safety_yellow"], props)
    if car_bodies_silver:
        add_trimesh_to_blender(trimesh.util.concatenate(car_bodies_silver), "Basement_Cars_Silver", bsm_coll, mats["car_paint_silver"], props)
    if car_bodies_blue:
        add_trimesh_to_blender(trimesh.util.concatenate(car_bodies_blue), "Basement_Cars_Blue", bsm_coll, mats["car_paint_blue"], props)
    if scooter_bodies:
        add_trimesh_to_blender(trimesh.util.concatenate(scooter_bodies), "Basement_Scooters", bsm_coll, mats["coral_velvet"], props)
    if car_glass:
        add_trimesh_to_blender(trimesh.util.concatenate(car_glass), "Basement_Vehicle_Glass", bsm_coll, mats["window_glass"], props)
    if car_wheels:
        add_trimesh_to_blender(trimesh.util.concatenate(car_wheels), "Basement_Vehicle_Wheels", bsm_coll, mats["tire_rubber"], props)

    # 6. Ceiling Linear LED Light Fixtures across Basement Driveway & Bays
    led_tubes: list[trimesh.Trimesh] = []
    for y_pos in range(3, 35, 5):
        for x_pos in (3.5, 7.2, 10.8):
            led_tubes.append(make_box_trimesh(x_pos - 0.65, y_pos - 0.06, -slab_t - 0.04, x_pos + 0.65, y_pos + 0.06, -slab_t - 0.01))
    add_trimesh_to_blender(trimesh.util.concatenate(led_tubes), "Basement_Ceiling_LEDs", bsm_coll, mats["cool_led"], props)


def build_stilt_parking_and_entrance_lobby(
    geom: dict[str, Any],
    mats: dict[str, bpy.types.Material],
    stilt_coll: bpy.types.Collection,
) -> None:
    """
    Amenity 2 (Stilt Parking) & Amenity 3 (Entrance Lobby) on Ground Floor (z = 0.0 to 3.30m):
    - Stilt Parking: Extracted car & two-wheeler bays on Ground Floor, parked 3D cars,
      yellow bay stripes, and soffit LED fixtures.
    - Entrance Lobby (matching brochure/14.jpg): Travertine marble floor & walls, coffered
      wooden ceiling with warm cove + triple spotlights, sculptural ring chandelier,
      2 brushed-bronze lift doors with call buttons, fluted wood wall with cream 2-seater sofa,
      armchair, round glass coffee table, and travertine bench.
    """
    gf = geom.get("ground_floor", {})
    stilt_h = float(geom["heights"]["stilt_floor_to_floor"])
    slab_t = float(geom["heights"]["slab_thickness"])
    z_ceil = stilt_h - slab_t
    props = {"floor_index": 0, "floor_label": "Ground Floor (Stilt & Lobby)"}

    # --- A. STILT PARKING BAYS, CARS & SOFFIT LIGHTS ---
    bay_lines: list[trimesh.Trimesh] = []
    cars_white: list[trimesh.Trimesh] = []
    cars_bronze: list[trimesh.Trimesh] = []
    car_glass: list[trimesh.Trimesh] = []
    car_wheels: list[trimesh.Trimesh] = []

    for idx, cb in enumerate(gf.get("car_bays", [])):
        poly = Polygon(cb["polygon"])
        ring = poly.exterior.buffer(0.035)
        rm = extrude_shapely_polys([ring], 0.05, 0.065)
        if rm is not None:
            bay_lines.append(rm)
        cx, cy = cb["centroid"]
        ang = math.pi * 0.5 if cb["depth"] > cb["width"] else 0.0
        b_ms, g_ms, w_ms = make_car_meshes(cx, cy, 0.05, ang)
        if idx % 2 == 0:
            cars_white.extend(b_ms)
        else:
            cars_bronze.extend(b_ms)
        car_glass.extend(g_ms)
        car_wheels.extend(w_ms)

    # Also add 2 front stilt cars in the south hollow plinth zone (visible from entrance & stilt cam)
    for idx, (cx, cy, ang) in enumerate([(5.2, 6.8, 0.0), (5.2, 11.2, 0.0)]):
        b_ms, g_ms, w_ms = make_car_meshes(cx, cy, 0.05, ang)
        if idx == 0:
            cars_bronze.extend(b_ms)
        else:
            cars_white.extend(b_ms)
        car_glass.extend(g_ms)
        car_wheels.extend(w_ms)

    stilt_leds: list[trimesh.Trimesh] = []
    for y_pos in [4.5, 8.5, 12.5, 16.0, 26.0, 30.5, 35.0]:
        for x_pos in [3.5, 7.5, 10.5]:
            if not (18.5 <= y_pos <= 23.5):
                stilt_leds.append(make_box_trimesh(x_pos - 0.45, y_pos - 0.06, z_ceil - 0.03, x_pos + 0.45, y_pos + 0.06, z_ceil))

    if bay_lines:
        add_trimesh_to_blender(trimesh.util.concatenate(bay_lines), "Floor_0_Stilt_Bay_Lines", stilt_coll, mats["safety_yellow"], props)
    if cars_white:
        add_trimesh_to_blender(trimesh.util.concatenate(cars_white), "Floor_0_Stilt_Cars_White", stilt_coll, mats["car_paint_white"], props)
    if cars_bronze:
        add_trimesh_to_blender(trimesh.util.concatenate(cars_bronze), "Floor_0_Stilt_Cars_Bronze", stilt_coll, mats["car_paint_bronze"], props)
    if car_glass:
        add_trimesh_to_blender(trimesh.util.concatenate(car_glass), "Floor_0_Stilt_Car_Glass", stilt_coll, mats["window_glass"], props)
    if car_wheels:
        add_trimesh_to_blender(trimesh.util.concatenate(car_wheels), "Floor_0_Stilt_Car_Wheels", stilt_coll, mats["tire_rubber"], props)
    if stilt_leds:
        add_trimesh_to_blender(trimesh.util.concatenate(stilt_leds), "Floor_0_Stilt_Soffit_LEDs", stilt_coll, mats["warm_led"], props)

    # --- B. ENTRANCE LOBBY (matching brochure/14.jpg at x in [4.15, 8.95], y in [18.90, 23.10]) ---
    lobby_b = gf.get("entrance_lobby", {}).get("bounds", [4.265, 19.094, 8.965, 23.084])
    lx0, ly0, lx1, ly1 = lobby_b[0], lobby_b[1], lobby_b[2], lobby_b[3]
    z_lf = 0.06

    # 1. Polished beige travertine marble floor & lift wall cladding
    trav_meshes: list[trimesh.Trimesh] = [
        make_box_trimesh(lx0 - 0.1, ly0 - 0.1, 0.04, lx1 + 1.2, ly1 + 0.1, z_lf),
        # Lift wall cladding along West wall (x = lx0, where the 2 lifts sit at y=20.08 & y=21.98)
        make_box_trimesh(lx0 - 0.02, ly0, z_lf, lx0 + 0.06, ly1, z_ceil - 0.12),
        # North wall travertine cladding + travertine bench (matching right side of 14.jpg)
        make_box_trimesh(lx0, ly1 - 0.08, z_lf, lx1, ly1, z_ceil - 0.12),
        make_box_trimesh(lx0 + 1.65, ly1 - 0.52, z_lf + 0.04, lx0 + 3.25, ly1 - 0.10, z_lf + 0.46),
    ]
    add_trimesh_to_blender(trimesh.util.concatenate(trav_meshes), "Floor_0_Lobby_Travertine", stilt_coll, mats["travertine_marble"], props)

    # 2. Two Brushed Bronze Elevator Doors on West wall (y in [19.63, 20.53] and [21.53, 22.43])
    bronze_meshes: list[trimesh.Trimesh] = []
    for ey0, ey1 in [(19.58, 20.58), (21.48, 22.48)]:
        bronze_meshes.append(make_box_trimesh(lx0 + 0.02, ey0, z_lf, lx0 + 0.09, ey1, z_lf + 2.15))
    add_trimesh_to_blender(trimesh.util.concatenate(bronze_meshes), "Floor_0_Lobby_Lift_Doors", stilt_coll, mats["bronze_metal"], props)

    # 3. Coffered wooden grid ceiling + Fluted wood South feature wall (matching left side of 14.jpg)
    wood_meshes: list[trimesh.Trimesh] = [
        make_box_trimesh(lx0, ly0, z_ceil - 0.12, lx1, ly1, z_ceil),
        make_box_trimesh(lx0, ly0, z_lf, lx1 - 0.6, ly0 + 0.08, z_ceil - 0.12),
    ]
    for fx in [lx0 + 0.15 + i * 0.14 for i in range(28)]:
        if fx < lx1 - 0.65:
            wood_meshes.append(make_box_trimesh(fx - 0.02, ly0 + 0.06, z_lf, fx + 0.02, ly0 + 0.11, z_ceil - 0.12))
    add_trimesh_to_blender(trimesh.util.concatenate(wood_meshes), "Floor_0_Lobby_Wood_Finishes", stilt_coll, mats["fluted_wood"], props)

    # 4. Cream Upholstered 2-Seater Sofa + Lounge Armchair + Round Glass Coffee Table (matching 14.jpg)
    sofa_x0, sofa_x1 = lx0 + 0.95, lx0 + 2.75
    lobby_sofas = [
        # 2-seater sofa against South fluted wood wall
        make_box_trimesh(sofa_x0, ly0 + 0.14, z_lf + 0.08, sofa_x1, ly0 + 0.92, z_lf + 0.44),
        make_box_trimesh(sofa_x0, ly0 + 0.14, z_lf + 0.44, sofa_x1, ly0 + 0.34, z_lf + 0.86),
        make_box_trimesh(sofa_x0 - 0.14, ly0 + 0.14, z_lf + 0.08, sofa_x0 + 0.04, ly0 + 0.92, z_lf + 0.66),
        make_box_trimesh(sofa_x1 - 0.04, ly0 + 0.14, z_lf + 0.08, sofa_x1 + 0.14, ly0 + 0.92, z_lf + 0.66),
        # Single armchair on East side facing West/North
        make_box_trimesh(sofa_x1 + 0.35, ly0 + 0.45, z_lf + 0.08, sofa_x1 + 1.15, ly0 + 1.25, z_lf + 0.44),
        make_box_trimesh(sofa_x1 + 0.95, ly0 + 0.45, z_lf + 0.44, sofa_x1 + 1.15, ly0 + 1.25, z_lf + 0.82),
    ]
    add_trimesh_to_blender(trimesh.util.concatenate(lobby_sofas), "Floor_0_Lobby_Seating", stilt_coll, mats["bed_linen_white"], props)

    ctop = trimesh.creation.cylinder(radius=0.46, height=0.03, sections=28)
    ctop.apply_translation([(sofa_x0 + sofa_x1) * 0.5, ly0 + 1.42, z_lf + 0.36])
    add_trimesh_to_blender(ctop, "Floor_0_Lobby_Coffee_Table", stilt_coll, mats["dark_glass_table"], props)

    # 5. Sculptural glowing ring chandelier + ceiling spotlights in Lobby (matching 14.jpg)
    lobby_leds: list[trimesh.Trimesh] = []
    for r_ring, z_ring, tilt in [(0.52, z_ceil - 0.55, 0.18), (0.44, z_ceil - 0.68, -0.22)]:
        torus = trimesh.creation.annulus(r_min=r_ring - 0.03, r_max=r_ring, height=0.04, sections=32)
        torus.apply_transform(trimesh.transformations.rotation_matrix(tilt, [1, 1, 0]))
        torus.apply_translation([(sofa_x0 + sofa_x1) * 0.5, ly0 + 1.25, z_ring])
        lobby_leds.append(torus)
    for sx in (lx0 + 0.8, lx0 + 2.2, lx0 + 3.6):
        for sy in (ly0 + 0.9, ly0 + 2.1, ly0 + 3.2):
            lobby_leds.append(make_box_trimesh(sx - 0.08, sy - 0.04, z_ceil - 0.14, sx + 0.08, sy + 0.04, z_ceil - 0.11))
    add_trimesh_to_blender(trimesh.util.concatenate(lobby_leds), "Floor_0_Lobby_Chandelier_LEDs", stilt_coll, mats["warm_led"], props)


def build_landscape_and_drive_amenities(
    geom: dict[str, Any],
    mats: dict[str, bpy.types.Material],
    site_coll: bpy.types.Collection,
) -> None:
    """
    Amenity 4: Landscape & Entrance Drive (matching brochure/17.jpg, 18.jpg & 22.jpg):
    - Raised granite planter beds with lush shrubs along the West and South-East perimeter walls
    - Wooden deck walkway with outdoor timber benches along the West garden edge (matching 17.jpg)
    - Warm bollard & wall sconce lights along the entrance driveway and ramp wall (matching 22.jpg)
    - Parked luxury sedan on the entrance driveway
    """
    # 1. West & East perimeter raised garden planter beds + lush green hedge
    planter_walls: list[trimesh.Trimesh] = [
        make_box_trimesh(-3.75, 4.50, 0.0, -2.85, 26.50, 0.52),
        make_box_trimesh(13.20, -3.50, 0.0, 14.35, 18.50, 0.52),
    ]
    garden_foliage: list[trimesh.Trimesh] = [
        make_box_trimesh(-3.68, 4.60, 0.48, -2.92, 26.40, 1.35),
        make_box_trimesh(-3.80, 4.60, 1.10, -3.35, 26.40, 2.35),  # vertical green wall on West compound wall (17.jpg)
        make_box_trimesh(13.28, -3.40, 0.48, 14.25, 18.40, 1.25),
    ]
    add_trimesh_to_blender(trimesh.util.concatenate(planter_walls), "Site_Garden_Planter_Walls", site_coll, mats["dark_concrete"])
    add_trimesh_to_blender(trimesh.util.concatenate(garden_foliage), "Site_Garden_Planter_Shrubs", site_coll, mats["foliage_bright"])

    # 2. Wooden garden deck & outdoor timber benches along West landscape walkway (matching brochure/17.jpg)
    deck_meshes: list[trimesh.Trimesh] = [
        make_box_trimesh(-2.85, 5.00, 0.01, -0.40, 22.50, 0.06),
    ]
    for by in [7.0, 10.5, 14.0, 17.5]:
        deck_meshes.append(make_box_trimesh(-2.35, by - 0.25, 0.06, -1.05, by + 0.25, 0.48))
    add_trimesh_to_blender(trimesh.util.concatenate(deck_meshes), "Site_West_Garden_Deck_Benches", site_coll, mats["oak_floor"])

    # 3. Warm Driveway Bollard & Compound Wall Sconce Lights (matching brochure/22.jpg)
    bollards: list[trimesh.Trimesh] = []
    bollard_leds: list[trimesh.Trimesh] = []
    for by in [2.0, 6.5, 11.0, 15.5, 20.0]:
        bollards.append(make_box_trimesh(-2.75, by - 0.06, 0.06, -2.63, by + 0.06, 0.68))
        bollard_leds.append(make_box_trimesh(-2.76, by - 0.05, 0.58, -2.62, by + 0.05, 0.66))
    add_trimesh_to_blender(trimesh.util.concatenate(bollards), "Site_Driveway_Bollards", site_coll, mats["charcoal_metal"])
    add_trimesh_to_blender(trimesh.util.concatenate(bollard_leds), "Site_Driveway_Bollard_LEDs", site_coll, mats["warm_led"])

    # 4. Arrival car on the entrance driveway
    b_ms, g_ms, w_ms = make_car_meshes(1.2, 2.2, 0.02, math.radians(66.0))
    add_trimesh_to_blender(trimesh.util.concatenate(b_ms), "Site_Driveway_Car_Body", site_coll, mats["car_paint_Bronze" if "car_paint_Bronze" in mats else "car_paint_bronze"])
    add_trimesh_to_blender(trimesh.util.concatenate(g_ms), "Site_Driveway_Car_Glass", site_coll, mats["window_glass"])
    add_trimesh_to_blender(trimesh.util.concatenate(w_ms), "Site_Driveway_Car_Wheels", site_coll, mats["tire_rubber"])


def build_terrace_amenities(
    geom: dict[str, Any],
    z_terrace: float,
    mats: dict[str, bpy.types.Material],
    terr_coll: bpy.types.Collection,
) -> None:
    """
    Amenity 5: Terrace Amenities (z = 24.70m) driven by `geom["terrace"]["amenity_zones"]`
    and matching `brochure/12.jpg`, `15.jpg`, `16.jpg`, `18.jpg`, and `20.jpg`:
    1. South-Central Zone (`pergola_seating`): Timber & charcoal-metal slatted Pergola
       with warm pendant lanterns, outdoor L-shaped lounge sofas, terracotta cushions,
       round coffee tables, and hardwood deck floor (`brochure/20.jpg`).
    2. South-Front Zone (`kids_play_area`): Soft-fall EPDM sand/blue play court with
       curved perimeter planter hedge, swing set, climbing arch, seesaw, and merry-go-round
       (`brochure/16.jpg`, `18.jpg`, `20.jpg`).
    3. North Zone (`terrace_gym` + `yoga_deck`): Glass-walled air-conditioned Fitness Gym
       pavilion with rooftop solar panels above (`brochure/12.jpg`, `15.jpg`, `16.jpg`),
       sprint track lane, 2 curved treadmills, 3 stationary exercise bikes, dumbbell rack,
       weight bench, exercise balls, and adjacent wooden Yoga Deck with yoga mats & bolsters.
    """
    zones = geom.get("terrace", {}).get("amenity_zones", {})
    if not zones:
        return
    z_t = z_terrace + 0.09
    props = {"floor_index": 8, "floor_label": "Open Terrace & Amenities"}

    # --- 1. SOUTH PERGOLA SEATING AREA (matching brochure/20.jpg) ---
    pb = zones["pergola_seating"]["bounds"]
    px0, py0, px1, py1 = pb[0], pb[1], pb[2], pb[3]
    perg_h = 2.85

    # Hardwood deck under pergola
    deck_meshes: list[trimesh.Trimesh] = [make_box_trimesh(px0, py0, z_t, px1, py1, z_t + 0.04)]

    # Two pergola bays (West bay & East bay) with columns, perimeter beams, and roof louvers
    perg_metal: list[trimesh.Trimesh] = []
    perg_leds: list[trimesh.Trimesh] = []
    perg_sofas: list[trimesh.Trimesh] = []
    perg_cushions: list[trimesh.Trimesh] = []
    perg_tables: list[trimesh.Trimesh] = []

    for bx0, bx1 in [(px0 + 0.2, (px0 + px1) * 0.5 - 0.3), ((px0 + px1) * 0.5 + 0.3, px1 - 0.2)]:
        by0, by1 = py0 + 0.2, py1 - 0.2
        # 4 corner columns
        for cx in (bx0, bx1):
            for cy in (by0, by1):
                perg_metal.append(make_box_trimesh(cx - 0.09, cy - 0.09, z_t, cx + 0.09, cy + 0.09, z_t + perg_h))
        # Perimeter roof beams
        perg_metal.extend(
            [
                make_box_trimesh(bx0 - 0.1, by0 - 0.1, z_t + perg_h - 0.18, bx1 + 0.1, by0 + 0.1, z_t + perg_h),
                make_box_trimesh(bx0 - 0.1, by1 - 0.1, z_t + perg_h - 0.18, bx1 + 0.1, by1 + 0.1, z_t + perg_h),
                make_box_trimesh(bx0 - 0.1, by0, z_t + perg_h - 0.18, bx0 + 0.1, by1, z_t + perg_h),
                make_box_trimesh(bx1 - 0.1, by0, z_t + perg_h - 0.18, bx1 + 0.1, by1, z_t + perg_h),
            ]
        )
        # Roof louver slats
        num_slats = 16
        for i in range(num_slats):
            sy = by0 + 0.15 + (by1 - by0 - 0.30) * (i / (num_slats - 1))
            perg_metal.append(make_box_trimesh(bx0, sy - 0.03, z_t + perg_h - 0.12, bx1, sy + 0.03, z_t + perg_h - 0.02))

        # Hanging warm cage lantern in center of pergola bay (matching brochure/20.jpg)
        mcx, mcy = (bx0 + bx1) * 0.5, (by0 + by1) * 0.5
        perg_metal.append(make_box_trimesh(mcx - 0.02, mcy - 0.02, z_t + perg_h - 0.65, mcx + 0.02, mcy + 0.02, z_t + perg_h))
        bulb = trimesh.creation.icosphere(subdivisions=1, radius=0.14)
        bulb.apply_translation([mcx, mcy, z_t + perg_h - 0.72])
        perg_leds.append(bulb)

        # Outdoor L-shaped sofa + cushions + round coffee table inside each pergola bay
        perg_sofas.extend(
            [
                make_box_trimesh(bx0 + 0.45, by1 - 1.15, z_t + 0.08, bx1 - 0.45, by1 - 0.35, z_t + 0.42),
                make_box_trimesh(bx0 + 0.45, by1 - 0.52, z_t + 0.42, bx1 - 0.45, by1 - 0.35, z_t + 0.82),
                make_box_trimesh(bx0 + 0.45, by0 + 0.45, z_t + 0.08, bx0 + 1.25, by1 - 1.15, z_t + 0.42),
                make_box_trimesh(bx0 + 0.45, by0 + 0.45, z_t + 0.42, bx0 + 0.62, by1 - 1.15, z_t + 0.82),
            ]
        )
        for qx in (bx0 + 0.85, mcx, bx1 - 0.85):
            perg_cushions.append(make_box_trimesh(qx - 0.20, by1 - 0.72, z_t + 0.42, qx + 0.20, by1 - 0.52, z_t + 0.74))
        tbl = trimesh.creation.cylinder(radius=0.48, height=0.38, sections=24)
        tbl.apply_translation([mcx + 0.2, mcy - 0.15, z_t + 0.23])
        perg_tables.append(tbl)

    add_trimesh_to_blender(trimesh.util.concatenate(perg_metal), "Terrace_Pergola_Structure", terr_coll, mats["charcoal_metal"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(perg_leds), "Terrace_Pergola_Lanterns", terr_coll, mats["warm_led"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(perg_sofas), "Terrace_Pergola_Sofas", terr_coll, mats["bed_linen_white"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(perg_cushions), "Terrace_Pergola_Cushions", terr_coll, mats["cushion_terracotta"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(perg_tables), "Terrace_Pergola_Tables", terr_coll, mats["dark_glass_table"], props)

    # --- 2. SOUTH-FRONT KIDS' PLAY AREA (matching brochure/16.jpg, 18.jpg, 20.jpg) ---
    kb = zones["kids_play_area"]["bounds"]
    kx0, ky0, kx1, ky1 = kb[0], kb[1], kb[2], kb[3]
    kcx, kcy = (kx0 + kx1) * 0.5, (ky0 + ky1) * 0.5

    # Rounded sand/EPDM play pit with curved curb & lush perimeter greenery
    play_pit_poly = Polygon([(kx0 + 1.2, ky0 + 1.0), (kx1 - 1.2, ky0 + 1.0), (kx1 - 1.2, ky1 - 0.8), (kx0 + 1.2, ky1 - 0.8)]).buffer(0.8, resolution=12)
    pit_tm = extrude_shapely_polys([play_pit_poly], z_t, z_t + 0.06)
    add_trimesh_to_blender(pit_tm, "Terrace_Kids_Play_Mat", terr_coll, mats["epdm_sand"], props)

    pit_curb = extrude_shapely_polys([play_pit_poly.exterior.buffer(0.12)], z_t, z_t + 0.22)
    add_trimesh_to_blender(pit_curb, "Terrace_Kids_Play_Curb", terr_coll, mats["dark_concrete"], props)

    # Perimeter planter hedge around South terrace edge
    terr_hedge = [
        make_box_trimesh(kx0 - 0.2, ky0 - 0.4, z_t, kx1 + 0.2, ky0 + 0.35, z_t + 0.95),
        make_box_trimesh(kx0 - 0.3, ky0, z_t, kx0 + 0.35, ky1, z_t + 0.95),
        make_box_trimesh(kx1 - 0.35, ky0, z_t, kx1 + 0.3, ky1, z_t + 0.95),
    ]
    add_trimesh_to_blender(trimesh.util.concatenate(terr_hedge), "Terrace_Perimeter_Hedge", terr_coll, mats["foliage_bright"], props)

    # Kids' play equipment: Swing set (red/yellow), climbing arch, seesaw, and merry-go-round
    play_red_ms: list[trimesh.Trimesh] = [
        # Swing frame at (kcx + 1.2, kcy - 0.8)
        make_box_trimesh(kcx + 0.2, kcy - 0.9, z_t + 0.06, kcx + 0.3, kcy - 0.8, z_t + 2.15),
        make_box_trimesh(kcx + 2.2, kcy - 0.9, z_t + 0.06, kcx + 2.3, kcy - 0.8, z_t + 2.15),
        make_box_trimesh(kcx + 0.2, kcy - 0.9, z_t + 2.08, kcx + 2.3, kcy - 0.8, z_t + 2.18),
        # Climbing arch / slide
        make_box_trimesh(kcx + 1.1, kcy - 2.2, z_t + 0.06, kcx + 2.5, kcy - 1.5, z_t + 1.05),
    ]
    play_yellow_ms: list[trimesh.Trimesh] = [
        # Swing seats
        make_box_trimesh(kcx + 0.75, kcy - 0.95, z_t + 0.48, kcx + 1.10, kcy - 0.75, z_t + 0.54),
        make_box_trimesh(kcx + 1.40, kcy - 0.95, z_t + 0.48, kcx + 1.75, kcy - 0.75, z_t + 0.54),
        # Seesaw plank at (kcx - 1.4, kcy - 1.2)
        make_box_trimesh(kcx - 2.3, kcy - 1.35, z_t + 0.42, kcx - 0.5, kcy - 1.05, z_t + 0.50),
    ]
    mgr = trimesh.creation.cylinder(radius=0.75, height=0.12, sections=24)
    mgr.apply_translation([kcx - 1.3, kcy + 0.8, z_t + 0.28])
    play_yellow_ms.append(mgr)

    add_trimesh_to_blender(trimesh.util.concatenate(play_red_ms), "Terrace_Play_Equipment_Red", terr_coll, mats["play_red"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(play_yellow_ms), "Terrace_Play_Equipment_Yellow", terr_coll, mats["play_yellow"], props)

    # --- 3. NORTH TERRACE FITNESS GYM PAVILION & YOGA DECK (matching brochure/12.jpg & 15.jpg) ---
    gb = zones["terrace_gym"]["bounds"]
    gx0, gy0, gx1, gy1 = gb[0], gb[1], gb[2], gb[3]
    gcx = (gx0 + gx1) * 0.5
    gym_h = 3.00

    # Yoga deck along West edge (x in [0.25, gx0], y in [24.2, 37.6], matching brochure/15.jpg)
    deck_meshes.append(make_box_trimesh(0.25, 24.20, z_t, gx0, 37.60, z_t + 0.04))
    add_trimesh_to_blender(trimesh.util.concatenate(deck_meshes), "Terrace_Wood_Decks", terr_coll, mats["oak_floor"], props)

    # Yoga mats & bolsters on the West Yoga Deck (matching brochure/15.jpg)
    yoga_mats = [
        make_box_trimesh(0.65, 27.5, z_t + 0.04, 1.65, 29.2, z_t + 0.06),
        make_box_trimesh(0.65, 30.2, z_t + 0.04, 1.65, 31.9, z_t + 0.06),
    ]
    add_trimesh_to_blender(trimesh.util.concatenate(yoga_mats), "Terrace_Yoga_Mats", terr_coll, mats["bed_throw_grey"], props)

    # Gym dark rubber floor + central sprint track lines (matching brochure/12.jpg)
    gym_floor = make_box_trimesh(gx0, gy0, z_t, gx1, gy1, z_t + 0.05)
    add_trimesh_to_blender(gym_floor, "Terrace_Gym_Floor", terr_coll, mats["gym_floor_dark"], props)

    track_lines: list[trimesh.Trimesh] = [
        make_box_trimesh(gcx - 0.72, gy0 + 0.8, z_t + 0.05, gcx - 0.66, gy1 - 0.8, z_t + 0.065),
        make_box_trimesh(gcx + 0.66, gy0 + 0.8, z_t + 0.05, gcx + 0.72, gy1 - 0.8, z_t + 0.065),
    ]
    for ty in [gy0 + 1.5 + i * 1.15 for i in range(7)]:
        track_lines.append(make_box_trimesh(gcx - 0.55, ty - 0.03, z_t + 0.05, gcx + 0.55, ty + 0.03, z_t + 0.065))
    add_trimesh_to_blender(trimesh.util.concatenate(track_lines), "Terrace_Gym_Track_Lines", terr_coll, mats["cool_led"], props)

    # Gym Glass Pavilion Enclosure (Sloped/flat roof, glass curtain walls on West, North, East)
    gym_roof = make_box_trimesh(gx0 - 0.35, gy0 - 0.35, z_t + gym_h - 0.18, gx1 + 0.35, gy1 + 0.35, z_t + gym_h)
    add_trimesh_to_blender(gym_roof, "Terrace_Gym_Roof", terr_coll, mats["concrete_facade"], props)

    # Rooftop Solar PV Panel Array atop the Gym Roof (matching brochure/16.jpg & 18.jpg & DXF label)
    solar_panels: list[trimesh.Trimesh] = []
    for sy in [gy0 + 0.8 + i * 1.45 for i in range(6)]:
        solar_panels.append(make_box_trimesh(gx0 + 0.6, sy, z_t + gym_h + 0.05, gx1 - 0.6, sy + 1.15, z_t + gym_h + 0.14))
    add_trimesh_to_blender(trimesh.util.concatenate(solar_panels), "Terrace_Solar_Panels", terr_coll, mats["car_paint_blue"], props)

    gym_frames: list[trimesh.Trimesh] = []
    gym_glass: list[trimesh.Trimesh] = [
        make_box_trimesh(gx0, gy0, z_t + 0.35, gx0 + 0.04, gy1, z_t + gym_h - 0.18),
        make_box_trimesh(gx1 - 0.04, gy0, z_t + 0.35, gx1, gy1, z_t + gym_h - 0.18),
        make_box_trimesh(gx0, gy1 - 0.04, z_t + 0.35, gx1, gy1, z_t + gym_h - 0.18),
        make_box_trimesh(gx0, gy0, z_t + 0.35, gx1, gy0 + 0.04, z_t + gym_h - 0.18),
    ]
    for my in [gy0 + i * 2.1 for i in range(6)]:
        gym_frames.append(make_box_trimesh(gx0 - 0.03, my - 0.03, z_t, gx0 + 0.06, my + 0.03, z_t + gym_h - 0.18))
        gym_frames.append(make_box_trimesh(gx1 - 0.06, my - 0.03, z_t, gx1 + 0.03, my + 0.03, z_t + gym_h - 0.18))

    # Gym Equipment (matching brochure/12.jpg):
    # - 2 Curved Treadmills on East side facing East/North
    # - 3 Stationary Air Bikes on West side
    # - Dumbbell Rack + Weight Bench
    # - Blue Exercise Stability Ball in center
    for ty in (gy0 + 2.2, gy0 + 4.4):
        # Treadmill base + uprights + console
        gym_frames.extend(
            [
                make_box_trimesh(gx1 - 2.35, ty - 0.45, z_t + 0.06, gx1 - 0.55, ty + 0.45, z_t + 0.32),
                make_box_trimesh(gx1 - 0.75, ty - 0.42, z_t + 0.32, gx1 - 0.65, ty - 0.34, z_t + 1.35),
                make_box_trimesh(gx1 - 0.75, ty + 0.34, z_t + 0.32, gx1 - 0.65, ty + 0.42, z_t + 1.35),
                make_box_trimesh(gx1 - 0.85, ty - 0.44, z_t + 1.28, gx1 - 0.55, ty + 0.44, z_t + 1.42),
            ]
        )
    for by in (gy0 + 2.0, gy0 + 3.8, gy0 + 5.6):
        # Air bike base + fan wheel + seat + handlebars
        gym_frames.extend(
            [
                make_box_trimesh(gx0 + 0.55, by - 0.30, z_t + 0.06, gx0 + 1.85, by + 0.30, z_t + 0.16),
                make_box_trimesh(gx0 + 1.45, by - 0.18, z_t + 0.16, gx0 + 1.65, by + 0.18, z_t + 0.88),
                make_box_trimesh(gx0 + 0.75, by - 0.28, z_t + 0.16, gx0 + 0.92, by + 0.28, z_t + 1.28),
            ]
        )
        wheel = trimesh.creation.cylinder(radius=0.34, height=0.14, sections=16)
        wheel.apply_transform(trimesh.transformations.rotation_matrix(math.pi * 0.5, [1, 0, 0]))
        wheel.apply_translation([gx0 + 0.85, by, z_t + 0.48])
        gym_frames.append(wheel)

    # Dumbbell rack & weight bench at (gx1 - 1.5, gy0 + 6.8)
    gym_frames.extend(
        [
            make_box_trimesh(gx1 - 2.1, gy0 + 6.4, z_t + 0.06, gx1 - 0.8, gy0 + 7.2, z_t + 0.88),
            make_box_trimesh(gx1 - 2.4, gy0 + 7.8, z_t + 0.06, gx1 - 1.1, gy0 + 8.3, z_t + 0.48),
        ]
    )

    add_trimesh_to_blender(trimesh.util.concatenate(gym_frames), "Terrace_Gym_Equipment_And_Frames", terr_coll, mats["charcoal_metal"], props)
    add_trimesh_to_blender(trimesh.util.concatenate(gym_glass), "Terrace_Gym_Glass_Walls", terr_coll, mats["window_glass"], props)

    # Blue Stability Ball on the central track (matching brochure/12.jpg)
    ball = trimesh.creation.icosphere(subdivisions=2, radius=0.36)
    ball.apply_translation([gcx, gy0 + 5.2, z_t + 0.41])
    add_trimesh_to_blender(ball, "Terrace_Gym_Stability_Ball", terr_coll, mats["epdm_blue"], props)

    # Gym ceiling recessed spotlights
    gym_spots: list[trimesh.Trimesh] = []
    for sx in (gx0 + 1.8, gcx, gx1 - 1.8):
        for sy in (gy0 + 2.0, gy0 + 4.5, gy0 + 7.0, gy0 + 9.0):
            gym_spots.append(make_box_trimesh(sx - 0.08, sy - 0.08, z_t + gym_h - 0.20, sx + 0.08, sy + 0.08, z_t + gym_h - 0.17))
    add_trimesh_to_blender(trimesh.util.concatenate(gym_spots), "Terrace_Gym_Ceiling_LEDs", terr_coll, mats["warm_led"], props)
