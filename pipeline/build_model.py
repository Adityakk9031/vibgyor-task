"""
Stage 2: Build the 3D model (.blend) from outputs/extracted_geometry.json.

Generates the entire Vibgyor residential tower, architectural facade detailing
(curved corner slab bands, vertical charcoal metal louver fins, terracotta/wood
planter boxes with greenery, glazed windows & sliding doors with dark mullions,
balcony glass railings, wooden balcony soffits, terrace parapets, stair cabin
and overhead water tank), the immediate plot (angled 18m main road with median
shrubs and lane markings, compound wall with glowing 'VIBGYOR' signage, wooden
slat entrance canopy & gate, stilt parking driveway, basement ramp, and 25 site
trees), and a complete Type A interior on Floor 1 (walls, doors, marble floor,
coffered ceiling with cove lighting, L-shaped sofa, coffee tables, TV console,
fluted green wall panelling, dining table & chairs, kitchen island & counters)
for the 360-degree drawing room panorama bonus.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import bpy
import bmesh
from mathutils import Vector
import trimesh
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union


# =============================================================================
# Geometry & Mesh Helpers
# =============================================================================


def get_or_create_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(coll)
    else:
        parent.children.link(coll)
    return coll


def add_trimesh_to_blender(
    tm: trimesh.Trimesh,
    name: str,
    collection: bpy.types.Collection,
    material: bpy.types.Material | None = None,
    custom_props: dict[str, Any] | None = None,
) -> bpy.types.Object | None:
    if tm is None or len(tm.vertices) == 0 or len(tm.faces) == 0:
        return None
    mesh = bpy.data.meshes.new(name)
    verts = [(float(v[0]), float(v[1]), float(v[2])) for v in tm.vertices]
    faces = [(int(f[0]), int(f[1]), int(f[2])) for f in tm.faces]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # Add cube-projected UVs so PBR textures and glTF export have real-world metre scale
    if not mesh.uv_layers:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            n = poly.normal
            ax_x, ax_y = (0, 1) if abs(n.z) > 0.7 else ((0, 2) if abs(n.y) > 0.7 else (1, 2))
            for loop_idx in poly.loop_indices:
                v = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                uv_layer.data[loop_idx].uv = (v[ax_x] * 0.5, v[ax_y] * 0.5)

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    if custom_props:
        for k, v in custom_props.items():
            obj[k] = v
    return obj


def extrude_shapely_polys(
    polys: list[Polygon],
    z_bottom: float,
    z_top: float,
) -> trimesh.Trimesh | None:
    height = z_top - z_bottom
    if height <= 1e-4 or not polys:
        return None
    meshes: list[trimesh.Trimesh] = []
    for p in polys:
        if not p.is_valid:
            p = p.buffer(0)
        geoms = [p] if isinstance(p, Polygon) else (list(p.geoms) if isinstance(p, MultiPolygon) else [])
        for g in geoms:
            if g.area <= 1e-4:
                continue
            try:
                m = trimesh.creation.extrude_polygon(g, height=height)
                m.apply_translation([0.0, 0.0, z_bottom])
                meshes.append(m)
            except Exception:
                pass
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


def make_box_trimesh(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> trimesh.Trimesh:
    extents = [max(1e-4, abs(x1 - x0)), max(1e-4, abs(y1 - y0)), max(1e-4, abs(z1 - z0))]
    m = trimesh.creation.box(extents=extents)
    m.apply_translation([(x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5])
    return m


def make_oriented_box(
    p1: tuple[float, float],
    p2: tuple[float, float],
    thickness: float,
    z0: float,
    z1: float,
) -> trimesh.Trimesh | None:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length <= 1e-4 or z1 <= z0:
        return None
    angle = math.atan2(dy, dx)
    m = trimesh.creation.box(extents=[length, thickness, z1 - z0])
    rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    m.apply_transform(rot)
    m.apply_translation([(p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5, (z0 + z1) * 0.5])
    return m


# =============================================================================
# Procedural PBR Materials (Works in both Cycles and glTF Export)
# =============================================================================


def create_pbr_material(
    name: str,
    base_color: tuple[float, float, float],
    roughness: float = 0.6,
    metallic: float = 0.0,
    transmission: float = 0.0,
    alpha: float = 1.0,
    emission_color: tuple[float, float, float] | None = None,
    emission_strength: float = 0.0,
    bump_scale: float = 0.0,
    bump_strength: float = 0.0,
) -> bpy.types.Material:
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    if alpha < 1.0 or transmission > 0.0:
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value = (base_color[0], base_color[1], base_color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if transmission > 0.0:
        for t_name in ("Transmission Weight", "Transmission"):
            if t_name in bsdf.inputs:
                bsdf.inputs[t_name].default_value = transmission
                break
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.52

    if emission_color is not None and emission_strength > 0.0:
        for e_col_name in ("Emission Color", "Emission"):
            if e_col_name in bsdf.inputs:
                bsdf.inputs[e_col_name].default_value = (
                    emission_color[0],
                    emission_color[1],
                    emission_color[2],
                    1.0,
                )
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength

    # Add procedural noise bump for realistic surface micro-detail in Cycles renders
    if bump_strength > 0.0 and bump_scale > 0.0:
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        noise = nodes.new(type="ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 8.0
        noise.inputs["Roughness"].default_value = 0.65
        bump = nodes.new(type="ShaderNodeBump")
        bump.inputs["Strength"].default_value = bump_strength
        bump.inputs["Distance"].default_value = 0.02
        links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def create_all_materials() -> dict[str, bpy.types.Material]:
    return {
        "concrete_facade": create_pbr_material(
            "Mat_Concrete_Facade",
            base_color=(0.73, 0.74, 0.75),
            roughness=0.68,
            bump_scale=18.0,
            bump_strength=0.18,
        ),
        "wall_stucco": create_pbr_material(
            "Mat_Wall_Stucco",
            base_color=(0.82, 0.81, 0.79),
            roughness=0.75,
            bump_scale=30.0,
            bump_strength=0.10,
        ),
        "dark_concrete": create_pbr_material(
            "Mat_Dark_Concrete",
            base_color=(0.20, 0.21, 0.23),
            roughness=0.72,
            bump_scale=15.0,
            bump_strength=0.20,
        ),
        "charcoal_metal": create_pbr_material(
            "Mat_Charcoal_Metal",
            base_color=(0.13, 0.14, 0.15),
            roughness=0.32,
            metallic=0.85,
        ),
        "planter_terracotta": create_pbr_material(
            "Mat_Planter_Terracotta",
            base_color=(0.66, 0.39, 0.21),
            roughness=0.58,
            bump_scale=12.0,
            bump_strength=0.14,
        ),
        "wood_slats": create_pbr_material(
            "Mat_Wood_Slats",
            base_color=(0.52, 0.31, 0.16),
            roughness=0.45,
            bump_scale=20.0,
            bump_strength=0.12,
        ),
        "wood_soffit": create_pbr_material(
            "Mat_Wood_Soffit",
            base_color=(0.58, 0.37, 0.20),
            roughness=0.48,
        ),
        "window_glass": create_pbr_material(
            "Mat_Window_Glass",
            base_color=(0.75, 0.87, 0.94),
            roughness=0.04,
            metallic=0.10,
            transmission=0.82,
            alpha=0.38,
        ),
        "railing_glass": create_pbr_material(
            "Mat_Railing_Glass",
            base_color=(0.82, 0.91, 0.93),
            roughness=0.05,
            metallic=0.05,
            transmission=0.88,
            alpha=0.32,
        ),
        "asphalt_road": create_pbr_material(
            "Mat_Asphalt_Road",
            base_color=(0.17, 0.17, 0.18),
            roughness=0.86,
            bump_scale=45.0,
            bump_strength=0.25,
        ),
        "road_marking": create_pbr_material(
            "Mat_Road_Marking",
            base_color=(0.88, 0.88, 0.86),
            roughness=0.50,
        ),
        "paver_driveway": create_pbr_material(
            "Mat_Paver_Driveway",
            base_color=(0.52, 0.50, 0.48),
            roughness=0.76,
            bump_scale=35.0,
            bump_strength=0.22,
        ),
        "tree_trunk": create_pbr_material(
            "Mat_Tree_Trunk",
            base_color=(0.30, 0.21, 0.14),
            roughness=0.88,
        ),
        "foliage_green": create_pbr_material(
            "Mat_Foliage_Green",
            base_color=(0.17, 0.37, 0.12),
            roughness=0.65,
            bump_scale=25.0,
            bump_strength=0.20,
        ),
        "foliage_bright": create_pbr_material(
            "Mat_Foliage_Bright",
            base_color=(0.24, 0.46, 0.15),
            roughness=0.60,
        ),
        "warm_led": create_pbr_material(
            "Mat_Warm_LED",
            base_color=(1.0, 0.86, 0.62),
            roughness=0.20,
            emission_color=(1.0, 0.82, 0.52),
            emission_strength=14.0,
        ),
        "sign_glow": create_pbr_material(
            "Mat_Sign_Glow",
            base_color=(1.0, 0.92, 0.76),
            roughness=0.20,
            emission_color=(1.0, 0.88, 0.68),
            emission_strength=22.0,
        ),
        # Interior materials for Type A Drawing Room (Bonus 360 Panorama)
        "marble_floor": create_pbr_material(
            "Mat_Marble_Floor",
            base_color=(0.91, 0.90, 0.88),
            roughness=0.14,
            bump_scale=6.0,
            bump_strength=0.03,
        ),
        "interior_wall": create_pbr_material(
            "Mat_Interior_Wall",
            base_color=(0.93, 0.91, 0.88),
            roughness=0.70,
        ),
        "sage_panelling": create_pbr_material(
            "Mat_Sage_Panelling",
            base_color=(0.32, 0.39, 0.30),
            roughness=0.52,
        ),
        "sofa_fabric": create_pbr_material(
            "Mat_Sofa_Fabric",
            base_color=(0.38, 0.34, 0.31),
            roughness=0.82,
            bump_scale=60.0,
            bump_strength=0.12,
        ),
        "cushion_terracotta": create_pbr_material(
            "Mat_Cushion_Terracotta",
            base_color=(0.56, 0.30, 0.20),
            roughness=0.78,
        ),
        "brass_gold": create_pbr_material(
            "Mat_Brass_Gold",
            base_color=(0.82, 0.66, 0.36),
            roughness=0.24,
            metallic=0.92,
        ),
        "dark_glass_table": create_pbr_material(
            "Mat_Dark_Glass_Table",
            base_color=(0.10, 0.11, 0.12),
            roughness=0.06,
            metallic=0.20,
        ),
        "rug_fabric": create_pbr_material(
            "Mat_Rug_Fabric",
            base_color=(0.46, 0.43, 0.40),
            roughness=0.92,
            bump_scale=80.0,
            bump_strength=0.18,
        ),
    }


# =============================================================================
# Window, Sliding Door, Railing, and Facade Fin Builders
# =============================================================================


def build_window_or_door_assembly(
    w_dict: dict[str, Any],
    z_floor: float,
) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Returns (frame_meshes, glass_meshes) for a window or sliding door opening."""
    b = w_dict["bounds"]
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
    z0 = z_floor + float(w_dict.get("sill_height", 0.90))
    z1 = z_floor + float(w_dict.get("lintel_height", 2.12))

    frames: list[trimesh.Trimesh] = []
    glasses: list[trimesh.Trimesh] = []

    ft = 0.045  # frame thickness 4.5cm
    w = x1 - x0
    d = y1 - y0
    is_horiz = w >= d

    # Outer perimeter frame
    frames.append(make_box_trimesh(x0, y0, z0, x1, y1, z0 + ft))  # bottom sill frame
    frames.append(make_box_trimesh(x0, y0, z1 - ft, x1, y1, z1))  # top head frame

    if is_horiz:
        frames.append(make_box_trimesh(x0, y0, z0, x0 + ft, y1, z1))
        frames.append(make_box_trimesh(x1 - ft, y0, z0, x1, y1, z1))
        num_panels = 3 if w > 2.0 else (2 if w > 0.9 else 1)
        for i in range(1, num_panels):
            mx = x0 + (w * i) / num_panels
            frames.append(make_box_trimesh(mx - ft * 0.4, y0, z0, mx + ft * 0.4, y1, z1))
        cy = (y0 + y1) * 0.5
        glasses.append(make_box_trimesh(x0 + ft, cy - 0.01, z0 + ft, x1 - ft, cy + 0.01, z1 - ft))
    else:
        frames.append(make_box_trimesh(x0, y0, z0, x1, y0 + ft, z1))
        frames.append(make_box_trimesh(x0, y1 - ft, z0, x1, y1, z1))
        num_panels = 3 if d > 2.0 else (2 if d > 0.9 else 1)
        for i in range(1, num_panels):
            my = y0 + (d * i) / num_panels
            frames.append(make_box_trimesh(x0, my - ft * 0.4, z0, x1, my + ft * 0.4, z1))
        cx = (x0 + x1) * 0.5
        glasses.append(make_box_trimesh(cx - 0.01, y0 + ft, z0 + ft, cx + 0.01, y1 - ft, z1 - ft))

    return frames, glasses


