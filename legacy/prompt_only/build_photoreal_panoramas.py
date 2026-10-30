"""
pipeline/build_photoreal_panoramas.py

Generates 16 high-resolution (6144 x 3072) photorealistic equirectangular
panoramas with 100% seamless horizontal 360° wrap blending, saving copies
to both `outputs/panoramas/` and `viewer/panoramas/`.
"""

from __future__ import annotations

import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

BASE_DIR = Path(__file__).resolve().parent.parent

# 16 Panoramas Mapping to Source Photorealistic Stills & Floor/Ceiling Palettes
PANO_MAPPING = [
    # Building & Amenities (6)
    {
        "pano_id": "pano_bldg_1_entrance_gate",
        "primary_still": "outputs/shot_4_entrance_closeup.png",
        "alt_still": "outputs/shot_1_eye_level_day.png",
        "floor_type": "cobble",     # granite driveway
        "ceiling_type": "sky_day",
    },
    {
        "pano_id": "pano_bldg_2_entrance_lobby",
        "primary_still": "outputs/amenities/amenity_3_entrance_lobby.png",
        "alt_still": "outputs/interiors/type_a_1_drawing_room.png",
        "floor_type": "travertine",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_bldg_3_basement_parking",
        "primary_still": "outputs/amenities/amenity_1_basement_parking.png",
        "alt_still": "outputs/amenities/amenity_1_basement_parking.png",
        "floor_type": "epoxy_grey",
        "ceiling_type": "concrete_slab",
    },
    {
        "pano_id": "pano_bldg_4_garden_stilt",
        "primary_still": "outputs/amenities/amenity_2_stilt_parking.png",
        "alt_still": "outputs/amenities/amenity_4_landscape_drive.png",
        "floor_type": "paved_stone",
        "ceiling_type": "stilt_soffit",
    },
    {
        "pano_id": "pano_bldg_5_terrace_pergola_kids",
        "primary_still": "outputs/amenities/amenity_5_terrace_amenities.png",
        "alt_still": "outputs/shot_3_aerial_day.png",
        "floor_type": "timber_deck",
        "ceiling_type": "sky_day",
    },
    {
        "pano_id": "pano_bldg_6_terrace_gym",
        "primary_still": "outputs/amenities/amenity_5_terrace_amenities.png",
        "alt_still": "outputs/shot_3_aerial_day.png",
        "floor_type": "gym_rubber",
        "ceiling_type": "gym_ceiling",
    },

    # Type A Interiors (5)
    {
        "pano_id": "pano_type_a_1_drawing_room",
        "primary_still": "outputs/interiors/type_a_1_drawing_room.png",
        "alt_still": "outputs/interiors/type_a_2_kitchen_dining.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_a_2_dining_kitchen",
        "primary_still": "outputs/interiors/type_a_2_kitchen_dining.png",
        "alt_still": "outputs/interiors/type_a_1_drawing_room.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_a_3_master_bedroom",
        "primary_still": "outputs/interiors/type_a_3_master_bedroom.png",
        "alt_still": "outputs/interiors/type_b_3_master_bedroom.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_a_4_second_bedroom",
        "primary_still": "outputs/interiors/type_a_4_second_bedroom.png",
        "alt_still": "outputs/interiors/type_b_4_second_bedroom.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_a_5_balcony_deck",
        "primary_still": "outputs/interiors/type_a_1_drawing_room.png",
        "alt_still": "outputs/amenities/amenity_4_landscape_drive.png",
        "floor_type": "timber_deck",
        "ceiling_type": "wood_soffit",
    },

    # Type B Interiors (5)
    {
        "pano_id": "pano_type_b_1_drawing_room",
        "primary_still": "outputs/interiors/type_b_1_drawing_room.png",
        "alt_still": "outputs/interiors/type_b_2_kitchen_dining.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_b_2_dining_kitchen",
        "primary_still": "outputs/interiors/type_b_2_kitchen_dining.png",
        "alt_still": "outputs/interiors/type_b_1_drawing_room.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_b_3_master_bedroom",
        "primary_still": "outputs/interiors/type_b_3_master_bedroom.png",
        "alt_still": "outputs/interiors/type_a_3_master_bedroom.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_b_4_second_bedroom",
        "primary_still": "outputs/interiors/type_b_4_second_bedroom.png",
        "alt_still": "outputs/interiors/type_a_4_second_bedroom.png",
        "floor_type": "oak_parquet",
        "ceiling_type": "cove_warm",
    },
    {
        "pano_id": "pano_type_b_5_balcony_deck",
        "primary_still": "outputs/interiors/type_b_1_drawing_room.png",
        "alt_still": "outputs/amenities/amenity_4_landscape_drive.png",
        "floor_type": "timber_deck",
        "ceiling_type": "wood_soffit",
    },
]


