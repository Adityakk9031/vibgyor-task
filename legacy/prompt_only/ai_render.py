"""
MyArchitectAI Batch Enhancement Script (pipeline/ai_render.py)

Takes our rendered 3D architectural stills from `outputs/` and passes them through
the official MyArchitectAI API (https://api.myarchitectai.com/v1) to generate
showroom/magazine-grade photorealistic renders matching the client's reference.

Usage:
    python pipeline/ai_render.py --api-key YOUR_MYARCHITECTAI_API_KEY
    # Or set MYARCHITECTAI_API_KEY in your environment:
    # set MYARCHITECTAI_API_KEY=your_key_here
    # python pipeline/ai_render.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

BASE_DIR = Path(__file__).resolve().parent.parent

# Stills to enhance for the client presentation
AI_TARGETS = [
    {
        "id": "type_a_2_kitchen_dining",
        "local_path": "outputs/interiors/type_a_2_kitchen_dining.png",
        "output_path": "outputs/interiors/type_a_2_kitchen_dining_photoreal.png",
        "endpoint": "render/interior",
        "prompt": (
            "Modern minimalist luxury kitchen and dining room, herringbone oak parquet wooden floor, "
            "matte black dome pendant lights, black steel grid Crittall glass doors, "
            "fluted walnut cabinetry with integrated oven, white statuario marble waterfall kitchen island, "
            "molded black dining chairs with wood dowel legs, soft architectural daylight streaming in, 8k"
        ),
    },
    {
        "id": "type_a_1_drawing_room",
        "local_path": "outputs/interiors/type_a_1_drawing_room.png",
        "output_path": "outputs/interiors/type_a_1_drawing_room_photoreal.png",
        "endpoint": "render/interior",
        "prompt": (
            "Contemporary Scandinavian living room, plush low-profile sectional sofa, nested marble coffee table, "
            "chevron light oak flooring, warm LED cove lighting, sheer curtains, architectural digest, ultra photorealistic, 8k"
        ),
    },
    {
        "id": "type_a_3_master_bedroom",
        "local_path": "outputs/interiors/type_a_3_master_bedroom.png",
        "output_path": "outputs/interiors/type_a_3_master_bedroom_photoreal.png",
        "endpoint": "render/interior",
        "prompt": (
            "High-end master bedroom suite, king upholstered bed with crisp linen, fluted wood accent wall, "
            "pendant reading lights, herringbone parquet floor, sheer floor-to-ceiling curtains, morning sunlight, 8k"
        ),
    },
    {
        "id": "amenity_3_entrance_lobby",
        "local_path": "outputs/amenities/amenity_3_entrance_lobby.png",
        "output_path": "outputs/amenities/amenity_3_entrance_lobby_photoreal.png",
        "endpoint": "render/interior",
        "prompt": (
            "Luxury residential entrance lobby, bookmatched travertine marble walls, bronze elevator doors, "
            "sculptural ring chandelier, curved velvet sofa lounge, polished terrazzo floor, warm interior lighting, 8k"
        ),
    },
    {
        "id": "shot_1_eye_level_day",
        "local_path": "outputs/shot_1_eye_level_day.png",
        "output_path": "outputs/shot_1_eye_level_day_photoreal.png",
        "endpoint": "render/exterior",
        "prompt": (
            "Modern residential apartment tower facade, concrete and timber louvers, glass balconies, "
            "landscaped entrance gate with security cabin and lush trees, bright clear daylight, architectural photograph, 8k"
        ),
    },
]


def upload_temp_image(image_path: Path) -> str:
    """Uploads a local image to a free temporary image host (Catbox/Freeimage) to obtain a public URL."""
    print(f"[upload] Uploading {image_path.name} to generate public image URL...")
    # Use Litterbox (Catbox temporary upload, 1 hour retention)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = []
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="reqtype"')
    data.append(b"")
    data.append(b"fileupload")
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="time"')
    data.append(b"")
    data.append(b"1h")
    data.append(f"--{boundary}".encode())
    data.append(f'Content-Disposition: form-data; name="fileToUpload"; filename="{image_path.name}"'.encode())
    data.append(b"Content-Type: image/png")
    data.append(b"")
    data.append(image_path.read_bytes())
    data.append(f"--{boundary}--".encode())
    data.append(b"")
    body = b"\r\n".join(data)

    req = urllib.request.Request(
        "https://litterbox.catbox.moe/resources/internals/api.php",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        url = resp.read().decode("utf-8").strip()
        print(f"[upload] Uploaded -> {url}")
        return url


def call_myarchitectai(api_key: str, endpoint: str, image_url: str, prompt: str) -> str:
    """Calls MyArchitectAI API v1 to render the view."""
    api_url = f"https://api.myarchitectai.com/v1/{endpoint}"
    payload = json.dumps({
        "image": image_url,
        "prompt": prompt,
        "outputFormat": "png",
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "Vibgyor-Pipeline/2.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("url") or data.get("resultUrl") or ""
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(f"MyArchitectAI API returned HTTP {e.code}: {err_body}")


def main():
    parser = argparse.ArgumentParser(description="MyArchitectAI Batch Enhancement Pipeline")
    parser.add_argument("--api-key", default=os.getenv("MYARCHITECTAI_API_KEY", ""), help="MyArchitectAI API key")
    parser.add_argument("--shot", default=None, help="Enhance only a specific shot ID")
    args = parser.parse_args()

    api_key = args.api_key.strip()
    if not api_key:
        print("\n[ERROR] No MyArchitectAI API key provided.")
        print("Please provide it via --api-key YOUR_KEY or set MYARCHITECTAI_API_KEY environment variable.\n")
        print("Example:")
        print("  python pipeline/ai_render.py --api-key YOUR_KEY\n")
        return 1

    targets = [t for t in AI_TARGETS if not args.shot or t["id"] == args.shot]
    print(f"\n=== MyArchitectAI Enhancement Pipeline ({len(targets)} targets) ===\n")

    for t in targets:
        local_in = BASE_DIR / t["local_path"]
        local_out = BASE_DIR / t["output_path"]
        if not local_in.exists():
            print(f"[skip] Input {local_in} does not exist.")
            continue

        print(f"\n[processing] Shot: {t['id']}")
        try:
            pub_url = upload_temp_image(local_in)
            print(f"[api] Calling MyArchitectAI ({t['endpoint']})...")
            result_url = call_myarchitectai(api_key, t["endpoint"], pub_url, t["prompt"])
            if result_url:
                print(f"[download] Downloading enhanced render from {result_url} -> {local_out} ...")
                urllib.request.urlretrieve(result_url, str(local_out))
                print(f"[success] Saved {local_out} ({local_out.stat().st_size // 1024} KB)")
            else:
                print(f"[error] No output URL received for {t['id']}")
        except Exception as e:
            print(f"[error] Failed processing {t['id']}: {e}")

    print("\n=== MyArchitectAI Enhancement Completed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