def build_facade_details_for_floor(
    slab_poly: Polygon,
    proj_polys: list[Polygon],
    railings: list[dict[str, Any]],
    z_floor: float,
    floor_h: float,
    slab_t: float,
    planter_h: float,
) -> dict[str, list[trimesh.Trimesh]]:
    """
    Generates the signature architectural facade elements seen in brochure/exterior.jpg:
    - Extended continuous slab band (slab + exterior projections) with rounded corners
    - Front angled balcony terracotta/wood planter boxes + green foliage hedge
    - Vertical charcoal metal louver fins spanning floor-to-floor on the front & side facades
    - Glass balcony railings with top metal handrails
    - Recessed ceiling LED downlights on balcony soffits
    """
    out: dict[str, list[trimesh.Trimesh]] = {
        "slab_band": [],
        "planter_box": [],
        "planter_foliage": [],
        "metal_fins": [],
        "railing_glass": [],
        "LED_spots": [],
        "wood_soffit": [],
    }

    # 1. Continuous architectural slab band (union of structural slab + 0.60m chajja projections)
    full_slab = unary_union([slab_poly] + proj_polys)
    # Smooth corners slightly (buffer out & in by 0.25m) to match rounded corner band in exterior.jpg
    rounded_band = full_slab.buffer(0.18, resolution=8).buffer(-0.18, resolution=8)
    band_polys = [rounded_band] if isinstance(rounded_band, Polygon) else list(rounded_band.geoms)
    sm = extrude_shapely_polys(band_polys, z_floor - slab_t, z_floor + 0.06)
    if sm is not None:
        out["slab_band"].append(sm)

    # Subtle horizontal architectural groove/band at lintel height on exterior perimeter
    lintel_ring = rounded_band.exterior.buffer(0.03, resolution=4)
    lm = extrude_shapely_polys([lintel_ring], z_floor + 2.12, z_floor + 2.24)
    if lm is not None:
        out["slab_band"].append(lm)

    # 2. Front angled facade line: from (1.675, 4.936) to (13.120, 0.000)
    # Outward unit normal of front angled line is (sin, -cos) = (-0.396, -0.918)
    fx0, fy0 = 1.675, 4.936
    fx1, fy1 = 13.120, 0.000
    f_dx, f_dy = fx1 - fx0, fy1 - fy0
    f_len = math.hypot(f_dx, f_dy)
    ux, uy = f_dx / f_len, f_dy / f_len  # along front facade (+x, -y)
    nx, ny = -0.3962, -0.9182  # outward normal toward main road

    def front_pt(dist_along: float, offset_out: float = 0.0) -> tuple[float, float]:
        return (
            fx0 + ux * dist_along + nx * offset_out,
            fy0 + uy * dist_along + ny * offset_out,
        )

    # Two front balcony planter zones from elevation (bay 1: s in [1.65, 5.45], bay 2: s in [7.75, 11.85])
    for s_start, s_end in [(1.65, 5.50), (7.75, 11.85)]:
        p1 = front_pt(s_start, offset_out=0.35)
        p2 = front_pt(s_end, offset_out=0.35)
        pb = make_oriented_box(p1, p2, thickness=0.32, z0=z_floor + 0.04, z1=z_floor + planter_h + 0.04)
        if pb is not None:
            out["planter_box"].append(pb)
        # Green bush/grass strip atop the planter box
        fg = make_oriented_box(
            p1, p2, thickness=0.26, z0=z_floor + planter_h + 0.02, z1=z_floor + planter_h + 0.36
        )
        if fg is not None:
            out["planter_foliage"].append(fg)
        # Wooden soffit on underside of the upper slab above the balcony
        sp1 = front_pt(s_start, offset_out=0.10)
        sp2 = front_pt(s_end, offset_out=0.10)
        soffit = make_oriented_box(
            sp1, sp2, thickness=0.95, z0=z_floor + floor_h - slab_t - 0.02, z1=z_floor + floor_h - slab_t
        )
        if soffit is not None:
            out["wood_soffit"].append(soffit)

        # Warm LED soffit spotlights
        for frac in (0.25, 0.50, 0.75):
            lx, ly = front_pt(s_start + (s_end - s_start) * frac, offset_out=0.25)
            spot = make_box_trimesh(
                lx - 0.06, ly - 0.06, z_floor + floor_h - slab_t - 0.03,
                lx + 0.06, ly + 0.06, z_floor + floor_h - slab_t + 0.01,
            )
            out["LED_spots"].append(spot)

    # 3. Vertical Charcoal Metal Louver Fins on the front angled facade (3 clusters matching exterior.jpg)
    # Cluster 1 (left corner): s in [0.35, 1.55] (6 fins)
    # Cluster 2 (center pier): s in [5.60, 7.65] (9 fins)
    # Cluster 3 (right pier):  s in [11.90, 12.40] (3 fins)
    fin_clusters = [
        [0.35 + i * 0.22 for i in range(6)],
        [5.65 + i * 0.23 for i in range(9)],
        [11.92 + i * 0.22 for i in range(3)],
    ]
    for cluster in fin_clusters:
        for s_pos in cluster:
            fp = front_pt(s_pos, offset_out=0.48)
            p_in = front_pt(s_pos, offset_out=0.30)
            fin = make_oriented_box(
                p_in, fp, thickness=0.06, z0=z_floor + 0.06, z1=z_floor + floor_h - slab_t
            )
            if fin is not None:
                out["metal_fins"].append(fin)
        # Small warm LED accent dots at bottom & top of fin clusters (visible in dusk render 7.jpg)
        for s_pos in (cluster[0], cluster[-1]):
            lx, ly = front_pt(s_pos, offset_out=0.45)
            out["LED_spots"].append(
                make_box_trimesh(lx - 0.04, ly - 0.04, z_floor + 0.06, lx + 0.04, ly + 0.04, z_floor + 0.11)
            )

    # Side louvered utility screen panels on West facade (x = 1.12, y in [6.0, 8.3] and [13.5, 15.3])
    for y_start, y_end in [(5.2, 8.3), (15.4, 18.8)]:
        panel = make_box_trimesh(
            1.10, y_start, z_floor + 0.06, 1.16, y_end, z_floor + floor_h - slab_t
        )
        out["metal_fins"].append(panel)

    # 4. Side & Rear Balconies (East balcony at x=13.12, y=[11.89, 16.76]; West balcony at x=0.0, y=[24.71, 29.96])
    # Add planter box + glass railing + metal fins
    for bx, by0, by1, out_dir in [(13.45, 11.89, 16.76, 1.0), (-0.35, 24.71, 29.96, -1.0)]:
        out["planter_box"].append(
            make_box_trimesh(bx - 0.15, by0, z_floor + 0.04, bx + 0.15, by1, z_floor + planter_h + 0.04)
        )
        out["planter_foliage"].append(
            make_box_trimesh(
                bx - 0.12, by0 + 0.1, z_floor + planter_h + 0.02,
                bx + 0.12, by1 - 0.1, z_floor + planter_h + 0.34,
            )
        )
        out["railing_glass"].append(
            make_box_trimesh(
                bx - 0.02, by0, z_floor + planter_h + 0.04,
                bx + 0.02, by1, z_floor + 1.15,
            )
        )
        out["metal_fins"].append(
            make_box_trimesh(
                bx - 0.04, by0, z_floor + 1.12,
                bx + 0.04, by1, z_floor + 1.17,
            )
        )

    # Also build glass railings for all extracted railing polygons on g-ele01
    for r_dict in railings:
        r_poly = Polygon(r_dict["polygon"])
        gm = extrude_shapely_polys([r_poly], z_floor + planter_h, z_floor + 1.12)
        if gm is not None:
            out["railing_glass"].append(gm)
        hm = extrude_shapely_polys([r_poly.buffer(0.015)], z_floor + 1.12, z_floor + 1.16)
        if hm is not None:
            out["metal_fins"].append(hm)

    return out


