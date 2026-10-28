"""
Unit tests for Stage 1 (pipeline/extract.py) verifying that all dimensions,
floor plans, structural columns, walls, openings, RERA carpet areas, and
landscape elements are accurately extracted from SUBMISSION - 04.dxf.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from pipeline.extract import extract_geometry, load_config, resolve_dxf_path


@pytest.fixture(scope="module")
def extracted_data(tmp_path_factory):
    out_json = tmp_path_factory.mktemp("outputs") / "extracted_geometry.json"
    return extract_geometry(config_path="config.json", output_path=out_json)


def test_dxf_resolution():
    cfg = load_config("config.json")
    dxf_path = resolve_dxf_path(cfg, Path("."))
    assert dxf_path.exists()
    assert dxf_path.suffix.lower() == ".dxf"


def test_building_footprint_dimensions(extracted_data):
    """Verifies the real building footprint matches the 13.12m x 38.73m DWG truth."""
    meta = extracted_data["metadata"]
    assert meta["units"] == "metres"
    assert meta["footprint_width_m"] == pytest.approx(13.12, abs=0.02)
    assert meta["footprint_depth_m"] == pytest.approx(38.733, abs=0.02)
    # Net built-up area on typical floor in DXF area calculation table is 398.59 sq.m
    assert meta["footprint_area_sqm"] == pytest.approx(398.59, abs=0.5)


def test_vertical_heights_from_section(extracted_data):
    """Verifies floor-to-floor heights and total heights match Section A-A."""
    meta = extracted_data["metadata"]
    heights = extracted_data["heights"]
    assert meta["num_residential_floors"] == 7
    assert heights["stilt_floor_to_floor"] == pytest.approx(3.30, abs=0.01)
    assert heights["typical_floor_to_floor"] == pytest.approx(3.05, abs=0.01)
    assert heights["top_floor_to_terrace"] == pytest.approx(3.10, abs=0.01)
    assert heights["slab_thickness"] == pytest.approx(0.15, abs=0.01)
    # Stilt (3.30) + 6 * Typical (18.30) + 7th (3.10) = 24.70m to terrace
    assert meta["total_height_to_terrace_m"] == pytest.approx(24.70, abs=0.05)


def test_structural_columns_and_walls(extracted_data):
    """Verifies structural columns (23 on COLUMN_BSE) and wall polygons are extracted."""
    typ = extracted_data["typical_floor"]
    assert len(typ["columns"]) == 23
    assert len(typ["walls"]) >= 45
    assert len(typ["projections"]) >= 20

    # Every column and wall must have positive area and valid polygon coordinates
    for col in typ["columns"]:
        assert col["area"] > 0.15
        assert len(col["polygon"]) >= 4
    for wall in typ["walls"]:
        assert wall["area"] > 0.004
        assert len(wall["polygon"]) >= 3


def test_openings_and_balconies(extracted_data):
    """Verifies windows, sliding doors, interior doors, and railings are extracted."""
    typ = extracted_data["typical_floor"]
    assert len(typ["windows"]) == 10
    assert len(typ["sliding_doors"]) == 16
    assert len(typ["doors"]) == 21
    assert len(typ["railings"]) == 6

    # Check bathroom ventilators (on A_WINDOW) vs main windows & sliding doors (on g-dw)
    ventilators = [w for w in typ["windows"] if w["type"] == "ventilator"]
    large_windows = [s for s in typ["sliding_doors"] if s["type"] == "large_window"]
    sliding_doors = [s for s in typ["sliding_doors"] if s["type"] == "sliding_door"]
    assert len(ventilators) == 10
    assert len(large_windows) >= 6
    assert len(sliding_doors) >= 4
    for v in ventilators:
        assert v["sill_height"] > 1.2
    for lw in large_windows:
        assert lw["sill_height"] == pytest.approx(0.90, abs=0.05)
    for sd in sliding_doors:
        assert sd["sill_height"] == pytest.approx(0.0, abs=0.05)


def test_rera_carpet_flats_type_a_and_type_b(extracted_data):
    """Verifies Type A (front, 160.05 sqm) and Type B (rear, 143.18 sqm) flats."""
    flats = extracted_data["typical_floor"]["flats"]
    type_a = flats["type_a"]
    type_b = flats["type_b"]
    assert type_a is not None
    assert type_b is not None
    assert type_a["area"] == pytest.approx(160.05, abs=0.5)
    assert type_b["area"] == pytest.approx(143.18, abs=0.5)
    # Type A sits at the front (south, smaller Y centroid) and Type B at the rear (north, larger Y centroid)
    assert type_a["centroid"][1] < type_b["centroid"][1]
    assert len(flats["balconies"]) == 6


def test_site_and_landscape_extraction(extracted_data):
    """Verifies plot boundary, 18m main road, and 25 landscape trees are extracted."""
    site = extracted_data["site"]
    assert site["plot_boundary"] is not None
    assert site["plot_boundary"]["area"] > 600.0
    assert site["main_road"] is not None
    assert site["main_road"]["area"] > 150.0
    assert len(site["trees"]) == 25


def test_level2_basement_parking_extraction(extracted_data):
    """Verifies Basement Plan extraction: slab, columns, car bays, scooter/two-wheeler bays, and ramp."""
    bsm = extracted_data["basement"]
    assert bsm["slab"] is not None
    assert bsm["slab"]["area"] > 500.0
    assert len(bsm["columns"]) >= 25
    assert len(bsm["car_bays"]) >= 2
    assert len(bsm["scooter_bays"]) >= 18
    assert len(bsm["ramp_zones"]) >= 1


def test_level2_stilt_and_entrance_lobby_extraction(extracted_data):
    """Verifies Ground Floor Stilt Parking (car bays, scooter bays) and Entrance Lobby."""
    ground = extracted_data["ground_floor"]
    assert ground["slab"] is not None
    assert len(ground["car_bays"]) >= 5
    assert len(ground["scooter_bays"]) >= 12
    assert ground["entrance_lobby"] is not None
    assert ground["entrance_lobby"]["area"] > 15.0


def test_level2_terrace_amenities_extraction(extracted_data):
    """Verifies Terrace Plan and Level 2 Terrace Amenity Zones (pergola, kids play, gym)."""
    terrace = extracted_data["terrace"]
    assert terrace["stair_cabin_slab"] is not None
    assert len(terrace["walls_and_parapets"]) >= 10
    zones = terrace["amenity_zones"]
    assert "pergola_seating" in zones
    assert "kids_play_area" in zones
    assert "terrace_gym" in zones
    for zname in ("pergola_seating", "kids_play_area", "terrace_gym"):
        b = zones[zname]["bounds"]
        assert len(b) == 4
        assert b[2] > b[0] and b[3] > b[1]


def test_level2_structured_rooms_type_a_and_type_b(extracted_data):
    """Verifies wall-snapped room bounding boxes and semantic roles for Type A and Type B flats."""
    flats = extracted_data["typical_floor"]["flats"]
    rooms_a = flats["type_a"]["rooms"]
    rooms_b = flats["type_b"]["rooms"]
    assert len(rooms_a) >= 15
    assert len(rooms_b) >= 15

    roles_a = {r["role"] for r in rooms_a}
    roles_b = {r["role"] for r in rooms_b}
    for req_role in ("drawing_room", "kitchen_dining", "master_bedroom", "second_bedroom", "main_balcony"):
        assert req_role in roles_a
        assert req_role in roles_b

    # Verify Type A Drawing Room dimensions match 6.53m x 3.65m DWG callout
    dr_a = next(r for r in rooms_a if r["role"] == "drawing_room")
    assert dr_a["label_dimensions"][0] == pytest.approx(6.53, abs=0.05)
    assert dr_a["label_dimensions"][1] == pytest.approx(3.65, abs=0.05)

    # Verify Type B Drawing Room dimensions match 6.31m x 3.65m DWG callout
    dr_b = next(r for r in rooms_b if r["role"] == "drawing_room")
    assert dr_b["label_dimensions"][0] == pytest.approx(6.31, abs=0.05)
    assert dr_b["label_dimensions"][1] == pytest.approx(3.65, abs=0.05)

