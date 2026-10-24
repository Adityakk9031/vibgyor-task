"""
Stage 1: Extract clean 2D geometry JSON from SUBMISSION - 04.dxf.

Reads the architect's DXF file and config.json, expands nested blocks via
ezdxf's virtual_entities(), aligns each plan region into a unified building-relative
coordinate system in metres (where (0, 0) is the SW corner of the building
footprint bbox), reconstructs closed 2D polygons for walls, columns, slabs,
architectural projections, windows, sliding doors, railings, stairs, terrace
cabin, and site/plot features, and writes outputs/extracted_geometry.json.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import ezdxf
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, unary_union


def load_config(config_path: str | Path = "config.json") -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_dxf_path(config: dict[str, Any], base_dir: Path = Path(".")) -> Path:
    for candidate in config.get("dxf_candidates", ["SUBMISSION - 04.dxf"]):
        p = base_dir / candidate
        if p.exists():
            return p
    raise FileNotFoundError("Could not find 'SUBMISSION - 04.dxf' in workspace.")


def iter_virtual_leaves(container: Any, max_depth: int = 4, _depth: int = 0):
    """Yields all leaf DXF entities, expanding INSERT references into world space."""
    for entity in container:
        if entity.dxftype() == "INSERT" and _depth < max_depth:
            try:
                for ve in entity.virtual_entities():
                    yield from iter_virtual_leaves([ve], max_depth, _depth + 1)
            except Exception:
                pass
        else:
            yield entity


def clean_dxf_text(raw: str) -> str:
    """Strips AutoCAD formatting codes from TEXT/MTEXT strings."""
    text = raw.replace("\\P", " ").replace("%%U", "").replace("%%u", "")
    text = re.sub(r"\{\\[^;]+;", "", text)
    text = re.sub(r"\\A1;", "", text)
    text = re.sub(r"\\C\d+;", "", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def poly_to_coords(poly: Polygon) -> list[list[float]]:
    coords = [[round(float(x), 4), round(float(y), 4)] for x, y in poly.exterior.coords]
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def poly_to_dict(poly: Polygon, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    b = [round(float(v), 4) for v in poly.bounds]
    c = poly.centroid
    d: dict[str, Any] = {
        "polygon": poly_to_coords(poly),
        "holes": [
            [[round(float(x), 4), round(float(y), 4)] for x, y in interior.coords[:-1]]
            for interior in poly.interiors
        ],
        "bounds": b,
        "width": round(b[2] - b[0], 4),
        "depth": round(b[3] - b[1], 4),
        "area": round(float(poly.area), 4),
        "centroid": [round(float(c.x), 4), round(float(c.y), 4)],
    }
    if extra:
        d.update(extra)
    return d


def dedup_polygons(polys: list[Polygon], tol: float = 0.05) -> list[Polygon]:
    """Removes duplicate/concentric inner frame polylines (e.g. double-rect windows in CAD)."""
    sorted_polys = sorted(polys, key=lambda p: p.area, reverse=True)
    kept: list[Polygon] = []
    for p in sorted_polys:
        if p.area < 1e-4:
            continue
        is_dup = False
        for k in kept:
            if k.buffer(tol).contains(p) or k.centroid.distance(p.centroid) < tol:
                is_dup = True
                break
        if not is_dup:
            kept.append(p)
    return kept


def extract_geometry(
    config_path: str | Path = "config.json",
    output_path: str | Path = "outputs/extracted_geometry.json",
) -> dict[str, Any]:
    base_dir = Path(config_path).resolve().parent
    config = load_config(config_path)
    dxf_path = resolve_dxf_path(config, base_dir)

    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    leaves = list(iter_virtual_leaves(msp))

    regions_cfg = config["dxf_regions"]
    layers_cfg = config["layers"]

    # -------------------------------------------------------------------------
    # 1. TYPICAL FLOOR PLAN (1st to 7th Floor)
    # -------------------------------------------------------------------------
    typ_bbox = regions_cfg["typical_floor_plan"]["bbox"]
    tox, toy = regions_cfg["typical_floor_plan"]["building_origin"]

    def in_bbox(x: float, y: float, bbox: list[float]) -> bool:
        return bbox[0] <= x <= bbox[1] and bbox[2] <= y <= bbox[3]

    typ_wall_Boundary_lines: list[LineString] = []
    raw_columns: list[Polygon] = []
    raw_windows: list[Polygon] = []
    raw_sliding: list[Polygon] = []
    raw_railings: list[Polygon] = []
    raw_doors: list[dict[str, Any]] = []
    raw_proj_lines: list[LineString] = []
    raw_stair_treads: list[list[list[float]]] = []
    raw_ducts: list[list[list[float]]] = []
    typical_slab_poly: Polygon | None = None
    room_labels: list[dict[str, Any]] = []
    dw_labels: list[dict[str, Any]] = []

    boundary_layers = set(
        layers_cfg["walls"]
        + layers_cfg["columns"]
        + layers_cfg["windows"]
        + layers_cfg["glazed_sliding"]
        + layers_cfg["railings"]
        + layers_cfg["doors"]
    )

    for e in leaves:
        etype = e.dxftype()
        lyr = e.dxf.layer

        if etype == "LINE":
            sx, sy = float(e.dxf.start.x), float(e.dxf.start.y)
            ex, ey = float(e.dxf.end.x), float(e.dxf.end.y)
            if in_bbox((sx + ex) * 0.5, (sy + ey) * 0.5, typ_bbox):
                p1 = (round(sx - tox, 4), round(sy - toy, 4))
                p2 = (round(ex - tox, 4), round(ey - toy, 4))
                if p1 != p2:
                    ls = LineString([p1, p2])
                    if lyr in boundary_layers:
                        typ_wall_Boundary_lines.append(ls)
                    if lyr in layers_cfg["projections"]:
                        raw_proj_lines.append(ls)
                    elif lyr in layers_cfg["doors"]:
                        length = round(math.hypot(p2[0] - p1[0], p2[1] - p1[1]), 4)
                        raw_doors.append(
                            {
                                "start": list(p1),
                                "end": list(p2),
                                "midpoint": [
                                    round((p1[0] + p2[0]) * 0.5, 4),
                                    round((p1[1] + p2[1]) * 0.5, 4),
                                ],
                                "width": length,
                                "orientation": "horizontal"
                                if abs(p1[1] - p2[1]) < abs(p1[0] - p2[0])
                                else "vertical",
                            }
                        )
                    elif lyr in ("g-ele02", "g-ele-03"):
                        raw_stair_treads.append([list(p1), list(p2)])
                    elif lyr in layers_cfg["ducts"]:
                        raw_ducts.append([list(p1), list(p2)])

        elif etype == "LWPOLYLINE":
            pts_raw = list(e.get_points())
            if not pts_raw:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, typ_bbox):
                pts = [(round(float(p[0]) - tox, 4), round(float(p[1]) - toy, 4)) for p in pts_raw]
                if e.closed and pts[0] != pts[-1]:
                    pts.append(pts[0])
                if len(pts) >= 2:
                    ls = LineString(pts)
                    if lyr in boundary_layers:
                        typ_wall_Boundary_lines.append(ls)
                    if len(pts) >= 4:
                        poly = Polygon(pts)
                        if not poly.is_valid:
                            poly = poly.buffer(0)
                        if isinstance(poly, Polygon) and poly.area > 1e-4:
                            if lyr == "COLUMN_BSE":
                                raw_columns.append(poly)
                            elif lyr in layers_cfg["windows"]:
                                raw_windows.append(poly)
                            elif lyr in layers_cfg["glazed_sliding"]:
                                raw_sliding.append(poly)
                            elif lyr in layers_cfg["railings"]:
                                raw_railings.append(poly)
                            elif lyr in layers_cfg["slabs"]:
                                typical_slab_poly = poly

        elif etype in ("TEXT", "MTEXT"):
            ix, iy = float(e.dxf.insert.x), float(e.dxf.insert.y)
            if in_bbox(ix, iy, typ_bbox):
                raw_txt = e.dxf.text if etype == "TEXT" else e.text
                txt = clean_dxf_text(raw_txt)
                rx, ry = round(ix - tox, 4), round(iy - toy, 4)
                if lyr in layers_cfg["room_labels"] and txt:
                    room_labels.append({"text": txt, "position": [rx, ry]})
                elif lyr in layers_cfg["dw_labels"] and txt:
                    dw_labels.append({"tag": txt, "position": [rx, ry]})

    # Deduplicate columns, windows, sliding doors, railings
    columns_dedup = dedup_polygons(raw_columns, tol=0.05)
    windows_dedup = dedup_polygons(raw_windows, tol=0.04)
    sliding_dedup = dedup_polygons(raw_sliding, tol=0.04)
    railings_dedup = dedup_polygons(raw_railings, tol=0.04)

    # Polygonize wall network
    unioned_lines = unary_union(typ_wall_Boundary_lines)
    all_closed_polys = list(polygonize(unioned_lines))

    # Filter wall polygons: exclude rooms (thickness_est >= 0.35 or area > 4.0)
    # and subtract windows, sliding doors, railings, and structural columns so walls are clean!
    cutouts_union = unary_union(
        [p.buffer(0.005) for p in (windows_dedup + sliding_dedup + railings_dedup + columns_dedup)]
    )
    wall_polygons: list[Polygon] = []
    for p in all_closed_polys:
        if p.area <= 0.004 or p.length <= 0:
            continue
        thickness_est = 2.0 * p.area / p.length
        if thickness_est < 0.34 and p.area < 3.5:
            diff = p.difference(cutouts_union)
            if isinstance(diff, Polygon) and diff.area > 0.004:
                wall_polygons.append(diff)
            elif isinstance(diff, MultiPolygon):
                for sp in diff.geoms:
                    if sp.area > 0.004:
                        wall_polygons.append(sp)

    # Reconstruct exterior architectural projections (chajjas / balcony ledges)
    proj_polygons: list[Polygon] = []
    if typical_slab_poly is not None and raw_proj_lines:
        combined_proj = raw_proj_lines + [typical_slab_poly.exterior]
        cand_projs = list(polygonize(unary_union(combined_proj)))
        for cp in cand_projs:
            if cp.area > 0.02 and not typical_slab_poly.contains(cp.representative_point()):
                proj_polygons.append(cp)

    # Match D&W tags (W, W1-W4, V, SD) to nearest window/sliding polygon
    def find_nearest_tag(poly: Polygon, allowed_prefixes: tuple[str, ...]) -> str:
        c = poly.centroid
        best_tag = allowed_prefixes[0]
        best_dist = 999.0
        for item in dw_labels:
            t = item["tag"]
            if any(t.startswith(pref) for pref in allowed_prefixes):
                d = math.hypot(c.x - item["position"][0], c.y - item["position"][1])
                if d < best_dist:
                    best_dist = d
                    best_tag = t
        return best_tag

    windows_out = []
    for wp in windows_dedup:
        tag = find_nearest_tag(wp, ("V", "W"))
        is_vent = tag.startswith("V")
        sill = (
            config["heights"]["ventilator_sill_height"]
            if is_vent
            else config["heights"]["window_sill_height"]
        )
        lintel = (
            config["heights"]["ventilator_lintel_height"]
            if is_vent
            else config["heights"]["window_lintel_height"]
        )
        windows_out.append(
            poly_to_dict(
                wp,
                {
                    "tag": tag,
                    "type": "ventilator" if is_vent else "window",
                    "sill_height": sill,
                    "lintel_height": lintel,
                },
            )
        )

    sliding_out = []
    for sp in sliding_dedup:
        tag = find_nearest_tag(sp, ("SD", "W", "D"))
        is_sd = tag == "SD" or max(sp.bounds[2] - sp.bounds[0], sp.bounds[3] - sp.bounds[1]) > 2.8
        sill = 0.0 if is_sd else config["heights"]["window_sill_height"]
        lintel = (
            config["heights"]["door_lintel_height"]
            if is_sd
            else config["heights"]["window_lintel_height"]
        )
        sliding_out.append(
            poly_to_dict(
                sp,
                {
                    "tag": tag,
                    "type": "sliding_door" if is_sd else "large_window",
                    "sill_height": sill,
                    "lintel_height": lintel,
                },
            )
        )

    # -------------------------------------------------------------------------
    # 2. RERA CARPET POLYGONS (Type A, Type B, Balconies, Foyer)
    # -------------------------------------------------------------------------
    rera_cfg = regions_cfg["rera_carpet_plan"]
    rera_blk = doc.blocks.get(rera_cfg["block_name"])
    y_off_rera = float(rera_cfg["y_offset_in_block"])
    flats_data: dict[str, Any] = {"type_a": None, "type_b": None, "balconies": []}
    if rera_blk is not None:
        balcony_polys: list[Polygon] = []
        for e in rera_blk:
            if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "A_RERA CARPET":
                pts = [
                    (round(float(p[0]), 4), round(float(p[1]) + y_off_rera, 4))
                    for p in e.get_points()
                ]
                if len(pts) >= 3:
                    poly = Polygon(pts)
                    if poly.area > 150.0:
                        flats_data["type_a"] = poly_to_dict(
                            poly,
                            {
                                "name": "Type A (Front 4BHK)",
                                "units": [f"{f}01" for f in range(1, 8)],
                                "rera_carpet_area_sqm": 160.05,
                            },
                        )
                    elif poly.area > 130.0:
                        flats_data["type_b"] = poly_to_dict(
                            poly,
                            {
                                "name": "Type B (Rear 4BHK)",
                                "units": [f"{f}02" for f in range(1, 8)],
                                "rera_carpet_area_sqm": 143.18,
                            },
                        )
                    elif 1.5 < poly.area < 15.0:
                        balcony_polys.append(poly)

        for idx, bp in enumerate(sorted(balcony_polys, key=lambda p: p.centroid.y)):
            unit_type = "Type A" if bp.centroid.y < 20.0 else "Type B"
            flats_data["balconies"].append(
                poly_to_dict(bp, {"id": f"balcony_{idx+1}", "unit": unit_type})
            )

    # -------------------------------------------------------------------------
    # 3. GROUND FLOOR (STILT PARKING) PLAN
    # -------------------------------------------------------------------------
    gf_bbox = regions_cfg["ground_floor_plan"]["bbox"]
    gox, goy = regions_cfg["ground_floor_plan"]["building_origin"]
    gf_wall_lines: list[LineString] = []
    gf_slab_poly: Polygon | None = None
    for e in leaves:
        etype = e.dxftype()
        lyr = e.dxf.layer
        if etype == "LINE":
            sx, sy = float(e.dxf.start.x), float(e.dxf.start.y)
            ex, ey = float(e.dxf.end.x), float(e.dxf.end.y)
            if in_bbox((sx + ex) * 0.5, (sy + ey) * 0.5, gf_bbox):
                p1 = (round(sx - gox, 4), round(sy - goy, 4))
                p2 = (round(ex - gox, 4), round(ey - goy, 4))
                if p1 != p2 and lyr in ("A_Wall", "g-wall", "g-r.c.c"):
                    gf_wall_lines.append(LineString([p1, p2]))
        elif etype == "LWPOLYLINE":
            pts_raw = list(e.get_points())
            if not pts_raw:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, gf_bbox):
                pts = [(round(float(p[0]) - gox, 4), round(float(p[1]) - goy, 4)) for p in pts_raw]
                if e.closed and pts[0] != pts[-1]:
                    pts.append(pts[0])
                if len(pts) >= 2 and lyr in ("A_Wall", "g-wall", "g-r.c.c", "A_WINDOW"):
                    gf_wall_lines.append(LineString(pts))
                if len(pts) >= 4 and lyr in layers_cfg["slabs"]:
                    gf_slab_poly = Polygon(pts)

    gf_polys = [
        p
        for p in polygonize(unary_union(gf_wall_lines))
        if 0.005 < p.area < 3.0 and (2.0 * p.area / p.length) < 0.35
    ]

    # -------------------------------------------------------------------------
    # 4. TERRACE & STAIR CABIN PLAN
    # -------------------------------------------------------------------------
    terr_bbox = regions_cfg["terrace_plan"]["bbox"]
    trox, troy = regions_cfg["terrace_plan"]["building_origin"]
    terrace_parapets: list[Polygon] = []
    stair_cabin_slab: Polygon | None = None
    terr_wall_lines: list[LineString] = []

    for e in leaves:
        etype = e.dxftype()
        lyr = e.dxf.layer
        if etype == "LINE":
            sx, sy = float(e.dxf.start.x), float(e.dxf.start.y)
            ex, ey = float(e.dxf.end.x), float(e.dxf.end.y)
            if in_bbox((sx + ex) * 0.5, (sy + ey) * 0.5, terr_bbox):
                p1 = (round(sx - trox, 4), round(sy - troy, 4))
                p2 = (round(ex - trox, 4), round(ey - troy, 4))
                if p1 != p2 and p1[0] >= -0.05 and p2[0] >= -0.05:
                    if lyr in ("A_Wall", "g-r.c.c", "A_DOOR"):
                        terr_wall_lines.append(LineString([p1, p2]))
        elif etype == "LWPOLYLINE":
            pts_raw = list(e.get_points())
            if not pts_raw:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, terr_bbox):
                pts = [
                    (round(float(p[0]) - trox, 4), round(float(p[1]) - troy, 4)) for p in pts_raw
                ]
                if pts[0][0] < -0.05:
                    continue
                if e.closed and pts[0] != pts[-1]:
                    pts.append(pts[0])
                if len(pts) >= 2 and lyr in ("A_Wall", "g-r.c.c", "A_PARAPET"):
                    terr_wall_lines.append(LineString(pts))
                if len(pts) >= 4 and lyr in layers_cfg["slabs"]:
                    stair_cabin_slab = Polygon(pts)

    terr_polys = [
        p
        for p in polygonize(unary_union(terr_wall_lines))
        if 0.005 < p.area < 8.0 and (2.0 * p.area / p.length) < 0.35
    ]

    # -------------------------------------------------------------------------
    # 5. FRONT ELEVATION FACADE DETAILING
    # -------------------------------------------------------------------------
    elev_bbox = regions_cfg["front_elevation"]["bbox"]
    eox = float(regions_cfg["front_elevation"]["origin_x"])
    planter_zones_x: list[list[float]] = []
    for e in leaves:
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "a-Ele2-HM":
            pts_raw = list(e.get_points())
            if pts_raw and in_bbox(pts_raw[0][0], pts_raw[0][1], elev_bbox):
                xs = [round(float(p[0]) - eox, 3) for p in pts_raw]
                ys = [float(p[1]) for p in pts_raw]
                w = round(max(xs) - min(xs), 3)
                h = round(max(ys) - min(ys), 3)
                if 2.5 < w < 5.0 and 0.40 <= h <= 0.55:
                    zone = [min(xs), max(xs)]
                    if zone not in planter_zones_x:
                        planter_zones_x.append(zone)

    # -------------------------------------------------------------------------
    # 6. SITE / LAYOUT PLAN (Plot boundary, road, basement ramp, trees)
    # -------------------------------------------------------------------------
    site_bbox = regions_cfg["layout_plan"]["bbox"]
    sox, soy = regions_cfg["layout_plan"]["building_origin"]
    plot_boundary_poly: Polygon | None = None
    road_poly: Polygon | None = None
    basement_footprint_poly: Polygon | None = None
    ramp_wall_poly: Polygon | None = None
    tree_positions: list[list[float]] = []

    for e in leaves:
        if e.dxftype() == "LWPOLYLINE":
            pts_raw = list(e.get_points())
            if not pts_raw:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, site_bbox):
                pts = [(round(float(p[0]) - sox, 4), round(float(p[1]) - soy, 4)) for p in pts_raw]
                if len(pts) >= 4:
                    poly = Polygon(pts)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if e.dxf.layer == "F.P.LINE" and poly.area > 400.0:
                        plot_boundary_poly = poly
                    elif e.dxf.layer == "A_ROAD" and poly.area > 100.0:
                        road_poly = poly
                    elif e.dxf.layer == "A_BUILT UP" and poly.area > 550.0:
                        basement_footprint_poly = poly
                    elif e.dxf.layer == "A_Wall" and len(pts_raw) >= 15:
                        ramp_wall_poly = poly

    for ins in msp.query('INSERT[name=="TR1"]'):
        px, py = float(ins.dxf.insert.x), float(ins.dxf.insert.y)
        if in_bbox(px, py, site_bbox):
            tree_positions.append([round(px - sox, 4), round(py - soy, 4)])

    # Assemble clean JSON structure
    if typical_slab_poly is None:
        raise RuntimeError("Failed to extract typical floor slab polygon from DXF.")

    sb = [round(float(v), 4) for v in typical_slab_poly.bounds]
    result: dict[str, Any] = {
        "metadata": {
            "source_dxf": dxf_path.name,
            "units": "metres",
            "footprint_width_m": round(sb[2] - sb[0], 4),
            "footprint_depth_m": round(sb[3] - sb[1], 4),
            "footprint_area_sqm": round(float(typical_slab_poly.area), 4),
            "num_residential_floors": config["heights"]["num_residential_floors"],
            "total_height_to_terrace_m": round(
                config["heights"]["stilt_floor_to_floor"]
                + 6 * config["heights"]["typical_floor_to_floor"]
                + config["heights"]["top_floor_to_terrace"],
                3,
            ),
            "total_height_with_ohwt_m": round(
                config["heights"]["stilt_floor_to_floor"]
                + 6 * config["heights"]["typical_floor_to_floor"]
                + config["heights"]["top_floor_to_terrace"]
                + config["heights"]["stair_cabin_height"]
                + config["heights"]["ohwt_height"],
                3,
            ),
        },
        "heights": config["heights"],
        "typical_floor": {
            "slab": poly_to_dict(typical_slab_poly),
            "columns": [poly_to_dict(c, {"id": f"col_{i+1}"}) for i, c in enumerate(columns_dedup)],
            "walls": [poly_to_dict(w, {"id": f"wall_{i+1}"}) for i, w in enumerate(wall_polygons)],
            "projections": [
                poly_to_dict(p, {"id": f"proj_{i+1}"}) for i, p in enumerate(proj_polygons)
            ],
            "windows": windows_out,
            "sliding_doors": sliding_out,
            "railings": [
                poly_to_dict(r, {"id": f"railing_{i+1}"}) for i, r in enumerate(railings_dedup)
            ],
            "doors": raw_doors,
            "stair_treads": raw_stair_treads,
            "ducts": raw_ducts,
            "room_labels": room_labels,
            "flats": flats_data,
        },
        "ground_floor": {
            "slab": poly_to_dict(gf_slab_poly if gf_slab_poly else typical_slab_poly),
            "core_walls": [
                poly_to_dict(w, {"id": f"gf_wall_{i+1}"}) for i, w in enumerate(gf_polys)
            ],
        },
        "terrace": {
            "stair_cabin_slab": poly_to_dict(stair_cabin_slab) if stair_cabin_slab else None,
            "walls_and_parapets": [
                poly_to_dict(w, {"id": f"terr_wall_{i+1}"}) for i, w in enumerate(terr_polys)
            ],
        },
        "facade_elevation": {
            "front_planter_zones_x": sorted(planter_zones_x),
        },
        "site": {
            "plot_boundary": poly_to_dict(plot_boundary_poly) if plot_boundary_poly else None,
            "main_road": poly_to_dict(road_poly) if road_poly else None,
            "basement_footprint": poly_to_dict(basement_footprint_poly)
            if basement_footprint_poly
            else None,
            "ramp_retaining_wall": poly_to_dict(ramp_wall_poly) if ramp_wall_poly else None,
            "trees": tree_positions,
        },
    }

    out_file = base_dir / output_path
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(
        f"[extract] Saved {out_file} | "
        f"Footprint: {result['metadata']['footprint_width_m']}m x {result['metadata']['footprint_depth_m']}m | "
        f"Columns: {len(columns_dedup)}, Walls: {len(wall_polygons)}, "
        f"Windows: {len(windows_out)}, Sliding: {len(sliding_out)}, "
        f"Projections: {len(proj_polygons)}, Trees: {len(tree_positions)}"
    )
    return result


if __name__ == "__main__":
    extract_geometry()