# =============================================================================
# Site, Plot, Entrance Canopy, VIBGYOR Signage, and Trees Builder
# =============================================================================


def build_site_and_plot(
    geom: dict[str, Any],
    mats: dict[str, bpy.types.Material],
    site_coll: bpy.types.Collection,
) -> None:
    site = geom["site"]
    heights = geom["heights"]

    # 1. Ground plane & Plot paver surface
    ground_tm = make_box_trimesh(-60.0, -55.0, -0.35, 75.0, 85.0, -0.12)
    add_trimesh_to_blender(ground_tm, "Site_Terrain_Base", site_coll, mats["asphalt_road"])

    if site.get("plot_boundary"):
        plot_poly = Polygon(site["plot_boundary"]["polygon"])
        paver_tm = extrude_shapely_polys([plot_poly], -0.12, 0.0)
        add_trimesh_to_blender(paver_tm, "Plot_Driveway_Pavers", site_coll, mats["paver_driveway"])

        # Compound wall along West, North, East, and Front (leaving driveway gate opening on front-left)
        # Front edge runs from (-2.697, 0.288) through (5.741, -3.359) to (17.088, -8.245)
        # Gate opening is from (-2.697, 0.288) to (4.80, -2.95)
        cw_h = float(heights.get("compound_wall_height", 2.10))
        cw_meshes: list[trimesh.Trimesh] = []

        # Front right compound wall (where "VIBGYOR" sign & feature trees sit!)
        p_gate_r = (4.60, -2.86)
        p_front_se = (17.088, -8.245)
        m_front = make_oriented_box(p_gate_r, p_front_se, thickness=0.28, z0=-0.10, z1=cw_h)
        if m_front is not None:
            cw_meshes.append(m_front)

        # Perimeter compound wall on West, North, and East plot edges
        pts = site["plot_boundary"]["polygon"]
        for i in range(len(pts)):
            p1 = (pts[i][0], pts[i][1])
            p2 = (pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1])
            # Skip front edge (already handled with gate opening)
            if p1[1] < 0.5 and p2[1] < 0.5:
                continue
            seg = make_oriented_box(p1, p2, thickness=0.23, z0=-0.10, z1=cw_h)
            if seg is not None:
                cw_meshes.append(seg)

        if cw_meshes:
            add_trimesh_to_blender(
                trimesh.util.concatenate(cw_meshes),
                "Plot_Compound_Wall",
                site_coll,
                mats["dark_concrete"],
            )

        # Entrance Canopy & Wooden Slat Gate (matching brochure/exterior.jpg & 7.jpg & 8.jpg)
        # Spans from (-2.65, 0.28) to (4.60, -2.86) and extends back 4.5m into driveway
        canopy_h = float(heights.get("canopy_height", 3.15))
        g_p1 = (-2.65, 0.28)
        g_p2 = (4.60, -2.86)
        # Portal frame top beam & side piers
        canopy_meshes: list[trimesh.Trimesh] = []
        for d_in in [0.0, 1.5, 3.0, 4.5]:
            sx, sy = 0.3962 * d_in, 0.9182 * d_in
            b_beam = make_oriented_box(
                (g_p1[0] + sx, g_p1[1] + sy),
                (g_p2[0] + sx, g_p2[1] + sy),
                thickness=1.60,
                z0=canopy_h - 0.22,
                z1=canopy_h,
            )
            if b_beam is not None:
                canopy_meshes.append(b_beam)
        # Left & right canopy walls
        canopy_meshes.append(
            make_oriented_box(g_p1, (g_p1[0] + 0.3962 * 4.8, g_p1[1] + 0.9182 * 4.8), 0.25, 0.0, canopy_h)
        )
        canopy_meshes.append(
            make_oriented_box(g_p2, (g_p2[0] + 0.3962 * 4.8, g_p2[1] + 0.9182 * 4.8), 0.25, 0.0, canopy_h)
        )
        add_trimesh_to_blender(
            trimesh.util.concatenate([m for m in canopy_meshes if m is not None]),
            "Entrance_Canopy_Frame",
            site_coll,
            mats["dark_concrete"],
        )

        # Wooden slat gate & side screening under canopy
        slat_meshes: list[trimesh.Trimesh] = []
        num_slats = 28
        for i in range(num_slats):
            t = (i + 0.5) / num_slats
            sx = g_p1[0] + (g_p2[0] - g_p1[0]) * t
            sy = g_p1[1] + (g_p2[1] - g_p1[1]) * t
            slat = make_box_trimesh(sx - 0.03, sy - 0.03, 0.05, sx + 0.03, sy + 0.03, 1.35)
            slat_meshes.append(slat)
        # Side wooden louver screen inside canopy right wall
        for i in range(18):
            d_in = 0.3 + i * 0.24
            sx = g_p2[0] - 0.15 + 0.3962 * d_in
            sy = g_p2[1] - 0.05 + 0.9182 * d_in
            slat_meshes.append(make_box_trimesh(sx - 0.04, sy - 0.04, 0.20, sx + 0.04, sy + 0.04, canopy_h - 0.25))
        add_trimesh_to_blender(
            trimesh.util.concatenate(slat_meshes),
            "Entrance_Wooden_Gate_Slats",
            site_coll,
            mats["wood_slats"],
        )

        # Canopy warm ceiling light strips
        canopy_lights: list[trimesh.Trimesh] = []
        for d_in in [0.8, 2.2, 3.6]:
            sx, sy = 0.3962 * d_in, 0.9182 * d_in
            cl = make_oriented_box(
                (g_p1[0] + 0.6 + sx, g_p1[1] - 0.25 + sy),
                (g_p2[0] - 0.6 + sx, g_p2[1] + 0.25 + sy),
                thickness=0.08,
                z0=canopy_h - 0.24,
                z1=canopy_h - 0.21,
            )
            if cl is not None:
                canopy_lights.append(cl)
        add_trimesh_to_blender(
            trimesh.util.concatenate(canopy_lights),
            "Entrance_Canopy_Lights",
            site_coll,
            mats["warm_led"],
        )

        # 3D Illuminated "V I B G Y O R" Signage on the front compound wall
        txt_curve = bpy.data.curves.new(type="FONT", name="Vibgyor_Sign_Font")
        txt_curve.body = "V I B G Y O R"
        txt_curve.size = 0.52
        txt_curve.extrude = 0.06
        txt_curve.align_x = "CENTER"
        txt_curve.align_y = "CENTER"
        txt_obj = bpy.data.objects.new("Vibgyor_Entrance_Sign", txt_curve)
        site_coll.objects.link(txt_obj)
        # Position on front-right compound wall facing the 18m main road
        mid_x = (p_gate_r[0] + p_front_se[0]) * 0.5
        mid_y = (p_gate_r[1] + p_front_se[1]) * 0.5
        txt_obj.location = (mid_x - 0.3962 * 0.18, mid_y - 0.9182 * 0.18, 1.05)
        txt_obj.rotation_euler = (math.pi * 0.5, 0.0, math.atan2(-5.385, 12.488))
        txt_obj.data.materials.append(mats["sign_glow"])

    # 2. Main 18m Road in front of the plot (extended so eye-level & aerial shots have full road context)
    # Road direction vector is u = (0.9182, -0.3962), outward normal is n = (-0.3962, -0.9182)
    r_p1 = (-28.0, 11.20)
    r_p2 = (42.0, -19.00)
    road_tm = make_oriented_box(
        (r_p1[0] - 0.3962 * 9.0, r_p1[1] - 0.9182 * 9.0),
        (r_p2[0] - 0.3962 * 9.0, r_p2[1] - 0.9182 * 9.0),
        thickness=18.0,
        z0=-0.11,
        z1=-0.02,
    )
    add_trimesh_to_blender(road_tm, "Main_18m_Road", site_coll, mats["asphalt_road"])

    # Road median curb & dashed lane markings (matching brochure/7.jpg & 8.jpg)
    markings: list[trimesh.Trimesh] = []
    median_shrubs: list[trimesh.Trimesh] = []
    for s in range(-15, 32, 4):
        mx1 = -2.697 + 0.9182 * s - 0.3962 * 4.5
        my1 = 0.288 - 0.3962 * s - 0.9182 * 4.5
        mx2 = mx1 + 0.9182 * 2.0
        my2 = my1 - 0.3962 * 2.0
        dash = make_oriented_box((mx1, my1), (mx2, my2), thickness=0.14, z0=-0.02, z1=-0.005)
        if dash is not None:
            markings.append(dash)
        # Median island & low shrubs at offset 8.5m
        ix1 = -2.697 + 0.9182 * s - 0.3962 * 8.5
        iy1 = 0.288 - 0.3962 * s - 0.9182 * 8.5
        ix2 = ix1 + 0.9182 * 2.8
        iy2 = iy1 - 0.3962 * 2.8
        curb = make_oriented_box((ix1, iy1), (ix2, iy2), thickness=0.65, z0=-0.02, z1=0.14)
        if curb is not None:
            markings.append(curb)
        shrub = make_oriented_box((ix1, iy1), (ix2, iy2), thickness=0.50, z0=0.14, z1=0.55)
        if shrub is not None:
            median_shrubs.append(shrub)

    if markings:
        add_trimesh_to_blender(
            trimesh.util.concatenate(markings), "Road_Markings_And_Curb", site_coll, mats["road_marking"]
        )
    if median_shrubs:
        add_trimesh_to_blender(
            trimesh.util.concatenate(median_shrubs), "Road_Median_Shrubs", site_coll, mats["foliage_bright"]
        )

    # 3. Trees from the DXF landscape layout (25 TR1 positions + 2 feature trees by front wall)
    trunks: list[trimesh.Trimesh] = []
    canopies: list[trimesh.Trimesh] = []
    tree_coords = list(site.get("trees", []))

    for idx, (tx, ty) in enumerate(tree_coords):
        # Vary height slightly for natural look (deterministic from index)
        h_scale = 0.85 + (idx % 5) * 0.10
        trunk_h = 2.6 * h_scale
        trunk = trimesh.creation.cylinder(radius=0.11, height=trunk_h, sections=8)
        trunk.apply_translation([tx, ty, trunk_h * 0.5])
        trunks.append(trunk)

        # Layered organic canopy (3 overlapping icospheres)
        for ox_c, oy_c, oz_c, rad in [
            (0.0, 0.0, trunk_h + 0.7 * h_scale, 1.25 * h_scale),
            (0.45, -0.35, trunk_h + 0.35 * h_scale, 0.95 * h_scale),
            (-0.40, 0.40, trunk_h + 0.45 * h_scale, 1.00 * h_scale),
        ]:
            sphere = trimesh.creation.icosphere(subdivisions=2, radius=rad)
            sphere.apply_scale([1.0, 1.0, 0.72])
            sphere.apply_translation([tx + ox_c, ty + oy_c, oz_c])
            canopies.append(sphere)

    if trunks:
        trunk_obj = add_trimesh_to_blender(
            trimesh.util.concatenate(trunks), "Landscape_Tree_Trunks", site_coll, mats["tree_trunk"]
        )
        if trunk_obj and trunk_obj.data:
            for poly in trunk_obj.data.polygons:
                poly.use_smooth = True
    if canopies:
        canopy_obj = add_trimesh_to_blender(
            trimesh.util.concatenate(canopies), "Landscape_Tree_Canopies", site_coll, mats["foliage_green"]
        )
        if canopy_obj and canopy_obj.data:
            for poly in canopy_obj.data.polygons:
                poly.use_smooth = True