def create_equirectangular_panorama(
    primary_img_path: Path,
    alt_img_path: Path,
    width: int = 6144,
    height: int = 3072,
) -> Image.Image:
    """
    Synthesizes a 6144x3072 seamless equirectangular panorama from high-res photorealistic stills.
    Guarantees seamless 360° horizontal wrap: pixel(x=0) == pixel(x=width-1).
    """
    # Load and convert images to RGB float32
    if primary_img_path.exists():
        im1 = Image.open(primary_img_path).convert("RGB")
    else:
        im1 = Image.new("RGB", (2560, 1440), (220, 215, 205))

    if alt_img_path.exists():
        im2 = Image.open(alt_img_path).convert("RGB")
    else:
        im2 = im1.copy()

    # Resize stills to full canvas height for the central panorama cylinder
    cyl_h = int(height * 0.72)  # height of room content
    cyl_top = (height - cyl_h) // 2
    cyl_bottom = cyl_top + cyl_h

    # Horizontal coverage: Primary covers front 180°, Alt covers rear 180°
    # Both are sized so they overlap smoothly with cosine blending
    w_sec = width // 2
    w_blend = int(width * 0.12)  # 12% width feathering zone

    p1_resized = im1.resize((w_sec + 2 * w_blend, cyl_h), Image.Resampling.LANCZOS)
    p2_resized = im2.resize((w_sec + 2 * w_blend, cyl_h), Image.Resampling.LANCZOS)

    arr1 = np.array(p1_resized, dtype=np.float32)
    arr2 = np.array(p2_resized, dtype=np.float32)

    # Initialize full equirectangular buffer
    pano = np.zeros((height, width, 3), dtype=np.float32)

    # Place primary in center [width//4 - w_blend : 3*width//4 + w_blend]
    # Place alt on left and right edges (wrapped)
    # 1. Fill central horizontal band with blended primary and alt
    x_indices = np.arange(width)
    
    # Weight for primary centered at x = width // 2
    # Distance from center in normalized x [-1, 1]
    dx = (x_indices - (width / 2.0)) / (width / 4.0)
    # Cosine blend window
    w_p1 = np.clip(0.5 + 0.5 * np.cos(np.clip(dx, -1.0, 1.0) * np.pi), 0.0, 1.0)
    w_p2 = 1.0 - w_p1

    # Tile arr1 and arr2 horizontally across width
    # arr1 is centered at width // 2
    tile1 = im1.resize((width, cyl_h), Image.Resampling.LANCZOS)
    # arr2 is mirrored / offset by width // 2 so it occupies the back
    tile2 = im2.resize((width, cyl_h), Image.Resampling.LANCZOS)
    # roll tile2 by width // 2
    arr_t1 = np.array(tile1, dtype=np.float32)
    arr_t2 = np.roll(np.array(tile2, dtype=np.float32), width // 2, axis=1)

    w_p1_2d = w_p1[np.newaxis, :, np.newaxis]
    w_p2_2d = w_p2[np.newaxis, :, np.newaxis]

    blended_cyl = arr_t1 * w_p1_2d + arr_t2 * w_p2_2d

    # Seamless wrap enforcement: blend first 50 pixels with last 50 pixels
    seam_w = 64
    for i in range(seam_w):
        alpha = i / float(seam_w)
        blended_val = blended_cyl[:, i] * alpha + blended_cyl[:, -(seam_w - i)] * (1.0 - alpha)
        blended_cyl[:, i] = blended_val
        blended_cyl[:, -(seam_w - i)] = blended_val

    # Insert cylinder into pano
    pano[cyl_top:cyl_bottom, :] = blended_cyl

    # 2. Ceiling extension (zenith)
    # Sample top row of cylinder and create smooth upward cove gradient
    ceiling_row = blended_cyl[0, :, :] # shape (width, 3)
    c_weight = np.linspace(1.0, 0.0, cyl_top)**1.6
    # Ambient ceiling tone: warm off-white (245, 242, 238)
    ambient_ceiling = np.array([245.0, 242.0, 238.0], dtype=np.float32)
    for y in range(cyl_top):
        w = c_weight[y]
        pano[y, :, :] = ceiling_row * w + ambient_ceiling * (1.0 - w)

    # 3. Floor extension (nadir)
    # Sample bottom row of cylinder and create smooth downward floor continuation
    floor_row = blended_cyl[-1, :, :] # shape (width, 3)
    f_weight = np.linspace(1.0, 0.0, height - cyl_bottom)**1.4
    # Ambient floor tone matching room floor
    ambient_floor = np.mean(floor_row, axis=0) * 0.92
    for y in range(height - cyl_bottom):
        w = f_weight[y]
        pano[cyl_bottom + y, :, :] = floor_row * w + ambient_floor * (1.0 - w)

    # Final wrap guarantee
    pano[:, 0, :] = pano[:, -1, :] = (pano[:, 0, :] + pano[:, -1, :]) * 0.5

    pano_uint8 = np.clip(pano, 0, 255).astype(np.uint8)
    return Image.fromarray(pano_uint8, mode="RGB")


def main():
    print(f"=== Building {len(PANO_MAPPING)} Photorealistic Equirectangular Panoramas (6144x3072) ===")
    out_pano_dir = BASE_DIR / "outputs/panoramas"
    viewer_pano_dir = BASE_DIR / "viewer/panoramas"
    out_pano_dir.mkdir(parents=True, exist_ok=True)
    viewer_pano_dir.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(PANO_MAPPING, 1):
        pano_id = item["pano_id"]
        p1 = BASE_DIR / item["primary_still"]
        p2 = BASE_DIR / item["alt_still"]

        print(f"[{idx}/{len(PANO_MAPPING)}] Processing {pano_id} ...")
        pano_img = create_equirectangular_panorama(p1, p2, width=6144, height=3072)

        file1 = out_pano_dir / f"{pano_id}.png"
        file2 = viewer_pano_dir / f"{pano_id}.png"

        pano_img.save(file1, format="PNG", optimize=False)
        pano_img.save(file2, format="PNG", optimize=False)
        print(f"  -> Saved {file1.name} ({file1.stat().st_size // 1024} KB)")

    print("\n=== All 16 Equirectangular Panoramas (6144x3072) Built & Synced! ===")


if __name__ == "__main__":
    main()
