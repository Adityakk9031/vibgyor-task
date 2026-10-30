"""
Prepare the still renders for MyArchitectAI (pipeline/prepare_myarchitectai.py).

Copies the Blender still base renders of the CAD-derived model (outputs/ai_bases/stills/, from
render_ai_bases.py) into outputs/myarchitectai/inputs/ in upload order and writes PROMPTS.md with the
mode and prompt to use for each. Results saved to outputs/myarchitectai/results/ under the same file
name are brought in by `python -m pipeline.import_external_stills`.

    python -m pipeline.prepare_myarchitectai
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pipeline.package_ai_inputs import ROOMS, STILLS

BASE_DIR = Path(__file__).resolve().parent.parent
BASES = BASE_DIR / "outputs" / "ai_bases" / "stills"
OUT = BASE_DIR / "outputs" / "myarchitectai"

# Upload order: one test, then the rooms buyers look at first, exteriors last (dropped first if credits run out)
ORDER = [
    "amenity_3_entrance_lobby",
    "type_a_1_drawing_room", "type_a_2_kitchen_dining", "type_a_3_master_bedroom",
    "type_b_1_drawing_room", "type_b_2_kitchen_dining", "type_b_3_master_bedroom",
    "type_a_4_second_bedroom", "type_b_4_second_bedroom", "type_a_5_third_bedroom", "type_b_5_third_bedroom",
    "amenity_5_terrace_amenities", "amenity_6_terrace_gym", "amenity_1_basement_parking",
    "amenity_2_stilt_parking", "amenity_4_landscape_drive",
    "shot_1_eye_level_day", "shot_4_entrance_closeup", "shot_2_front_corner_dusk", "shot_3_aerial_day",
]
assert sorted(ORDER) == sorted(STILLS)

INTERIOR_ROOMS = {"lobby", "gym", "drawing", "kitchen", "master", "bedroom", "basement", "stilt"}


def short_prompt(room: str) -> str:
    """The material/mood part of the Kaggle prompt, without the generic photography suffix."""
    return ROOMS[room].split(", architectural")[0]


def prepare() -> list[str]:
    (OUT / "inputs").mkdir(parents=True, exist_ok=True)
    (OUT / "results").mkdir(parents=True, exist_ok=True)
    lines = [
        "# MyArchitectAI still renders",
        "",
        "For each row: **Render** → upload the file from `inputs/` → choose the mode → paste the prompt →",
        "keep creativity / variation **low** so walls, doors and furniture stay where they are → generate →",
        "download at the highest resolution → save it in `results/` with the **same file name** (any of .png / .jpg / .webp).",
        "",
        "Then run `python -m pipeline.import_external_stills` to layout-check and import them.",
        "",
        "| # | Upload file | Mode | Prompt |",
        "|:-:|:---|:---|:---|",
    ]
    missing = []
    for n, still_id in enumerate(ORDER, 1):
        room = STILLS[still_id][0]
        name = f"{n:02d}_{still_id}.jpg"
        src = BASES / f"{still_id}.png"
        if src.exists():
            Image.open(src).convert("RGB").save(OUT / "inputs" / name, quality=95)
            status = name
        else:
            missing.append(still_id)
            status = f"{name} *(still rendering)*"
        mode = "Interior" if room in INTERIOR_ROOMS else "Exterior"
        lines.append(f"| {n} | `{status}` | {mode} | {short_prompt(room)} |")
    (OUT / "PROMPTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[myarchitectai] {len(ORDER) - len(missing)} of {len(ORDER)} inputs ready in {OUT / 'inputs'}")
    if missing:
        print(f"[myarchitectai] still rendering: {', '.join(missing)} (re-run when render_ai_bases finishes)")
    return missing


if __name__ == "__main__":
    prepare()
