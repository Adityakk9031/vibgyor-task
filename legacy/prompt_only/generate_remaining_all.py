import urllib.request, json, time, sys
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent

REMAINING_ITEMS = [
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

def generate_item(item):
    item_id = item["id"]
    print(f"\n=== Generating {item_id} ===")
    payload = {
        'prompt': item["prompt"],
        'params': {'width': 1024, 'height': 576, 'steps': 8, 'cfg_scale': 6.0, 'sampler_name': 'k_euler', 'karras': True, 'n': 1},
        'models': ['Juggernaut XL', 'AlbedoBase XL (SDXL)'],
        'nsfw': True,
        'censor_nsfw': False,
        'r2': True
    }
    
    jid = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                'https://stablehorde.net/api/v2/generate/async',
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json', 'apikey': '0000000000', 'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
            )
            res = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
            jid = res['id']
            print(f"Submitted Job: {jid}")
            break
        except Exception as e:
            print(f"  [Attempt {attempt+1}] Submit error: {e}. Waiting 10s...")
            time.sleep(10)
            
    if not jid:
        raise RuntimeError(f"Could not submit job for {item_id}")
    
    while True:
        time.sleep(4)
        try:
            st = json.loads(urllib.request.urlopen(urllib.request.Request(
                f'https://stablehorde.net/api/v2/generate/check/{jid}',
                headers={'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
            ), timeout=30).read().decode())
        except Exception as e:
            print(f"  Check error: {e}")
            continue
            
        print(f"  Queue: {st.get('queue_position')} | Processing: {st.get('processing')} | Done: {st.get('done')}")
        if st.get('done'):
            full = json.loads(urllib.request.urlopen(urllib.request.Request(
                f'https://stablehorde.net/api/v2/generate/status/{jid}',
                headers={'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
            ), timeout=30).read().decode())
            img_url = full['generations'][0]['img']
            data = urllib.request.urlopen(urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=45).read()
            
            temp_path = BASE_DIR / f"scratch_{item_id}.webp"
            temp_path.write_bytes(data)
            
            with Image.open(temp_path) as img:
                img_2k = img.resize((2560, 1440), Image.Resampling.LANCZOS)
                for out_rel in item["out_paths"]:
                    out_path = BASE_DIR / out_rel
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    img_2k.save(out_path, format="PNG")
                    print(f"  -> Saved {out_rel} ({out_path.stat().st_size // 1024} KB)")
            break

def main():
    for item in REMAINING_ITEMS:
        generate_item(item)
    print("\n=== All items successfully generated! ===")

if __name__ == '__main__':
    main()
