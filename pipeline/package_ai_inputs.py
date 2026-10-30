"""
Package the Blender base renders for the GPU finishing notebook (pipeline/package_ai_inputs.py).

Collects outputs/ai_bases/ (beauty + depth for every spot and still, from render_ai_bases.py),
the style references in outputs/ai_style_refs/, the per-room prompts below and finish_ai.py
into outputs/ai_handoff/vibgyor_ai_inputs.zip. Upload that zip to Kaggle / Colab and run
notebooks/vibgyor_ai_finish.ipynb.

Usage:
    python -m pipeline.package_ai_inputs
    python -m pipeline.package_ai_inputs --only pano_type_a_1_drawing_room   # quick preview zip
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
BASES = BASE_DIR / "outputs" / "ai_bases"
STYLE_REFS = BASE_DIR / "outputs" / "ai_style_refs"
OUT_ZIP = BASE_DIR / "outputs" / "ai_handoff" / "vibgyor_ai_inputs.zip"

INTERIOR = "architectural interior photograph, luxury Scandinavian apartment, bright natural daylight through clear glass, soft shadows, warm cove lighting, realistic contrast"
EXTERIOR = "architectural photograph, realistic materials, sharp detail"

# Describe materials and mood only: the layout comes from the depth and edges of the model render
ROOMS = {
    "gate": f"entrance gate of a modern residential tower, canopy with timber soffit, stone compound wall, security cabin, granite driveway, tropical planting, bright daylight, {EXTERIOR}",
    "lobby": f"luxury residential entrance lobby, travertine marble walls and floor, fluted walnut panels, bronze elevator doors, ring chandelier, lounge seating, {INTERIOR}",
    "basement": f"underground residential car park, parked cars and scooters, grey epoxy floor, yellow parking bay lines, concrete columns with yellow and black safety bands, linear LED ceiling lights, {EXTERIOR}",
    "stilt": f"covered stilt parking under a residential tower, parked cars, concrete columns, paved driveway, parking bay markings, landscaped garden edge, daylight, {EXTERIOR}",
    "garden": f"landscaped garden deck beside a residential tower, timber benches, planter beds with tropical shrubs, paved driveway, bollard lights, daylight, {EXTERIOR}",
    "terrace": f"rooftop terrace of a residential tower, slatted timber pergola lounge, outdoor sofas, artificial turf play area, planters, blue sky, {EXTERIOR}",
    "gym": f"rooftop glass fitness studio, gym equipment, rubber floor, floor-to-ceiling glass walls, skyline view, daylight, {INTERIOR}",
    "drawing": f"living room, sofa, coffee table, fluted wood TV wall, large clear glass sliding door to a sunny balcony, light oak herringbone floor, boucle upholstery, sheer curtains, {INTERIOR}",
    "kitchen": f"open kitchen and dining room, quartz countertops, wooden dining table and chairs, pendant lights, light oak floor, {INTERIOR}",
    "master": f"master bedroom, upholstered king bed with linen bedding, fluted wood headboard wall, bedside tables and lamps, wardrobe, light oak floor, sheer curtains, {INTERIOR}",
    "bedroom": f"bedroom, upholstered bed with linen bedding, wood panel headboard wall, bedside tables, wardrobe, light oak floor, sheer curtains, {INTERIOR}",
    "street_day": f"modern seven storey residential apartment tower, street view, glass balconies, white and concrete facade, trees, clear daylight, {EXTERIOR}",
    "street_dusk": f"modern seven storey residential apartment tower at dusk, warm interior lights glowing, glass balconies, deep blue sky, {EXTERIOR}",
    "aerial": f"aerial view of a modern residential tower and its site, rooftop terrace, landscaped grounds, road, daylight, {EXTERIOR}",
}

# id -> (room prompt, seed, style reference in outputs/ai_style_refs or None).
# A spot and the still of the same room share a seed so they come out alike. Exteriors take no style
# reference: the earlier prompt-only images show a different building.
PANOS = {
    "pano_bldg_1_entrance_gate": ("gate", 101, None),
    "pano_bldg_2_entrance_lobby": ("lobby", 102, "amenity_3_entrance_lobby.png"),
    "pano_bldg_3_basement_parking": ("basement", 103, "amenity_1_basement_parking.png"),
    "pano_bldg_4_garden_stilt": ("stilt", 104, "amenity_2_stilt_parking.png"),
    "pano_bldg_5_terrace_pergola_kids": ("terrace", 105, "amenity_5_terrace_amenities.png"),
    "pano_bldg_6_terrace_gym": ("gym", 106, "amenity_6_terrace_gym.png"),
    "pano_type_a_1_drawing_room": ("drawing", 201, "type_a_1_drawing_room.png"),
    "pano_type_a_2_dining_kitchen": ("kitchen", 202, "type_a_2_kitchen_dining.png"),
    "pano_type_a_3_master_bedroom": ("master", 203, "type_a_3_master_bedroom.png"),
    "pano_type_a_4_second_bedroom": ("bedroom", 204, "type_a_4_second_bedroom.png"),
    "pano_type_a_5_balcony_deck": ("bedroom", 205, "type_a_5_third_bedroom.png"),
    "pano_type_b_1_drawing_room": ("drawing", 301, "type_b_1_drawing_room.png"),
    "pano_type_b_2_dining_kitchen": ("kitchen", 302, "type_b_2_kitchen_dining.png"),
    "pano_type_b_3_master_bedroom": ("master", 303, "type_b_3_master_bedroom.png"),
    "pano_type_b_4_second_bedroom": ("bedroom", 304, "type_b_4_second_bedroom.png"),
    "pano_type_b_5_balcony_deck": ("bedroom", 305, "type_b_5_third_bedroom.png"),
}
STILLS = {
    "shot_1_eye_level_day": ("street_day", 401, None),
    "shot_2_front_corner_dusk": ("street_dusk", 402, None),
    "shot_3_aerial_day": ("aerial", 403, None),
    "shot_4_entrance_closeup": ("gate", 101, None),
    "amenity_1_basement_parking": ("basement", 103, "amenity_1_basement_parking.png"),
    "amenity_2_stilt_parking": ("stilt", 104, "amenity_2_stilt_parking.png"),
    "amenity_3_entrance_lobby": ("lobby", 102, "amenity_3_entrance_lobby.png"),
    "amenity_4_landscape_drive": ("garden", 107, "amenity_4_landscape_drive.png"),
    "amenity_5_terrace_amenities": ("terrace", 105, "amenity_5_terrace_amenities.png"),
    "amenity_6_terrace_gym": ("gym", 106, "amenity_6_terrace_gym.png"),
    "type_a_1_drawing_room": ("drawing", 201, "type_a_1_drawing_room.png"),
    "type_a_2_kitchen_dining": ("kitchen", 202, "type_a_2_kitchen_dining.png"),
    "type_a_3_master_bedroom": ("master", 203, "type_a_3_master_bedroom.png"),
    "type_a_4_second_bedroom": ("bedroom", 204, "type_a_4_second_bedroom.png"),
    "type_a_5_third_bedroom": ("bedroom", 205, "type_a_5_third_bedroom.png"),
    "type_b_1_drawing_room": ("drawing", 301, "type_b_1_drawing_room.png"),
    "type_b_2_kitchen_dining": ("kitchen", 302, "type_b_2_kitchen_dining.png"),
    "type_b_3_master_bedroom": ("master", 303, "type_b_3_master_bedroom.png"),
    "type_b_4_second_bedroom": ("bedroom", 304, "type_b_4_second_bedroom.png"),
    "type_b_5_third_bedroom": ("bedroom", 305, "type_b_5_third_bedroom.png"),
}


def _jpeg(path: Path, max_width: int | None = None) -> bytes:
    im = Image.open(path).convert("RGB")
    if max_width and im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def package(only: list[str] | None = None, use_style: bool = True, panos_only: bool = False) -> Path:
    jobs: dict = {"panos": [], "stills": []}
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    root = "vibgyor_ai_inputs"
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(BASE_DIR / "pipeline" / "finish_ai.py", f"{root}/finish_ai.py")
        styles_added: set[str] = set()
        tables = (("panos", PANOS, "panos"),) if panos_only else (("panos", PANOS, "panos"), ("stills", STILLS, "stills"))
        for kind, table, folder in tables:
            for job_id, (room, seed, style) in table.items():
                if only and job_id not in only:
                    continue
                beauty, depth = BASES / folder / f"{job_id}.png", BASES / folder / f"{job_id}_depth.png"
                missing = [p.name for p in (beauty, depth) if not p.exists()]
                if missing:
                    raise SystemExit(f"Missing base render(s) {missing}: run python -m pipeline.render_ai_bases first")
                job = {"id": job_id, "base": f"{folder}/{job_id}.jpg", "depth": f"{folder}/{job_id}_depth.png",
                       "prompt": ROOMS[room], "seed": seed}
                zf.writestr(f"{root}/{job['base']}", _jpeg(beauty))
                zf.write(depth, f"{root}/{job['depth']}")
                if use_style and style and (STYLE_REFS / style).exists():
                    job["style"] = f"style/{Path(style).stem}.jpg"
                    if job["style"] not in styles_added:
                        zf.writestr(f"{root}/{job['style']}", _jpeg(STYLE_REFS / style, max_width=1024))
                        styles_added.add(job["style"])
                jobs[kind].append(job)
        zf.writestr(f"{root}/jobs.json", json.dumps(jobs, indent=2))
    print(f"[package] {len(jobs['panos'])} spots + {len(jobs['stills'])} stills -> {OUT_ZIP} "
          f"({OUT_ZIP.stat().st_size / 2**20:.0f} MB)")
    return OUT_ZIP


def main() -> None:
    parser = argparse.ArgumentParser(description="Zip Blender base renders for the GPU finishing notebook.")
    parser.add_argument("--only", nargs="*", help="Job ids to include (default: all)")
    parser.add_argument("--no-style", action="store_true", help="Leave out the style reference images")
    parser.add_argument("--panos-only", action="store_true", help="Only the 16 tour spots (keep the existing stills)")
    args = parser.parse_args()
    package(args.only, use_style=not args.no_style, panos_only=args.panos_only)


if __name__ == "__main__":
    main()
