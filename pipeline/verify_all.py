"""
pipeline/verify_all.py

Verifies:
1. All 20 still images (2560x1440) in outputs/ and viewer/. These are AI concept stills made from text
   prompts (look and feel only, not to the exact layout); the viewer labels them that way.
2. All 16 equirectangular panoramas (6144x3072) in outputs/panoramas/ and viewer/panoramas/,
   with a continuous 360° wrap: pixel column 0 matches column width-1
3. Provenance of the 360° tour: every panorama is listed in outputs/ai_manifest.json (written by
   pipeline/import_ai_results.py), is byte-identical to the imported AI result, was made from a Blender
   render of the CAD-derived model, and keeps that render's layout (layout_match >= 0.30)
4. viewer/index.html tour sub-modes and cache-busting hooks
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

MIN_LAYOUT_MATCH = 0.30

STILLS = [
    ("outputs/shot_1_eye_level_day.png", "viewer/exteriors/shot_1_eye_level_day.png"),
    ("outputs/shot_2_front_corner_dusk.png", "viewer/exteriors/shot_2_front_corner_dusk.png"),
    ("outputs/shot_3_aerial_day.png", "viewer/exteriors/shot_3_aerial_day.png"),
    ("outputs/shot_4_entrance_closeup.png", "viewer/exteriors/shot_4_entrance_closeup.png"),
    ("outputs/amenities/amenity_1_basement_parking.png", "viewer/amenities/amenity_1_basement_parking.png"),
    ("outputs/amenities/amenity_2_stilt_parking.png", "viewer/amenities/amenity_2_stilt_parking.png"),
    ("outputs/amenities/amenity_3_entrance_lobby.png", "viewer/amenities/amenity_3_entrance_lobby.png"),
    ("outputs/amenities/amenity_4_landscape_drive.png", "viewer/amenities/amenity_4_landscape_drive.png"),
    ("outputs/amenities/amenity_5_terrace_amenities.png", "viewer/amenities/amenity_5_terrace_amenities.png"),
    ("outputs/amenities/amenity_6_terrace_gym.png", "viewer/amenities/amenity_6_terrace_gym.png"),
    ("outputs/interiors/type_a_1_drawing_room.png", "viewer/interiors/type_a_1_drawing_room.png"),
    ("outputs/interiors/type_a_2_kitchen_dining.png", "viewer/interiors/type_a_2_kitchen_dining.png"),
    ("outputs/interiors/type_a_3_master_bedroom.png", "viewer/interiors/type_a_3_master_bedroom.png"),
    ("outputs/interiors/type_a_4_second_bedroom.png", "viewer/interiors/type_a_4_second_bedroom.png"),
    ("outputs/interiors/type_a_5_third_bedroom.png", "viewer/interiors/type_a_5_third_bedroom.png"),
    ("outputs/interiors/type_b_1_drawing_room.png", "viewer/interiors/type_b_1_drawing_room.png"),
    ("outputs/interiors/type_b_2_kitchen_dining.png", "viewer/interiors/type_b_2_kitchen_dining.png"),
    ("outputs/interiors/type_b_3_master_bedroom.png", "viewer/interiors/type_b_3_master_bedroom.png"),
    ("outputs/interiors/type_b_4_second_bedroom.png", "viewer/interiors/type_b_4_second_bedroom.png"),
    ("outputs/interiors/type_b_5_third_bedroom.png", "viewer/interiors/type_b_5_third_bedroom.png"),
]

PANOS = [
    "pano_bldg_1_entrance_gate",
    "pano_bldg_2_entrance_lobby",
    "pano_bldg_3_basement_parking",
    "pano_bldg_4_garden_stilt",
    "pano_bldg_5_terrace_pergola_kids",
    "pano_bldg_6_terrace_gym",
    "pano_type_a_1_drawing_room",
    "pano_type_a_2_dining_kitchen",
    "pano_type_a_3_master_bedroom",
    "pano_type_a_4_second_bedroom",
    "pano_type_a_5_balcony_deck",
    "pano_type_b_1_drawing_room",
    "pano_type_b_2_dining_kitchen",
    "pano_type_b_3_master_bedroom",
    "pano_type_b_4_second_bedroom",
    "pano_type_b_5_balcony_deck",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_provenance(job_id: str, files: list[Path], items: dict) -> str:
    item = items.get(job_id)
    assert item, f"{job_id}: not in outputs/ai_manifest.json (not made from the model; run the AI finishing pass)"
    for f in files:
        assert _sha256(f) == item["output_sha256"], f"{f}: differs from the imported AI result"
    assert item["layout_match"] >= MIN_LAYOUT_MATCH, f"{job_id}: layout match {item['layout_match']} too low"
    return f"layout {item['layout_match']:.2f}"


def main():
    print("==================================================")
    print(" VIBGYOR ARCHITECTURAL PIPELINE VERIFICATION")
    print("==================================================")

    manifest_path = Path("outputs/ai_manifest.json")
    assert manifest_path.exists(), "outputs/ai_manifest.json missing: run python -m pipeline.import_ai_results"
    manifest = json.loads(manifest_path.read_text())
    assert not manifest.get("dry_run"), "ai_manifest.json comes from a dry run"
    items = manifest["items"]

    provenance_path = Path("viewer/provenance.json")
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    for image_id, label in provenance.items():
        assert label != "model" or image_id in items, f"viewer labels {image_id} as model-based but it is not in the manifest"

    print(f"\n1. Checking {len(STILLS)} Stills (2560x1440 PNG; model-based where imported, otherwise AI concept)...")
    for out_p, view_p in STILLS:
        p1, p2 = Path(out_p), Path(view_p)
        assert p1.exists(), f"Missing {out_p}"
        assert p2.exists(), f"Missing {view_p}"
        im = Image.open(p1)
        assert im.size == (2560, 1440), f"Size mismatch for {out_p}: {im.size}"
        if provenance.get(p1.stem) == "model":
            prov = check_provenance(p1.stem, [p1, p2], items)
        else:
            prov = "AI concept (labelled in viewer)"
        print(f"  [OK] {p1.name:36s} | {im.size[0]}x{im.size[1]} | {prov} | {p1.stat().st_size // 1024} KB")

    print(f"\n2. Checking {len(PANOS)} Equirectangular Panoramas (6144x3072 PNG, rendered from the model)...")
    for pano_id in PANOS:
        p1 = Path(f"outputs/panoramas/{pano_id}.png")
        p2 = Path(f"viewer/panoramas/{pano_id}.png")
        assert p1.exists(), f"Missing {p1}"
        assert p2.exists(), f"Missing {p2}"
        im = Image.open(p1)
        assert im.size == (6144, 3072), f"Size mismatch for {p1}: {im.size}"
        # Seam continuity check (signed int16 to avoid uint8 underflow)
        arr = np.array(im.convert("RGB"), dtype=np.int16)
        seam_mean = float(np.mean(np.abs(arr[:, 0, :] - arr[:, -1, :])))
        assert seam_mean < 5.0, f"Seam mismatch on {pano_id}: mean={seam_mean:.2f}"
        prov = check_provenance(pano_id, [p1, p2], items)
        print(f"  [OK] {p1.name:36s} | {im.size[0]}x{im.size[1]} | Seam Mean: {seam_mean:.2f} | {prov}")

    print("\n3. Checking viewer/index.html...")
    html = Path("viewer/index.html").read_text(encoding="utf-8")
    for hook in ('id="spot-view-container"', 'id="spot-hotspots-overlay"', "btn-submode-spot", "btn-submode-sphere",
                 "ASSET_VERSION", "setTourSubMode", "rebuildSpotHotspots"):
        assert hook in html, f"viewer/index.html is missing {hook}"
    print("  [OK] viewer/index.html tour sub-modes, cache-busting & JS hooks validated")

    print("\n==================================================")
    model_stills = sum(provenance.get(Path(o).stem) == "model" for o, _ in STILLS)
    print(f" {len(PANOS)} 360° PANORAMAS + {model_stills} STILLS VERIFIED AS MADE FROM THE 3D MODEL; "
          f"{len(STILLS) - model_stills} STILLS ARE LABELLED AI CONCEPT")
    print("==================================================")


if __name__ == "__main__":
    main()
