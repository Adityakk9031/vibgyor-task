import urllib.request, json, time, sys
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent

MISSING_ITEMS = [
    {
        "id": "amenity_6_terrace_gym",
        "out_paths": [
            "outputs/amenities/amenity_6_terrace_gym.png",
            "viewer/amenities/amenity_6_terrace_gym.png",
        ],
        "prompt": (
            "Photorealistic 16:9 interior architectural photography of a luxury modern rooftop fitness gym pavilion on the terrace of a residential apartment tower, "
            "floor-to-ceiling glass curtain walls overlooking city skyline, matte black treadmills, air bikes, dumbbell rack, dark grey gym rubber flooring, "
            "linear recessed warm-white ceiling lights, bright morning daylight, Architectural Digest 8k"
        ),
    },
    {
        "id": "type_a_5_third_bedroom",
        "out_paths": [
            "outputs/interiors/type_a_5_third_bedroom.png",
            "viewer/interiors/type_a_5_third_bedroom.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a bright modern Scandinavian third bedroom (3.36m x 4.20m), "
            "upholstered queen bed in light cream linen with olive and rust throw cushions, light oak herringbone parquet wood floor with ribbed wool rug, "
            "fluted light oak feature wall with hidden warm LED strip, floating desk with minimalist black chair next to a large sunny window with sheer curtains, "
            "Architectural Digest 8k"
        ),
    },
    {
        "id": "type_b_5_third_bedroom",
        "out_paths": [
            "outputs/interiors/type_b_5_third_bedroom.png",
            "viewer/interiors/type_b_5_third_bedroom.png",
        ],
        "prompt": (
            "Photorealistic 16:9 architectural interior photography of a cozy luxury modern Scandinavian third bedroom (3.20m x 3.96m), "
            "upholstered double bed with dark sage linen duvet and terracotta accent pillows, warm vertical walnut wood panel headboard wall with recessed LED strip lighting, "
            "built-in matte grey wardrobe, light oak parquet flooring, sliding window with soft sunlight, Architectural Digest 8k"
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
    
    for wait_tick in range(60):
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
    for item in MISSING_ITEMS:
        generate_item(item)
    print("\n=== All missing items successfully generated! ===")

if __name__ == '__main__':
    main()