# =============================================================================
# Bonus: Type A Interior + Drawing Room Furniture (Floor 1, z = 3.30m)
# =============================================================================


def build_type_a_drawing_room_interior(
    z_floor: float,
    floor_h: float,
    slab_t: float,
    mats: dict[str, bpy.types.Material],
    int_coll: bpy.types.Collection,
) -> None:
    """
    Populates the Type A flat on Floor 1 (Drawing Room & Dining/Kitchen area:
    x in [3.4, 11.4], y in [8.5, 16.8], matching brochure/1.jpg - 5.jpg & type-a.png)
    so the 360-degree equirectangular panorama of the Drawing Room looks rich and realistic.
    """
    z_f = z_floor + 0.02
    z_ceil = z_floor + floor_h - slab_t

    # 1. Polished white marble floor across Type A living/dining/bedrooms
    floor_tm = make_box_trimesh(1.80, 2.00, z_floor, 13.00, 18.85, z_f)
    add_trimesh_to_blender(floor_tm, "TypeA_Marble_Floor", int_coll, mats["marble_floor"])

    # 2. Coffered false ceiling with warm cove LED lighting in Drawing & Dining Room
    ceil_tm = make_box_trimesh(3.30, 8.50, z_ceil - 0.12, 11.40, 16.80, z_ceil)
    add_trimesh_to_blender(ceil_tm, "TypeA_False_Ceiling", int_coll, mats["interior_wall"])

    # Warm cove light strips around drawing room ceiling recess
    cove_lights = [
        make_box_trimesh(5.20, 12.10, z_ceil - 0.14, 11.10, 12.18, z_ceil - 0.10),
        make_box_trimesh(5.20, 15.30, z_ceil - 0.14, 11.10, 15.38, z_ceil - 0.10),
        make_box_trimesh(5.20, 12.10, z_ceil - 0.14, 5.28, 15.38, z_ceil - 0.10),
        make_box_trimesh(11.02, 12.10, z_ceil - 0.14, 11.10, 15.38, z_ceil - 0.10),
    ]
    add_trimesh_to_blender(
        trimesh.util.concatenate(cove_lights), "TypeA_Ceiling_Cove_LEDs", int_coll, mats["warm_led"]
    )

    # 3. Sage green wainscoting / panelled feature wall (north/west wall of Drawing Room, matching 1.jpg)
    panel_meshes: list[trimesh.Trimesh] = [
        make_box_trimesh(5.80, 15.48, z_f, 11.35, 15.53, z_ceil - 0.12)
    ]
    for px in [6.2, 7.0, 7.8, 8.6, 9.4, 10.2, 11.0]:
        panel_meshes.append(make_box_trimesh(px - 0.02, 15.44, z_f + 0.1, px + 0.02, 15.49, z_ceil - 0.2))
    add_trimesh_to_blender(
        trimesh.util.concatenate(panel_meshes), "TypeA_Sage_Wall_Panelling", int_coll, mats["sage_panelling"]
    )

    # 4. Area Rug in Drawing Room center (x in [6.6, 10.6], y in [12.3, 15.1])
    rug_tm = make_box_trimesh(6.60, 12.30, z_f, 10.60, 15.10, z_f + 0.015)
    add_trimesh_to_blender(rug_tm, "TypeA_DrawingRoom_Rug", int_coll, mats["rug_fabric"])

    # 5. L-shaped Contemporary Sofa + Throw Cushions (matching type-a.png & 1.jpg)
    sofa_meshes: list[trimesh.Trimesh] = [
        # Main long sofa along north side (y in [14.45, 15.35], x in [6.80, 10.30])
        make_box_trimesh(6.80, 14.45, z_f + 0.05, 10.30, 15.35, z_f + 0.42),  # seat
        make_box_trimesh(6.80, 15.15, z_f + 0.42, 10.30, 15.38, z_f + 0.84),  # backrest
        make_box_trimesh(6.65, 14.45, z_f + 0.05, 6.82, 15.38, z_f + 0.64),   # left armrest
        make_box_trimesh(10.28, 14.45, z_f + 0.05, 10.45, 15.38, z_f + 0.64), # right armrest
        # Side loveseat along east balcony slider (x in [10.45, 11.25], y in [12.40, 14.25])
        make_box_trimesh(10.45, 12.40, z_f + 0.05, 11.25, 14.25, z_f + 0.42),
        make_box_trimesh(11.05, 12.40, z_f + 0.42, 11.28, 14.25, z_f + 0.84),
    ]
    add_trimesh_to_blender(
        trimesh.util.concatenate(sofa_meshes), "TypeA_Sofa_Set", int_coll, mats["sofa_fabric"]
    )

    cushions = [
        make_box_trimesh(7.10, 14.90, z_f + 0.42, 7.55, 15.14, z_f + 0.74),
        make_box_trimesh(8.30, 14.90, z_f + 0.42, 8.75, 15.14, z_f + 0.74),
        make_box_trimesh(9.50, 14.90, z_f + 0.42, 9.95, 15.14, z_f + 0.74),
    ]
    add_trimesh_to_blender(
        trimesh.util.concatenate(cushions), "TypeA_Sofa_Cushions", int_coll, mats["cushion_terracotta"]
    )

    # 6. Round Brass & Marble Nested Coffee Tables in Drawing Room center (x=8.5, y=13.5)
    t1_top = trimesh.creation.cylinder(radius=0.52, height=0.04, sections=32)
    t1_top.apply_translation([8.45, 13.55, z_f + 0.40])
    t2_top = trimesh.creation.cylinder(radius=0.38, height=0.04, sections=32)
    t2_top.apply_translation([9.10, 13.35, z_f + 0.33])
    add_trimesh_to_blender(
        trimesh.util.concatenate([t1_top, t2_top]), "TypeA_Coffee_Table_Tops", int_coll, mats["marble_floor"]
    )

    t1_ring = trimesh.creation.cylinder(radius=0.50, height=0.38, sections=24)
    t1_ring.apply_translation([8.45, 13.55, z_f + 0.19])
    t2_ring = trimesh.creation.cylinder(radius=0.36, height=0.31, sections=24)
    t2_ring.apply_translation([9.10, 13.35, z_f + 0.16])
    add_trimesh_to_blender(
        trimesh.util.concatenate([t1_ring, t2_ring]), "TypeA_Coffee_Table_Bases", int_coll, mats["brass_gold"]
    )

    # 7. Fluted Media Console & Large 65" OLED TV along south wall of Drawing Room (y=11.95, x in [7.2, 10.1])
    console_tm = make_box_trimesh(7.20, 11.92, z_f + 0.08, 10.10, 12.38, z_f + 0.52)
    add_trimesh_to_blender(console_tm, "TypeA_TV_Console", int_coll, mats["wood_soffit"])
    tv_tm = make_box_trimesh(7.85, 12.05, z_f + 0.58, 9.45, 12.11, z_f + 1.50)
    add_trimesh_to_blender(tv_tm, "TypeA_OLED_TV", int_coll, mats["dark_glass_table"])

    # 8. Dining Table (6-seater) & Kitchen Island (x in [4.5, 8.2], y in [9.5, 11.6])
    dining_top = make_box_trimesh(6.60, 10.10, z_f + 0.74, 8.25, 11.15, z_f + 0.78)
    add_trimesh_to_blender(dining_top, "TypeA_Dining_Table", int_coll, mats["dark_glass_table"])

    kitchen_counters = [
        make_box_trimesh(1.85, 8.60, z_f, 6.20, 9.25, z_f + 0.88),   # south counter
        make_box_trimesh(1.85, 9.25, z_f, 2.50, 13.35, z_f + 0.88),  # west counter
        make_box_trimesh(4.40, 10.40, z_f, 5.15, 12.10, z_f + 0.90), # breakfast island
    ]
    add_trimesh_to_blender(
        trimesh.util.concatenate(kitchen_counters), "TypeA_Kitchen_Counters", int_coll, mats["marble_floor"]
    )


