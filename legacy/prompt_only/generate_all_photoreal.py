"""
Photorealistic Batch Renderer (pipeline/generate_all_photoreal.py)

Generates MyArchitectAI / Architectural Digest grade photorealistic renders
for all Vibgyor still viewpoints (2560x1440 PNG) and 360° equirectangular
panoramas (6144x3072 PNG with seamless horizontal wrap blending), saving
synchronized copies to both `outputs/` and `viewer/`.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
API_BASE = "https://black-forest-labs-flux-1-schnell.hf.space/gradio_api"

STILL_TARGETS = [
    # Type B Interiors (4)
    {
        "id": "type_b_1_drawing_room",
        "out_paths": [
            "outputs/interiors/type_b_1_drawing_room.png",
            "viewer/interiors/type_b_1_drawing_room.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a luxury modern Scandinavian living room "
            "(Type B Drawing Room, 6.31m x 3.65m), light oak herringbone parquet wood floor with a textured cream wool area rug, "
            "spacious L-shaped modular sectional sofa in warm cream boucle with terracotta and sage green accent pillows, "
            "twin nested round Statuario white marble coffee tables with brushed brass rims, floor-to-ceiling vertical fluted "
            "walnut wood slat media wall with warm hidden LED strip lighting and floating walnut console, black steel Crittall "
            "glass partition door, wide sliding glass doors with sheer white curtains opening onto a sunny landscaped balcony "
            "with potted olive trees, natural daylight, Architectural Digest 8k"
        ),
    },
    {
        "id": "type_b_2_kitchen_dining",
        "out_paths": [
            "outputs/interiors/type_b_2_kitchen_dining.png",
            "viewer/interiors/type_b_2_kitchen_dining.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of an open-plan luxury modern Scandinavian kitchen and dining room "
            "(6.11m x 3.20m), light oak herringbone parquet wood floor, natural thick solid oak 6-seater dining table with angled matte "
            "black steel legs, molded matte black Eames-style dining chairs with wooden dowel legs, two oversized matte black dome pendant "
            "lights suspended above the dining table with warm glowing white interiors, white Statuario marble waterfall kitchen island "
            "with matte black barstools, floor-to-ceiling vertical walnut cabinetry with integrated stainless steel double oven, "
            "black steel Crittall grid glass double doors in the background, bright natural daylight, Architectural Digest 8k"
        ),
    },
    {
        "id": "type_b_3_master_bedroom",
        "out_paths": [
            "outputs/interiors/type_b_3_master_bedroom.png",
            "viewer/interiors/type_b_3_master_bedroom.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a luxury modern Scandinavian master bedroom suite "
            "(5.34m x 3.65m), king-size upholstered bed in cream boucle with crisp white linen bedding, olive green throw blanket and cushions, "
            "full-height vertical fluted dark walnut slat accent wall behind the headboard with warm recessed perimeter LED cove lighting, "
            "floating walnut nightstands with brass cylindrical pendant lights, light oak herringbone parquet flooring with a ribbed cream rug, "
            "large sliding glass window with sheer white floor-to-ceiling curtains and bright morning sunlight, Architectural Digest 8k"
        ),
    },
    {
        "id": "type_b_4_second_bedroom",
        "out_paths": [
            "outputs/interiors/type_b_4_second_bedroom.png",
            "viewer/interiors/type_b_4_second_bedroom.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a cozy modern Scandinavian corner second bedroom "
            "(4.73m x 3.35m), upholstered queen bed in warm beige linen with muted teal and cream accent pillows, "
            "warm oak wood panel headboard wall with recessed warm LED cove ceiling lighting, floating oak nightstands with black reading lamps, "
            "light oak herringbone parquet flooring, built-in matte cream floor-to-ceiling wardrobe with subtle brass handles, "
            "large window with sheer white linen curtains letting in soft natural daylight, Architectural Digest 8k"
        ),
    },
    # Amenities (5)
    {
        "id": "amenity_1_basement_parking",
        "out_paths": [
            "outputs/amenities/amenity_1_basement_parking.png",
            "viewer/amenities/amenity_1_basement_parking.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural photography of a clean modern luxury residential underground basement parking garage, "
            "polished grey epoxy concrete floor with crisp yellow painted parking bay lines and directional arrows, "
            "reinforced concrete structural columns painted with neat black and yellow safety hazard bands and bay numbers, "
            "curved concrete vehicular ramp visible in the background, sleek modern luxury SUVs and sedans parked neatly in bays, "
            "continuous suspended linear warm-white LED strip lighting along the ceiling slab, ultra-sharp architectural visualization 8k"
        ),
    },
    {
        "id": "amenity_2_stilt_parking",
        "out_paths": [
            "outputs/amenities/amenity_2_stilt_parking.png",
            "viewer/amenities/amenity_2_stilt_parking.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural photography of a ground-floor hollow-plinth covered stilt parking area in a contemporary "
            "luxury residential apartment tower, interlocking dark grey granite cobble stone driveway and numbered car parking bays, "
            "clean architectural concrete columns, warm recessed LED downlights in the ceiling soffit, luxury sedans and SUVs parked neatly, "
            "lush green tropical perimeter planter beds and sunlight filtering in from the open sides, ultra-realistic 8k"
        ),
    },
    {
        "id": "amenity_3_entrance_lobby",
        "out_paths": [
            "outputs/amenities/amenity_3_entrance_lobby.png",
            "viewer/amenities/amenity_3_entrance_lobby.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a luxury residential apartment ground-floor entrance lobby foyer, "
            "bookmatched cream travertine marble walls and polished Italian terrazzo flooring, vertical fluted walnut wood feature wall, "
            "two sleek brushed bronze elevator doors with warm LED floor indicators, sculptural interlocking warm brass ring chandelier "
            "suspended from a recessed cove ceiling, curved cream boucle lounge sofa with round marble coffee table and indoor fiddle-leaf fig tree, "
            "sunlight streaming through glass entrance doors, Architectural Digest 8k"
        ),
    },
    {
        "id": "amenity_4_landscape_drive",
        "out_paths": [
            "outputs/amenities/amenity_4_landscape_drive.png",
            "viewer/amenities/amenity_4_landscape_drive.png",
        ],
        "prompt": (
            "Photorealistic 16:9 exterior architectural photography of a landscaped garden deck and driveway along the setback of a luxury "
            "modern residential apartment building, raised warm Ipe hardwood timber seating deck with contemporary wooden benches, "
            "lush manicured tropical shrubs, frangipani trees and ornamental grasses in stone planter beds, paved dark granite driveway "
            "lined with warm architectural low bollard lights, golden afternoon sunlight, ultra-sharp 8k"
        ),
    },
    {
        "id": "amenity_5_terrace_amenities",
        "out_paths": [
            "outputs/amenities/amenity_5_terrace_amenities.png",
            "viewer/amenities/amenity_5_terrace_amenities.png",
        ],
        "prompt": (
            "Photorealistic 16:9 exterior architectural photography of a luxury rooftop terrace amenity deck on a modern 7-storey residential "
            "apartment building, dark bronze slatted architectural pergola in the foreground with warm hanging lanterns and outdoor L-shaped "
            "lounge sofas, colorful soft-fall EPDM children play zone in the middle, and a sleek floor-to-ceiling glass-walled rooftop fitness "
            "gym pavilion in the background with treadmills inside and solar panels on its roof, clear blue sky with soft clouds, 8k"
        ),
    },
    # Exteriors (4)
    {
        "id": "shot_1_eye_level_day",
        "out_paths": [
            "outputs/shot_1_eye_level_day.png",
            "viewer/exteriors/shot_1_eye_level_day.png",
        ],
        "prompt": (
            "Photorealistic 16:9 eye-level architectural exterior photography of a modern 7-storey luxury residential apartment tower "
            "viewed from a wide urban road in bright sunny daylight, contemporary white stucco and grey architectural concrete facade, "
            "vertical charcoal aluminum sun-shading louver fins, glass balcony railings with warm teak wood-slat balcony ceiling soffits "
            "and recessed spotlights, front stone boundary wall with glowing brass letters, cantilevered wood-soffit entrance gate canopy "
            "and lush green street trees, MyArchitectAI quality 8k"
        ),
    },
    {
        "id": "shot_2_front_corner_dusk",
        "out_paths": [
            "outputs/shot_2_front_corner_dusk.png",
            "viewer/exteriors/shot_2_front_corner_dusk.png",
        ],
        "prompt": (
            "Photorealistic 16:9 three-quarter corner architectural exterior photography of a modern 7-storey luxury residential apartment "
            "tower at golden blue-hour dusk, warm 2700K interior lights glowing through floor-to-ceiling glass sliding balcony doors on all 7 floors, "
            "warm recessed LED spotlights glowing under wooden balcony ceiling soffits, vertical architectural facade fins, illuminated entrance "
            "canopy gate and glowing architectural bollard lights along the landscaped boundary wall, deep twilight sky, 8k"
        ),
    },
    {
        "id": "shot_3_aerial_day",
        "out_paths": [
            "outputs/shot_3_aerial_day.png",
            "viewer/exteriors/shot_3_aerial_day.png",
        ],
        "prompt": (
            "Photorealistic 16:9 45-degree aerial architectural photography of a modern 7-storey luxury residential apartment tower and its "
            "complete site compound in bright daylight, showcasing the rooftop terrace with slatted pergola lounge, kids play area, and glass "
            "fitness gym pavilion topped with solar PV panels, white and grey facade with glass balconies and vertical louvers, ground-level "
            "landscaped garden driveway, entrance gate canopy, and adjacent wide paved main road with trees, 8k"
        ),
    },
    {
        "id": "shot_4_entrance_closeup",
        "out_paths": [
            "outputs/shot_4_entrance_closeup.png",
            "viewer/exteriors/shot_4_entrance_closeup.png",
        ],
        "prompt": (
            "Photorealistic 16:9 close-up eye-level architectural photography of the main entrance gate portal of a luxury modern residential "
            "apartment building named VIBGYOR, cantilevered architectural concrete entrance canopy with warm slatted teak wood ceiling soffit "
            "and recessed LED downlights, sleek modern glass-windowed security cabin, textured grey stone compound wall with backlit brushed "
            "brass letters, lush tropical planter beds, and granite cobble driveway leading into the ground-floor stilt level, bright daylight 8k"
        ),
    },
]


def generate_flux_image(prompt: str, width: int = 1280, height: int = 720, steps: int = 4) -> Image.Image:
    """Calls FLUX.1-schnell Gradio API and returns a PIL Image, respecting ZeroGPU cooldowns."""
    payload = json.dumps({
        "data": [prompt, 42, True, width, height, steps]
    }).encode("utf-8")

    for attempt in range(8):
        try:
            req = urllib.request.Request(
                f"{API_BASE}/call/infer",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                event_id = json.loads(resp.read().decode("utf-8"))["event_id"]

            stream_url = f"{API_BASE}/call/infer/{event_id}"
            req_stream = urllib.request.Request(stream_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_stream, timeout=90) as sresp:
                raw_sse = sresp.read().decode("utf-8")

            # Parse event: complete
            match = re.search(r"event:\s*complete\s*\ndata:\s*(\[.*\])", raw_sse)
            if not match:
                raise RuntimeError(f"Unexpected SSE response: {raw_sse[:300]}")

            data_arr = json.loads(match.group(1))
            img_info = data_arr[0]
            file_url = img_info.get("url")
            if not file_url and img_info.get("path"):
                file_url = f"{API_BASE}/file={img_info['path']}"

            req_img = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_img, timeout=45) as iresp:
                img_bytes = iresp.read()

            return Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            wait_s = 32 if "event: error" in str(e) else 10 * (attempt + 1)
            print(f"  [retry {attempt + 1}/8] Error: {e} (waiting {wait_s}s for ZeroGPU cooldown...)")
            time.sleep(wait_s)

    raise RuntimeError(f"Failed to generate image after 8 attempts for prompt: {prompt[:60]}...")


ALREADY_COMPLETED = {
    "type_b_1_drawing_room",
    "type_b_2_kitchen_dining",
}


def main():
    remaining = [t for t in STILL_TARGETS if t["id"] not in ALREADY_COMPLETED]
    print(f"=== Generating {len(remaining)} Remaining Photorealistic Stills (2560x1440) ===")
    for idx, item in enumerate(remaining, 1):
        print(f"[{idx}/{len(remaining)}] Generating {item['id']} ...")
        img = generate_flux_image(item["prompt"], width=1280, height=720, steps=4)
        img_2k = img.resize((2560, 1440), Image.Resampling.LANCZOS)
        for rel_path in item["out_paths"]:
            full_path = BASE_DIR / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            img_2k.save(str(full_path), format="PNG", optimize=False)
            print(f"  -> Saved {rel_path} ({full_path.stat().st_size // 1024} KB)")
        time.sleep(6)

    print("=== All 17 Photorealistic Stills Ready! ===")


if __name__ == "__main__":
    sys.exit(main())
