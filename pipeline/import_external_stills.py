"""
Import still renders finished outside the pipeline, e.g. in MyArchitectAI (pipeline/import_external_stills.py).

Reads outputs/myarchitectai/results/<NN>_<still_id>.(png|jpg|jpeg|webp), the results of uploading the
inputs made by `python -m pipeline.prepare_myarchitectai` (Blender renders of the CAD-derived model). For
each image it
  1. fits it to 2560 x 1440 (centre crop if the aspect is off, then resize),
  2. scores layout match against that camera's model depth map (same check as the 360° spots) and
     skips images below the threshold unless --force,
  3. copies it to outputs/ and viewer/, records it in outputs/ai_manifest.json with the hash of the
     model render that was uploaded, and marks it "model" in viewer/provenance.json.

    python -m pipeline.import_external_stills
    python -m pipeline.import_external_stills --source "MyArchitectAI Render" --force
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from pipeline import import_ai_results as core
from pipeline.package_ai_inputs import STILLS

OUT_SIZE = (2560, 1440)


def fit_16_9(im: Image.Image) -> Image.Image:
    w, h = im.size
    target = OUT_SIZE[0] / OUT_SIZE[1]
    if abs(w / h - target) > 0.005:
        if w / h > target:
            nw = round(h * target)
            im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = round(w / target)
            im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize(OUT_SIZE, Image.Resampling.LANCZOS)


def import_external(results_dir: Path, source: str, force: bool = False) -> dict:
    bases = core.BASE_DIR / "outputs" / "ai_bases" / "stills"
    uploads = results_dir.parent / "inputs"
    report: dict = {}
    for path in sorted(results_dir.iterdir()):
        m = re.fullmatch(r"(?:\d+_)?(.+?)\.(png|jpe?g|webp)", path.name, re.IGNORECASE)
        if not m or m.group(1) not in STILLS:
            print(f"[external] skip {path.name}: not a still id")
            continue
        still_id = m.group(1)
        depth_path = bases / f"{still_id}_depth.png"
        if not depth_path.exists():
            print(f"[external] skip {still_id}: no model depth map yet (run render_ai_bases)")
            continue
        im = Image.open(path).convert("RGB")
        orig = im.size
        im = fit_16_9(im)
        depth = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
        match = core.layout_match(cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR), depth, equirect=False)
        if match < core.MIN_LAYOUT_MATCH and not force:
            print(f"[external] {still_id:30s} layout match {match:5.2f}  <-- too low, NOT imported (check it, or --force)")
            continue

        dests = core.destinations(still_id, "still")
        dests[0].parent.mkdir(parents=True, exist_ok=True)
        im.save(dests[0])
        for d in dests[1:]:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dests[0], d)
        upload = next(uploads.glob(f"*_{still_id}.jpg"), None)
        report[still_id] = {
            "kind": "still",
            "output": path.name,
            "size": list(OUT_SIZE),
            "source_size": list(orig),
            "base_sha256": hashlib.sha256((bases / f"{still_id}.png").read_bytes()).hexdigest(),
            "uploaded_sha256": hashlib.sha256(upload.read_bytes()).hexdigest() if upload else None,
            "layout_match": round(match, 3),
            "output_sha256": hashlib.sha256(dests[0].read_bytes()).hexdigest(),
            "files": [d.relative_to(core.BASE_DIR).as_posix() for d in dests],
        }
        flag = "" if match >= core.MIN_LAYOUT_MATCH else "  (forced)"
        print(f"[external] {still_id:30s} {orig[0]}x{orig[1]} -> 2560x1440 | layout match {match:5.2f}{flag}")

    core.update_manifest(report, None, f"{source} of a Blender render of outputs/vibgyor.blend")
    core.record_provenance([i for i, r in report.items() if r["layout_match"] >= core.MIN_LAYOUT_MATCH])
    print(f"[external] {len(report)} stills imported")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import externally finished still renders (e.g. MyArchitectAI).")
    parser.add_argument("--results", type=Path, default=core.BASE_DIR / "outputs" / "myarchitectai" / "results")
    parser.add_argument("--source", default="MyArchitectAI Render")
    parser.add_argument("--force", action="store_true", help="Import even if the layout match is below the threshold")
    args = parser.parse_args()
    import_external(args.results, args.source, args.force)


if __name__ == "__main__":
    main()
