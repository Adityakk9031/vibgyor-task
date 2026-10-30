"""Geometry, tiling and seam checks for the AI finishing pass (runs on CPU, no model)."""

import json
import zipfile

import cv2
import numpy as np
import pytest

from pipeline import finish_ai, import_ai_results


def _smooth_equirect(w=512, h=256):
    lon = np.linspace(-np.pi, np.pi, w, endpoint=False)
    lat = finish_ai.latitudes(h)
    lon_g, lat_g = np.meshgrid(lon, lat)
    r = 128 + 100 * np.cos(lat_g) * np.sin(lon_g)
    g = 128 + 100 * np.sin(lat_g)
    b = 128 + 100 * np.cos(lat_g) * np.cos(lon_g)
    return np.dstack([r, g, b]).astype(np.uint8)


def test_perspective_round_trip_matches_equirect():
    equi = _smooth_equirect()
    face = finish_ai.equi_to_persp(equi, yaw=30, pitch=10, fov=90, size=256)
    back, valid = finish_ai.persp_to_equi(face, yaw=30, pitch=10, fov=90, width=512, height=256)
    inner = cv2.erode(valid.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    assert inner.sum() > 10_000
    err = np.abs(back.astype(int) - equi.astype(int))[inner]
    assert err.mean() < 2.0


def test_pole_face_looks_straight_up():
    equi = _smooth_equirect()
    top = finish_ai.equi_to_persp(equi, yaw=0, pitch=90, fov=90, size=64)
    # Green channel encodes sin(lat): the up-face centre is the zenith (brightest green)
    assert top[32, 32, 1] > 220


@pytest.mark.parametrize("wrap", [False, True])
def test_identity_refine_keeps_image(wrap):
    img = _smooth_equirect(640, 320)
    ctl = np.zeros_like(img)
    out = finish_ai.refine_tiles(img, ctl, ctl, finish_ai.dry_run_enhancer, prompt="", strength=0.3,
                                 steps=10, seed=0, tile=192, overlap=48, wrap_x=wrap)
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 1


def test_depth_control_near_is_bright_and_sky_black():
    depth = np.array([[0.0, 1.0, 10.0]], np.float32).repeat(4, 0)
    ctl = finish_ai.depth_control(depth)
    assert ctl[0, 0, 0] == 0
    assert ctl[0, 1, 0] > ctl[0, 2, 0]


def test_dry_run_pano_and_still_end_to_end(tmp_path):
    (tmp_path / "in").mkdir()
    equi = _smooth_equirect(512, 256)
    cv2.imwrite(str(tmp_path / "in" / "p.png"), cv2.cvtColor(equi, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(tmp_path / "in" / "p_depth.png"), np.full((256, 512), 350, np.uint16))
    still = cv2.resize(equi, (320, 180))
    cv2.imwrite(str(tmp_path / "in" / "s.png"), cv2.cvtColor(still, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(tmp_path / "in" / "s_depth.png"), np.full((180, 320), 420, np.uint16))
    jobs = {
        "panos": [{"id": "p", "base": "p.png", "depth": "p_depth.png", "prompt": "room", "seed": 1}],
        "stills": [{"id": "s", "base": "s.png", "depth": "s_depth.png", "prompt": "room", "seed": 2}],
        "settings": {
            "pano": {"work_width": 256, "pad": 16, "out_width": 512},
            "still": {"work_size": [136, 80], "out_size": [256, 144]},
        },
    }
    (tmp_path / "in" / "jobs.json").write_text(json.dumps(jobs))

    manifest = finish_ai.run(tmp_path / "in", tmp_path / "out", only=None, dry_run=True)

    pano = cv2.imread(str(tmp_path / "out" / "panoramas" / "p.png"))
    assert pano.shape == (256, 512, 3)
    assert np.abs(pano[:, 0].astype(int) - pano[:, -1].astype(int)).mean() < 5
    assert cv2.imread(str(tmp_path / "out" / "stills" / "s.png")).shape == (144, 256, 3)
    assert set(manifest["items"]) == {"p", "s"}
    assert manifest["items"]["p"]["base_sha256"]


def _box_scene(w=320, h=180):
    """A box 2 m away in front of a wall 4 m away: depth in cm and a matching image."""
    depth = np.full((h, w), 400, np.uint16)
    depth[60:140, 100:220] = 200
    img = np.full((h, w, 3), 200, np.uint8)
    img[60:140, 100:220] = 90
    return depth, img


def test_layout_match_separates_matching_and_unrelated_images():
    depth, img = _box_scene()
    other = np.full_like(img, 200)
    other[20:70, 10:90] = 60  # a different object somewhere else
    assert import_ai_results.layout_match(img, depth, equirect=False) > 0.8
    assert import_ai_results.layout_match(other, depth, equirect=False) < 0.1


def test_import_checks_provenance_and_places_files(tmp_path, monkeypatch):
    depth, img = _box_scene()
    inputs = tmp_path / "vibgyor_ai_inputs"
    (inputs / "stills").mkdir(parents=True)
    cv2.imwrite(str(inputs / "stills" / "type_a_1_drawing_room.jpg"), img)
    cv2.imwrite(str(inputs / "stills" / "type_a_1_drawing_room_depth.png"), depth)
    jobs = {"panos": [], "stills": [{"id": "type_a_1_drawing_room", "base": "stills/type_a_1_drawing_room.jpg",
                                    "depth": "stills/type_a_1_drawing_room_depth.png", "prompt": "room", "seed": 1}],
            "settings": {"still": {"work_size": [160, 88], "out_size": [320, 180]}}}
    (inputs / "jobs.json").write_text(json.dumps(jobs))
    inputs_zip = tmp_path / "vibgyor_ai_inputs.zip"
    with zipfile.ZipFile(inputs_zip, "w") as zf:
        for f in inputs.rglob("*"):
            zf.write(f, f.relative_to(tmp_path).as_posix())
    finish_ai.run(inputs, tmp_path / "results", only=None, dry_run=True)

    monkeypatch.setattr(import_ai_results, "BASE_DIR", tmp_path)
    monkeypatch.setattr(import_ai_results, "INPUTS_ZIP", inputs_zip)
    monkeypatch.setattr(import_ai_results, "MANIFEST_OUT", tmp_path / "ai_manifest.json")
    with pytest.raises(SystemExit):
        import_ai_results.import_results(tmp_path / "results")  # dry-run output is refused
    report = import_ai_results.import_results(tmp_path / "results", allow_dry_run=True)

    assert (tmp_path / "viewer" / "interiors" / "type_a_1_drawing_room.png").exists()
    assert (tmp_path / "outputs" / "interiors" / "type_a_1_drawing_room.png").exists()
    assert report["type_a_1_drawing_room"]["layout_match"] > 0.5

    cv2.imwrite(str(inputs / "stills" / "type_a_1_drawing_room.jpg"), 255 - img)  # a different base
    with zipfile.ZipFile(inputs_zip, "w") as zf:
        for f in inputs.rglob("*"):
            zf.write(f, f.relative_to(tmp_path).as_posix())
    with pytest.raises(SystemExit, match="hash mismatch"):
        import_ai_results.import_results(tmp_path / "results", allow_dry_run=True)


def test_external_stills_import_checks_layout(tmp_path, monkeypatch):
    from PIL import Image
    from pipeline import import_external_stills

    depth, img = _box_scene(320, 180)
    bases = tmp_path / "outputs" / "ai_bases" / "stills"
    bases.mkdir(parents=True)
    for sid in ("type_a_1_drawing_room", "type_b_1_drawing_room"):
        cv2.imwrite(str(bases / f"{sid}.png"), img)
        cv2.imwrite(str(bases / f"{sid}_depth.png"), depth)
    results = tmp_path / "outputs" / "myarchitectai" / "results"
    results.mkdir(parents=True)
    # Matching layout at a different size and slightly off aspect, and an unrelated image
    Image.fromarray(cv2.resize(img, (1344, 768))).save(results / "02_type_a_1_drawing_room.jpg", quality=95)
    other = np.full_like(img, 200)
    other[20:70, 10:90] = 60
    Image.fromarray(other).save(results / "05_type_b_1_drawing_room.png")

    monkeypatch.setattr(import_ai_results, "BASE_DIR", tmp_path)
    monkeypatch.setattr(import_ai_results, "MANIFEST_OUT", tmp_path / "outputs" / "ai_manifest.json")
    report = import_external_stills.import_external(results, "MyArchitectAI Render")

    assert set(report) == {"type_a_1_drawing_room"}  # the unrelated image is refused
    out = tmp_path / "viewer" / "interiors" / "type_a_1_drawing_room.png"
    assert Image.open(out).size == (2560, 1440)
    prov = json.loads((tmp_path / "viewer" / "provenance.json").read_text())
    assert prov == {"type_a_1_drawing_room": "model"}
    manifest = json.loads((tmp_path / "outputs" / "ai_manifest.json").read_text())
    assert manifest["items"]["type_a_1_drawing_room"]["source"].startswith("MyArchitectAI")