# =============================================================================
# Main 3D Scene Builder
# =============================================================================


def build_model(
    extracted_json_path: str | Path = "outputs/extracted_geometry.json",
    output_blend_path: str | Path = "outputs/vibgyor.blend",
) -> Path:
    base_dir = Path(extracted_json_path).resolve().parent.parent
    with open(extracted_json_path, "r", encoding="utf-8") as f:
        geom = json.load(f)

    # Clear default Blender scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    mats = create_all_materials()
    from pipeline.furnish import (
        ensure_level2_materials,
        build_basement_parking_amenity,
        build_stilt_parking_and_entrance_lobby,
        build_flat_interiors_for_floor,
        build_terrace_amenities,
        build_landscape_and_drive_amenities,
    )
    ensure_level2_materials(mats)

    heights = geom["heights"]
    stilt_h = float(heights["stilt_floor_to_floor"])
    typ_h = float(heights["typical_floor_to_floor"])
    top_h = float(heights["top_floor_to_terrace"])
    slab_t = float(heights["slab_thickness"])
    planter_h = float(heights["planter_box_height"])
    num_floors = int(heights["num_residential_floors"])

    # Prepare shapes from extracted JSON
    typ = geom["typical_floor"]
    slab_poly = Polygon(typ["slab"]["polygon"])
    col_polys = [Polygon(c["polygon"]) for c in typ["columns"]]
    wall_polys = [Polygon(w["polygon"]) for w in typ["walls"]]
    proj_polys = [Polygon(p["polygon"]) for p in typ["projections"]]

    gf = geom["ground_floor"]
    gf_slab_poly = Polygon(gf["slab"]["polygon"])
    gf_wall_polys = [Polygon(w["polygon"]) for w in gf["core_walls"]]

    building_coll = get_or_create_collection("Vibgyor_Building")
    site_coll = get_or_create_collection("Vibgyor_Site")

    # -------------------------------------------------------------------------
    # 0. BASEMENT PARKING (z = -3.15m to 0.0m)
    # -------------------------------------------------------------------------
    build_basement_parking_amenity(geom, mats, building_coll)

    # -------------------------------------------------------------------------
    # 1. STILT / GROUND FLOOR (z = 0.0 to 3.30m)
    # -------------------------------------------------------------------------
    stilt_coll = get_or_create_collection("Floor_0_Stilt", building_coll)
    stilt_props = {
        "floor_index": 0,
        "floor_label": "Ground Floor (Stilt Parking)",
        "flats": "Stilt Parking & Entrance Foyer",
    }

    # Ground plinth slab (cut out the North-East basement ramp entrance so the ramp is open!)
    ramp_entry_cut = Polygon([(10.8, 25.5), (15.0, 25.5), (15.0, 42.0), (-3.5, 42.0), (-3.5, 38.8), (10.8, 38.8)])
    gf_slab_clean = gf_slab_poly.difference(ramp_entry_cut)
    gf_slab_list = [gf_slab_clean] if isinstance(gf_slab_clean, Polygon) else list(gf_slab_clean.geoms)
    plinth_tm = extrude_shapely_polys(gf_slab_list, -0.10, 0.05)
    add_trimesh_to_blender(plinth_tm, "Floor_0_Plinth_Slab", stilt_coll, mats["paver_driveway"], stilt_props)

    stilt_cols_tm = extrude_shapely_polys(col_polys, 0.0, stilt_h - slab_t)
    add_trimesh_to_blender(stilt_cols_tm, "Floor_0_Stilt_Columns", stilt_coll, mats["concrete_facade"], stilt_props)

    stilt_core_tm = extrude_shapely_polys(gf_wall_polys, 0.0, stilt_h - slab_t)
    add_trimesh_to_blender(stilt_core_tm, "Floor_0_Core_Walls", stilt_coll, mats["wall_stucco"], stilt_props)

    # Populate Stilt Parking bays, parked cars, and the Entrance Lobby (lifts, travertine, fluted wood, seating)
    build_stilt_parking_and_entrance_lobby(geom, mats, stilt_coll)

    # -------------------------------------------------------------------------
    # 2. RESIDENTIAL FLOORS 1 TO 7
    # -------------------------------------------------------------------------
    type_a_info = typ["flats"].get("type_a")
    type_b_info = typ["flats"].get("type_b")
    type_a_poly = Polygon(type_a_info["polygon"]) if type_a_info else None
    type_b_poly = Polygon(type_b_info["polygon"]) if type_b_info else None

    for floor_num in range(1, num_floors + 1):
        z_floor = stilt_h + (floor_num - 1) * typ_h
        f_h = top_h if floor_num == num_floors else typ_h
        f_coll = get_or_create_collection(f"Floor_{floor_num}", building_coll)

        f_props = {
            "floor_index": floor_num,
            "floor_label": f"Floor {floor_num}",
            "flat_a": f"Flat {floor_num}01 (Type A · 4BHK Front · 160.05 sq.m)",
            "flat_b": f"Flat {floor_num}02 (Type B · 4BHK Rear · 143.18 sq.m)",
        }

        # Structural slab & columns & walls
        cols_tm = extrude_shapely_polys(col_polys, z_floor, z_floor + f_h - slab_t)
        add_trimesh_to_blender(
            cols_tm, f"Floor_{floor_num}_Columns", f_coll, mats["concrete_facade"], f_props
        )

        walls_tm = extrude_shapely_polys(wall_polys, z_floor, z_floor + f_h - slab_t)
        add_trimesh_to_blender(
            walls_tm, f"Floor_{floor_num}_Walls", f_coll, mats["wall_stucco"], f_props
        )

        # Sill & Lintel wall bands above/below windows and sliding doors
        sill_lintel_meshes: list[trimesh.Trimesh] = []
        frame_meshes: list[trimesh.Trimesh] = []
        glass_meshes: list[trimesh.Trimesh] = []

        for op in typ["windows"] + typ["sliding_doors"]:
            op_poly = Polygon(op["polygon"])
            sill_h = float(op.get("sill_height", 0.90))
            lintel_h = float(op.get("lintel_height", 2.12))
            if sill_h > 0.02:
                sm = extrude_shapely_polys([op_poly], z_floor, z_floor + sill_h)
                if sm is not None:
                    sill_lintel_meshes.append(sm)
            if lintel_h < f_h - slab_t - 0.02:
                lm = extrude_shapely_polys([op_poly], z_floor + lintel_h, z_floor + f_h - slab_t)
                if lm is not None:
                    sill_lintel_meshes.append(lm)

            f_ms, g_ms = build_window_or_door_assembly(op, z_floor)
            frame_meshes.extend(f_ms)
            glass_meshes.extend(g_ms)

        # Also add lintel headers above interior/foyer doors
        for d_item in typ["doors"]:
            dp1 = tuple(d_item["start"])
            dp2 = tuple(d_item["end"])
            dm = make_oriented_box(dp1, dp2, thickness=0.10, z0=z_floor + 2.10, z1=z_floor + f_h - slab_t)
            if dm is not None:
                sill_lintel_meshes.append(dm)

        if sill_lintel_meshes:
            add_trimesh_to_blender(
                trimesh.util.concatenate(sill_lintel_meshes),
                f"Floor_{floor_num}_Window_Walls",
                f_coll,
                mats["wall_stucco"],
                f_props,
            )
        if frame_meshes:
            add_trimesh_to_blender(
                trimesh.util.concatenate(frame_meshes),
                f"Floor_{floor_num}_Window_Frames",
                f_coll,
                mats["charcoal_metal"],
                f_props,
            )
        if glass_meshes:
            add_trimesh_to_blender(
                trimesh.util.concatenate(glass_meshes),
                f"Floor_{floor_num}_Window_Glazing",
                f_coll,
                mats["window_glass"],
                f_props,
            )

        # Facade detailing (rounded slab band, planters, foliage, metal fins, glass railings, LED spots)
        fac = build_facade_details_for_floor(
            slab_poly, proj_polys, typ["railings"], z_floor, f_h, slab_t, planter_h
        )
        if fac["slab_band"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["slab_band"]),
                f"Floor_{floor_num}_Slab_Band",
                f_coll,
                mats["concrete_facade"],
                f_props,
            )
        if fac["planter_box"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["planter_box"]),
                f"Floor_{floor_num}_Planter_Boxes",
                f_coll,
                mats["planter_terracotta"],
                f_props,
            )
        if fac["planter_foliage"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["planter_foliage"]),
                f"Floor_{floor_num}_Planter_Foliage",
                f_coll,
                mats["foliage_bright"],
                f_props,
            )
        if fac["metal_fins"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["metal_fins"]),
                f"Floor_{floor_num}_Facade_Fins",
                f_coll,
                mats["charcoal_metal"],
                f_props,
            )
        if fac["railing_glass"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["railing_glass"]),
                f"Floor_{floor_num}_Balcony_Glass",
                f_coll,
                mats["railing_glass"],
                f_props,
            )
        if fac["wood_soffit"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["wood_soffit"]),
                f"Floor_{floor_num}_Balcony_Soffit",
                f_coll,
                mats["wood_soffit"],
                f_props,
            )
        if fac["LED_spots"]:
            add_trimesh_to_blender(
                trimesh.util.concatenate(fac["LED_spots"]),
                f"Floor_{floor_num}_Facade_LEDs",
                f_coll,
                mats["warm_led"],
                f_props,
            )

        # Flat Type A & Type B floor plates (tagged by name so the interactive web viewer can highlight Type A & Type B!)
        if type_a_poly is not None:
            ta_tm = extrude_shapely_polys([type_a_poly], z_floor + 0.01, z_floor + 0.05)
            add_trimesh_to_blender(
                ta_tm,
                f"Floor_{floor_num}_Flat_{floor_num}01_TypeA",
                f_coll,
                mats["marble_floor"],
                {**f_props, "unit_type": "Type A", "unit_no": f"{floor_num}01"},
            )
        if type_b_poly is not None:
            tb_tm = extrude_shapely_polys([type_b_poly], z_floor + 0.01, z_floor + 0.05)
            add_trimesh_to_blender(
                tb_tm,
                f"Floor_{floor_num}_Flat_{floor_num}02_TypeB",
                f_coll,
                mats["marble_floor"],
                {**f_props, "unit_type": "Type B", "unit_no": f"{floor_num}02"},
            )

        # Populate complete geometry-driven interiors for both Type A and Type B on Floor 1
        if floor_num == 1:
            build_flat_interiors_for_floor(geom, floor_num, z_floor, f_h, slab_t, mats, f_coll)

    # -------------------------------------------------------------------------
    # 3. TERRACE LEVEL, PARAPET, STAIR CABIN & OVERHEAD WATER TANK (z = 24.70m+)
    # -------------------------------------------------------------------------
    z_terrace = stilt_h + 6 * typ_h + top_h
    terr_coll = get_or_create_collection("Floor_8_Terrace", building_coll)
    terr_props = {
        "floor_index": 8,
        "floor_label": "Open Terrace & Stair Cabin",
        "flats": "Open Terrace, Lift Machine Room & O.H.W.T.",
    }

    full_slab = unary_union([slab_poly] + proj_polys)
    rounded_terr = full_slab.buffer(0.18, resolution=8).buffer(-0.18, resolution=8)
    terr_polys_list = [rounded_terr] if isinstance(rounded_terr, Polygon) else list(rounded_terr.geoms)
    terr_slab_tm = extrude_shapely_polys(terr_polys_list, z_terrace - slab_t, z_terrace + 0.08)
    add_trimesh_to_blender(
        terr_slab_tm, "Floor_8_Terrace_Slab", terr_coll, mats["concrete_facade"], terr_props
    )

    # Terrace parapet wall (1.15m high around terrace perimeter)
    parapet_ring = rounded_terr.exterior.buffer(0.10, resolution=4)
    parapet_tm = extrude_shapely_polys(
        [parapet_ring], z_terrace + 0.08, z_terrace + float(heights["parapet_railing_height"])
    )
    add_trimesh_to_blender(
        parapet_tm, "Floor_8_Terrace_Parapet", terr_coll, mats["concrete_facade"], terr_props
    )

    # Stair cabin & lift machine room + Overhead Water Tank (O.H.W.T.) from Terrace Plan
    terr_data = geom.get("terrace", {})
    cabin_h = float(heights["stair_cabin_height"])
    ohwt_h = float(heights["ohwt_height"])
    terr_wall_polys = [Polygon(w["polygon"]) for w in terr_data.get("walls_and_parapets", [])]
    if terr_wall_polys:
        cabin_walls_tm = extrude_shapely_polys(terr_wall_polys, z_terrace, z_terrace + cabin_h)
        add_trimesh_to_blender(
            cabin_walls_tm, "Floor_8_Stair_Cabin_Walls", terr_coll, mats["concrete_facade"], terr_props
        )
    if terr_data.get("stair_cabin_slab"):
        cabin_slab_poly = Polygon(terr_data["stair_cabin_slab"]["polygon"])
        cabin_roof_tm = extrude_shapely_polys(
            [cabin_slab_poly], z_terrace + cabin_h - slab_t, z_terrace + cabin_h
        )
        add_trimesh_to_blender(
            cabin_roof_tm, "Floor_8_Stair_Cabin_Roof", terr_coll, mats["concrete_facade"], terr_props
        )
        # O.H.W.T. above lift/stair core (x in [1.675, 5.8], y in [18.86, 23.22], height 2.40m)
        ohwt_box = make_box_trimesh(
            1.675, 18.864, z_terrace + cabin_h, 5.80, 23.216, z_terrace + cabin_h + ohwt_h
        )
        add_trimesh_to_blender(
            ohwt_box, "Floor_8_Overhead_Water_Tank", terr_coll, mats["concrete_facade"], terr_props
        )

    # Populate Terrace Amenities (Pergola Seating, Kids' Play Area, Fitness Gym & Solar Roof)
    build_terrace_amenities(geom, z_terrace, mats, terr_coll)

    # -------------------------------------------------------------------------
    # 4. SITE & LANDSCAPE
    # -------------------------------------------------------------------------
    build_site_and_plot(geom, mats, site_coll)
    build_landscape_and_drive_amenities(geom, mats, site_coll)

    # Save .blend file
    out_blend = base_dir / output_blend_path
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    print(f"[build] Saved 3D model to {out_blend} ({out_blend.stat().st_size // 1024} KB)")
    return out_blend


if __name__ == "__main__":
    build_model()
