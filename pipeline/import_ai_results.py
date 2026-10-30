"""
Bring the GPU notebook's results into the repo (pipeline/import_ai_results.py).

    python -m pipeline.import_ai_results path/to/vibgyor_ai_results.zip   # or an unzipped folder

For every image in the results manifest this
  1. checks it was made from the base render packaged in outputs/ai_handoff/vibgyor_ai_inputs.zip
     (sha256 of the base and depth files the notebook used),
  2. measures layout match: how many of the model's depth jumps (furniture outlines, door and window
     frames, wall ends) have an edge in the finished image, above what edge density gives by chance
     (the raw model render scores ~0.6, an unrelated photo of a similar room ~0),
  3. copies it to outputs/ and viewer/ under the name the viewer and verify_all.py expect,
and writes outputs/ai_manifest.json as the provenance record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
INPUTS_ZIP = BASE_DIR / "outputs" / "ai_handoff" / "vibgyor_ai_inputs.zip"
MANIFEST_OUT = BASE_DIR / "outputs" / "ai_manifest.json"
MIN_LAYOUT_MATCH = 0.30


def record_provenance(ids: list[str]) -> None:
    """Mark images as rendered from the model in viewer/provenance.json (the viewer labels the rest as concept)."""
    path = BASE_DIR / "viewer" / "provenance.json"
    prov = json.loads(path.read_text()) if path.exists() else {}
    prov.update({i: "model" for i in ids})
    path.write_text(json.dumps(dict(sorted(prov.items())), indent=2))


def update_manifest(report: dict, models: dict | None, source: str) -> None:
    previous = json.loads(MANIFEST_OUT.read_text()) if MANIFEST_OUT.exists() else {"items": {}}
    for item in report.values():
        item.setdefault("source", source)
    previous["items"].update(report)
    if models:
        previous["models"] = models
    MANIFEST_OUT.write_text(json.dumps(previous, indent=2))


def destinations(job_id: str, kind: str) -> list[Path]:
    if kind == "pano":
        return [BASE_DIR / "outputs" / "panoramas" / f"{job_id}.png", BASE_DIR / "viewer" / "panoramas" / f"{job_id}.png"]
    if job_id.startswith("shot_"):
        return [BASE_DIR / "outputs" / f"{job_id}.png", BASE_DIR / "viewer" / "exteriors" / f"{job_id}.png"]
    sub = "amenities" if job_id.startswith("amenity_") else "interiors"
    return [BASE_DIR / "outputs" / sub / f"{job_id}.png", BASE_DIR / "viewer" / sub / f"{job_id}.png"]


def depth_jumps(depth_cm: np.ndarray) -> np.ndarray:
    """Pixels where camera distance jumps by more than 6% (object outlines) or geometry meets sky."""
    d = depth_cm.astype(np.float32) / 100.0
    hit = d > 0.01
    edges = np.zeros(d.shape, bool)
    near_x = np.maximum(np.minimum(d[:, 1:], d[:, :-1]), 0.1)
    near_y = np.maximum(np.minimum(d[1:], d[:-1]), 0.1)
    edges[:, 1:] |= (np.abs(d[:, 1:] - d[:, :-1]) / near_x > 0.06) | (hit[:, 1:] != hit[:, :-1])
    edges[1:] |= (np.abs(d[1:] - d[:-1]) / near_y > 0.06) | (hit[1:] != hit[:-1])
    return edges


def layout_match(image_bgr: np.ndarray, depth_cm: np.ndarray, equirect: bool) -> float:
    """Depth-jump edges found in the image (within 2 px), minus what the image's edge density gives by chance."""
    h, w = depth_cm.shape[:2]
    gray = cv2.cvtColor(cv2.resize(image_bgr, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    img_edges = cv2.dilate(cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120), np.ones((5, 5), np.uint8)) > 0
    geo = depth_jumps(depth_cm)
    region = np.ones_like(geo)
    if equirect:  # the stretched ceiling and floor caps carry no layout information
        lat = 90 - (np.arange(h) + 0.5) / h * 180
        region[np.abs(lat) > 55] = False
    recall = (geo & img_edges & region).sum() / max((geo & region).sum(), 1)
    density = img_edges[region].mean()
    return float((recall - density) / max(1 - density, 1e-6))


def import_results(src: Path, allow_dry_run: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        folder = src
        if src.suffix == ".zip":
            zipfile.ZipFile(src).extractall(tmp)
            folder = Path(tmp)
        manifest_file = next(folder.rglob("manifest.json"))
        results = manifest_file.parent
        manifest = json.loads(manifest_file.read_text())
        if manifest.get("dry_run") and not allow_dry_run:
            raise SystemExit("These results come from a --dry-run (no AI); refusing to import them.")

        inputs = zipfile.ZipFile(INPUTS_ZIP)
        packaged = {n.split("/", 1)[1]: n for n in inputs.namelist() if "/" in n}
        report = {}
        for job_id, item in manifest["items"].items():
            folder_name = "panos" if item["kind"] == "pano" else "stills"
            base_name, depth_name = f"{folder_name}/{job_id}.jpg", f"{folder_name}/{job_id}_depth.png"
            base_bytes = inputs.read(packaged[base_name])
            depth_bytes = inputs.read(packaged[depth_name])
            if (hashlib.sha256(base_bytes).hexdigest() != item["base_sha256"]
                    or hashlib.sha256(depth_bytes).hexdigest() != item["depth_sha256"]):
                raise SystemExit(f"{job_id}: result was not made from the packaged model render (hash mismatch)")

            image = cv2.imread(str(results / item["output"]))
            depth = cv2.imdecode(np.frombuffer(depth_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            match = layout_match(image, depth, equirect=item["kind"] == "pano")
            for dest in destinations(job_id, item["kind"]):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(results / item["output"], dest)
            report[job_id] = {**item, "layout_match": round(match, 3),
                              "output_sha256": hashlib.sha256((results / item["output"]).read_bytes()).hexdigest(),
                              "files": [d.relative_to(BASE_DIR).as_posix() for d in destinations(job_id, item["kind"])]}
            flag = "" if match >= MIN_LAYOUT_MATCH else "  <-- low, check this image"
            print(f"[import] {job_id:34s} layout match {match:5.2f}{flag}")

    update_manifest(report, manifest.get("models"),
                    "Blender render of outputs/vibgyor.blend (built from SUBMISSION - 04.dxf), finished by pipeline/finish_ai.py")
    record_provenance([j for j, item in report.items() if item["layout_match"] >= MIN_LAYOUT_MATCH])
    print(f"[import] {len(report)} images imported; provenance in {MANIFEST_OUT.relative_to(BASE_DIR)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import AI-finished renders from the GPU notebook.")
    parser.add_argument("results", type=Path, help="vibgyor_ai_results.zip or its unzipped folder")
    parser.add_argument("--allow-dry-run", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    import_results(args.results, allow_dry_run=args.allow_dry_run)


if __name__ == "__main__":
    main()
