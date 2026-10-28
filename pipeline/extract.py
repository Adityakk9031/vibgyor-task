"""
Stage 1: Extract clean 2D geometry JSON from SUBMISSION - 04.dxf.

Reads the architect's DXF file and config.json, expands nested blocks via
ezdxf's virtual_entities(), aligns each plan region into a unified building-relative
coordinate system in metres (where (0, 0) is the SW corner of the building
footprint bbox), reconstructs closed 2D polygons for walls, columns, slabs,
architectural projections, windows, sliding doors, railings, stairs, terrace
cabin, basement parking & curved ramp, stilt parking & entrance lobby, structured
room boundaries for Type A and Type B flats, and site/plot features, and writes
outputs/extracted_geometry.json.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import ezdxf
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
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


def extract_structured_rooms(
    room_labels: list[dict[str, Any]],
    walls_and_cols: list[Polygon],
    windows_out: list[dict[str, Any]],
    sliding_out: list[dict[str, Any]],
    doors_out: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Reconstructs wall-snapped 2D room bounding polygons for Type A, Type B, and Core
    directly from the DXF room text labels (e.g. 'DRAWING ROOM 6.53 x 3.65') and
    extracted interior/exterior wall faces, tagging each room's window/balcony/door walls
    so Stage 2 furniture placement is 100% geometry-driven.
    """
    x_edges: list[tuple[float, float, float]] = []
    y_edges: list[tuple[float, float, float]] = []
    for wp in walls_and_cols:
        b = wp.bounds
        w, d = b[2] - b[0], b[3] - b[1]
        if d > 0.35 and w < 0.45:
            x_edges.append((b[0], b[1], b[3]))
            x_edges.append((b[2], b[1], b[3]))
        if w > 0.35 and d < 0.45:
            y_edges.append((b[1], b[0], b[2]))
            y_edges.append((b[3], b[0], b[2]))

    def snap_room_box(rx: float, ry: float, rw: float, rd: float) -> list[float]:
        best_x = (rx - rw * 0.5, rx + rw * 0.5)
        best_x_err = 999.0
        cand_x0 = [x for x, y0, y1 in x_edges if x <= rx + 0.25 and y0 - 1.5 <= ry <= y1 + 1.5]
        cand_x1 = [x for x, y0, y1 in x_edges if x >= rx - 0.25 and y0 - 1.5 <= ry <= y1 + 1.5]
        for x0 in cand_x0:
            for x1 in cand_x1:
                err = abs((x1 - x0) - rw)
                if err < best_x_err and err < 0.35:
                    best_x_err = err
                    best_x = (x0, x1)

        best_y = (ry - rd * 0.5, ry + rd * 0.5)
        best_y_err = 999.0
        cand_y0 = [y for y, x0, x1 in y_edges if y <= ry + 0.25 and x0 - 1.5 <= rx <= x1 + 1.5]
        cand_y1 = [y for y, x0, x1 in y_edges if y >= ry - 0.25 and x0 - 1.5 <= rx <= x1 + 1.5]
        for y0 in cand_y0:
            for y1 in cand_y1:
                err = abs((y1 - y0) - rd)
                if err < best_y_err and err < 0.35:
                    best_y_err = err
                    best_y = (y0, y1)

        return [
            round(float(best_x[0]), 3),
            round(float(best_y[0]), 3),
            round(float(best_x[1]), 3),
            round(float(best_y[1]), 3),
        ]

    rooms_by_unit: dict[str, list[dict[str, Any]]] = {"type_a": [], "type_b": [], "core": []}

    for item in sorted(room_labels, key=lambda r: (r["position"][1], r["position"][0])):
        txt = item["text"]
        rx, ry = float(item["position"][0]), float(item["position"][1])
        m = re.search(r"([A-Z ./&]+?)\s+(\d+\.\d+)\s*x\s*(\d+\.\d+)", txt)
        if not m:
            continue
        raw_name = m.group(1).strip()
        rw, rd = float(m.group(2)), float(m.group(3))
        bbox = snap_room_box(rx, ry, rw, rd)
        rpoly = box(bbox[0], bbox[1], bbox[2], bbox[3])

        # Determine which walls of this room have windows, sliding doors, or entry doors
        ebuf = rpoly.buffer(0.32)
        room_openings: list[dict[str, Any]] = []
        for op in windows_out + sliding_out:
            op_pt = Point(op["centroid"][0], op["centroid"][1])
            if ebuf.contains(op_pt):
                ox, oy = op["centroid"]
                dists = {
                    "west": abs(ox - bbox[0]),
                    "east": abs(ox - bbox[2]),
                    "south": abs(oy - bbox[1]),
                    "north": abs(oy - bbox[3]),
                }
                wall_side = min(dists, key=dists.get)
                room_openings.append({"type": op["type"], "tag": op["tag"], "wall": wall_side, "centroid": [ox, oy]})

        for d_op in doors_out:
            d_pt = Point(d_op["midpoint"][0], d_op["midpoint"][1])
            if ebuf.contains(d_pt):
                dx, dy = d_op["midpoint"]
                dists = {
                    "west": abs(dx - bbox[0]),
                    "east": abs(dx - bbox[2]),
                    "south": abs(dy - bbox[1]),
                    "north": abs(dy - bbox[3]),
                }
                wall_side = min(dists, key=dists.get)
                room_openings.append({"type": "door", "wall": wall_side, "midpoint": [dx, dy]})

        unit_key = "type_a" if ry < 19.1 else ("core" if ry < 22.9 else "type_b")
        rooms_by_unit[unit_key].append(
            poly_to_dict(
                rpoly,
                {
                    "name": raw_name,
                    "full_label": txt,
                    "label_dimensions": [rw, rd],
                    "label_position": [rx, ry],
                    "unit": unit_key,
                    "openings": room_openings,
                },
            )
        )

    # Assign semantic room_role (e.g. master_bedroom, second_bedroom, third_bedroom, fourth_bedroom)
    for unit_key in ("type_a", "type_b"):
        bedrooms = [r for r in rooms_by_unit[unit_key] if "BED ROOM" in r["name"]]
        # Sort bedrooms by area descending so the largest bedroom is Master Bedroom
        bedrooms_sorted = sorted(bedrooms, key=lambda r: r["area"], reverse=True)
        role_names = ["master_bedroom", "second_bedroom", "third_bedroom", "fourth_bedroom"]
        for idx, br in enumerate(bedrooms_sorted):
            br["role"] = role_names[min(idx, len(role_names) - 1)]

        for r in rooms_by_unit[unit_key]:
            if "role" in r:
                continue
            nm = r["name"]
            if "DRAWING" in nm:
                r["role"] = "drawing_room"
            elif "KITCHEN" in nm:
                r["role"] = "kitchen_dining"
            elif "BALCONY" in nm:
                r["role"] = "main_balcony" if r["area"] > 5.0 else "front_balcony"
            elif "VESTIBULE" in nm:
                r["role"] = "vestibule"
            elif "FOYER" in nm:
                r["role"] = "foyer"
            elif "PUJA" in nm:
                r["role"] = "puja"
            elif "TOILET" in nm:
                r["role"] = "toilet"
            elif "WASH" in nm:
                r["role"] = "wash"
            elif "STORE" in nm:
                r["role"] = "store"
            else:
                r["role"] = nm.lower().replace(" ", "_")

    return rooms_by_unit


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

    def in_bbox(x: float, y: float, bbox: list[float]) -> bool:
        return bbox[0] <= x <= bbox[1] and bbox[2] <= y <= bbox[3]

    # -------------------------------------------------------------------------
    # 1. TYPICAL FLOOR PLAN (1st to 7th Floor)
    # -------------------------------------------------------------------------
    typ_bbox = regions_cfg["typical_floor_plan"]["bbox"]
    tox, toy = regions_cfg["typical_floor_plan"]["building_origin"]

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
    raw_thin_polys: list[Polygon] = []
    for p in all_closed_polys:
        if p.area <= 0.004 or p.length <= 0:
            continue
        thickness_est = 2.0 * p.area / p.length
        if thickness_est < 0.34 and p.area < 3.5:
            raw_thin_polys.append(p)
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

    # Extract wall-snapped room polygons for Type A, Type B, and Core
    structured_rooms = extract_structured_rooms(
        room_labels, raw_thin_polys, windows_out, sliding_out, raw_doors
    )

    # -------------------------------------------------------------------------
    # 2. RERA CARPET POLYGONS (Type A, Type B, Balconies, Foyer)
    # -------------------------------------------------------------------------
    rera_cfg = regions_cfg["rera_carpet_plan"]
    rera_blk = doc.blocks.get(rera_cfg["block_name"])
    y_off_rera = float(rera_cfg["y_offset_in_block"])
    flats_data: dict[str, Any] = {
        "type_a": None,
        "type_b": None,
        "balconies": [],
        "rooms": structured_rooms,
    }
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
                                "rooms": structured_rooms["type_a"],
                            },
                        )
                    elif poly.area > 130.0:
                        flats_data["type_b"] = poly_to_dict(
                            poly,
                            {
                                "name": "Type B (Rear 4BHK)",
                                "units": [f"{f}02" for f in range(1, 8)],
                                "rera_carpet_area_sqm": 143.18,
                                "rooms": structured_rooms["type_b"],
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
    # 3. BASEMENT PARKING PLAN (z = -3.15m to 0.0m)
    # -------------------------------------------------------------------------
    bsm_bbox = regions_cfg["basement_plan"]["bbox"]
    box_x, box_y = regions_cfg["basement_plan"]["building_origin"]
    bsm_slab_poly: Polygon | None = None
    bsm_ramp_polys: list[Polygon] = []
    bsm_cols: list[Polygon] = []
    bsm_car_bays: list[Polygon] = []
    bsm_scooter_bays: list[Polygon] = []
    bsm_parking_zones: list[Polygon] = []
    bsm_wall_lines: list[LineString] = []

    for e in leaves:
        etype = e.dxftype()
        lyr = e.dxf.layer
        if etype == "LINE":
            sx, sy = float(e.dxf.start.x), float(e.dxf.start.y)
            ex, ey = float(e.dxf.end.x), float(e.dxf.end.y)
            if in_bbox((sx + ex) * 0.5, (sy + ey) * 0.5, bsm_bbox):
                p1 = (round(sx - box_x, 4), round(sy - box_y, 4))
                p2 = (round(ex - box_x, 4), round(ey - box_y, 4))
                if p1 != p2 and lyr in ("A_Wall", "g-r.c.c"):
                    bsm_wall_lines.append(LineString([p1, p2]))
        elif etype == "LWPOLYLINE":
            pts_raw = list(e.get_points())
            if not pts_raw:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, bsm_bbox):
                pts = [
                    (round(float(p[0]) - box_x, 4), round(float(p[1]) - box_y, 4))
                    for p in pts_raw
                ]
                if e.closed and pts[0] != pts[-1]:
                    pts.append(pts[0])
                if len(pts) >= 2 and lyr in ("A_Wall", "g-r.c.c"):
                    bsm_wall_lines.append(LineString(pts))
                if len(pts) >= 4:
                    poly = Polygon(pts)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if isinstance(poly, Polygon) and poly.area > 0.05:
                        if lyr == "A_BUILT UP" and poly.area > 500.0:
                            bsm_slab_poly = poly
                        elif lyr == "g-r.c.c" and poly.area < 1.5:
                            bsm_cols.append(poly)
                        elif lyr == "A_CAR" and len(pts_raw) == 4:
                            bsm_car_bays.append(poly)
                        elif lyr == "A_SCOOTER" and len(pts_raw) == 4:
                            bsm_scooter_bays.append(poly)
                        elif lyr == "A_PARKING" and len(pts_raw) == 4:
                            bsm_parking_zones.append(poly)
                        elif lyr == "A_RAMP" and poly.area > 10.0:
                            bsm_ramp_polys.append(poly)

    bsm_cols_dedup = dedup_polygons(bsm_cols, tol=0.05)
    bsm_car_dedup = dedup_polygons(bsm_car_bays, tol=0.10)
    bsm_scooter_dedup = dedup_polygons(bsm_scooter_bays, tol=0.10)

    # -------------------------------------------------------------------------
    # 4. GROUND FLOOR (STILT PARKING & ENTRANCE LOBBY) PLAN
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

    # Also extract Stilt Parking car bays & scooter bays from gf_parking_plan
    gfp_bbox = regions_cfg["gf_parking_plan"]["bbox"]
    gpox, gpoy = regions_cfg["gf_parking_plan"]["building_origin"]
    gf_car_bays: list[Polygon] = []
    gf_scooter_bays: list[Polygon] = []
    gf_parking_zones: list[Polygon] = []
    for e in leaves:
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in ("A_CAR", "A_SCOOTER", "A_PARKING"):
            pts_raw = list(e.get_points())
            if len(pts_raw) != 4:
                continue
            cx = sum(p[0] for p in pts_raw) / len(pts_raw)
            cy = sum(p[1] for p in pts_raw) / len(pts_raw)
            if in_bbox(cx, cy, gfp_bbox):
                pts = [
                    (round(float(p[0]) - gpox, 4), round(float(p[1]) - gpoy, 4))
                    for p in pts_raw
                ]
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if isinstance(poly, Polygon) and poly.area > 0.5:
                    if e.dxf.layer == "A_CAR" and poly.area > 8.0:
                        gf_car_bays.append(poly)
                    elif e.dxf.layer == "A_SCOOTER":
                        gf_scooter_bays.append(poly)
                    elif e.dxf.layer == "A_PARKING":
                        gf_parking_zones.append(poly)

    gf_car_dedup = dedup_polygons(gf_car_bays, tol=0.10)
    gf_scooter_dedup = dedup_polygons(gf_scooter_bays, tol=0.10)

    # Entrance lobby polygon on Ground Floor (FOYER 4.40 x 3.99 adjacent to lifts at x=[4.27, 8.97], y=[19.09, 23.08])
    entrance_lobby_poly = box(4.265, 19.094, 8.965, 23.084)

    # -------------------------------------------------------------------------
    # 5. TERRACE & STAIR CABIN PLAN
    # -------------------------------------------------------------------------
    terr_bbox = regions_cfg["terrace_plan"]["bbox"]
    trox, troy = regions_cfg["terrace_plan"]["building_origin"]
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

    # Terrace Amenity Zones derived from Terrace Plan open deck (south & north of central core):
    # - South Deck (y in [1.5, 18.5], x in [1.8, 12.9]): Pergola Seating Lounge + Kids' Play Area
    # - North Deck (y in [23.5, 38.4], x in [0.3, 10.1]): Terrace Fitness Gym Pavilion + Yoga Deck
    terrace_amenity_zones = {
        "pergola_seating": poly_to_dict(
            box(2.10, 13.50, 12.60, 18.60),
            {"name": "Terrace Pergola Seating Lounge", "deck": "south"},
        ),
        "kids_play_area": poly_to_dict(
            box(2.40, 3.80, 12.50, 13.20),
            {"name": "Terrace Kids' Play Area", "deck": "south"},
        ),
        "terrace_gym": poly_to_dict(
            box(2.00, 26.20, 9.60, 36.80),
            {"name": "Terrace Fitness Gym Pavilion", "deck": "north"},
        ),
        "yoga_deck": poly_to_dict(
            box(0.25, 24.00, 2.00, 37.80),
            {"name": "Terrace Wooden Yoga & Wellness Deck", "deck": "north"},
        ),
    }

    # -------------------------------------------------------------------------
    # 6. FRONT ELEVATION FACADE DETAILING
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
    # 7. SITE / LAYOUT PLAN (Plot boundary, road, basement ramp, trees)
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
        "basement": {
            "slab": poly_to_dict(bsm_slab_poly if bsm_slab_poly else (basement_footprint_poly or typical_slab_poly)),
            "columns": [poly_to_dict(c, {"id": f"bsm_col_{i+1}"}) for i, c in enumerate(bsm_cols_dedup)],
            "car_bays": [poly_to_dict(b, {"id": f"bsm_car_{i+1}"}) for i, b in enumerate(bsm_car_dedup)],
            "scooter_bays": [
                poly_to_dict(s, {"id": f"bsm_scooter_{i+1}"}) for i, s in enumerate(bsm_scooter_dedup)
            ],
            "parking_zones": [
                poly_to_dict(z, {"id": f"bsm_zone_{i+1}"}) for i, z in enumerate(bsm_parking_zones)
            ],
            "ramp_zones": [poly_to_dict(r, {"id": f"bsm_ramp_{i+1}"}) for i, r in enumerate(bsm_ramp_polys)],
        },
        "ground_floor": {
            "slab": poly_to_dict(gf_slab_poly if gf_slab_poly else typical_slab_poly),
            "core_walls": [
                poly_to_dict(w, {"id": f"gf_wall_{i+1}"}) for i, w in enumerate(gf_polys)
            ],
            "entrance_lobby": poly_to_dict(
                entrance_lobby_poly, {"name": "Ground Floor Entrance Lobby & Lift Foyer"}
            ),
            "car_bays": [poly_to_dict(b, {"id": f"gf_car_{i+1}"}) for i, b in enumerate(gf_car_dedup)],
            "scooter_bays": [
                poly_to_dict(s, {"id": f"gf_scooter_{i+1}"}) for i, s in enumerate(gf_scooter_dedup)
            ],
            "parking_zones": [
                poly_to_dict(z, {"id": f"gf_zone_{i+1}"}) for i, z in enumerate(gf_parking_zones)
            ],
        },
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
        "terrace": {
            "stair_cabin_slab": poly_to_dict(stair_cabin_slab) if stair_cabin_slab else None,
            "walls_and_parapets": [
                poly_to_dict(w, {"id": f"terr_wall_{i+1}"}) for i, w in enumerate(terr_polys)
            ],
            "amenity_zones": terrace_amenity_zones,
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
        f"TypeA Rooms: {len(structured_rooms['type_a'])}, TypeB Rooms: {len(structured_rooms['type_b'])}, "
        f"Basement Bays: {len(bsm_car_dedup)} car + {len(bsm_scooter_dedup)} two-wheeler, "
        f"Stilt Bays: {len(gf_car_dedup)} car + {len(gf_scooter_dedup)} two-wheeler"
    )
    return result


if __name__ == "__main__":
    extract_geometry()
