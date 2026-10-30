import urllib.request, json, time
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent

PROMPT_STILT = (
    "Photorealistic 16:9 eye-level architectural interior photography of a covered ground-floor stilt parking garage "
    "underneath a luxury modern residential building, heavy square concrete structural columns supporting the building ceiling slab, "
    "interlocking grey stone pavement driveway with neatly painted white and yellow parking bay lines, "
    "luxury modern sedans and SUVs parked in parking bays between columns, warm recessed circular LED downlights glowing from the ceiling soffit, "
    "bright daylight entering from open perimeter sides with lush green tropical shrubs visible outside, ultra-sharp architectural photography 8k"
)

payload = {
    'prompt': PROMPT_STILT,
    'params': {'width': 1024, 'height': 576, 'steps': 8, 'cfg_scale': 6.0, 'sampler_name': 'k_euler', 'karras': True, 'n': 1},
    'models': ['Juggernaut XL', 'AlbedoBase XL (SDXL)'],
    'nsfw': True,
    'censor_nsfw': False,
    'r2': True
}

req = urllib.request.Request(
    'https://stablehorde.net/api/v2/generate/async',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'apikey': '0000000000', 'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
)

jid = '19bad7ef-70ae-48f5-8a78-5b633eba2884'
print(f"Resuming Stilt Parking Job: {jid}")

for i in range(40):
    time.sleep(3)
    st = json.loads(urllib.request.urlopen(urllib.request.Request(
        f'https://stablehorde.net/api/v2/generate/check/{jid}',
        headers={'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
    )).read().decode())
    print(f"[{i*3}s] Queue: {st.get('queue_position')} | Processing: {st.get('processing')} | Done: {st.get('done')}")
    if st.get('done'):
        full = json.loads(urllib.request.urlopen(urllib.request.Request(
            f'https://stablehorde.net/api/v2/generate/status/{jid}',
            headers={'Client-Agent': 'VibgyorArch:1.0:user', 'User-Agent': 'Mozilla/5.0'}
        )).read().decode())
        img_url = full['generations'][0]['img']
        data = urllib.request.urlopen(urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})).read()
        
        # Save temp
        temp_path = BASE_DIR / "scratch_stilt.webp"
        temp_path.write_bytes(data)
        
        # Upscale and save 2560x1440 PNG
        with Image.open(temp_path) as img:
            img_2k = img.resize((2560, 1440), Image.Resampling.LANCZOS)
            out1 = BASE_DIR / "outputs/amenities/amenity_2_stilt_parking.png"
            out2 = BASE_DIR / "viewer/amenities/amenity_2_stilt_parking.png"
            img_2k.save(out1, format="PNG")
            img_2k.save(out2, format="PNG")
            print(f"Saved amenity_2_stilt_parking.png ({out1.stat().st_size // 1024} KB)")
        break
