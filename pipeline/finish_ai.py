"""
AI finishing pass for the Vibgyor tour (pipeline/finish_ai.py).

Runs on a CUDA GPU (Kaggle / Colab, see notebooks/vibgyor_ai_finish.ipynb). The input is
the handoff folder made by `python -m pipeline.package_ai_inputs`: Blender renders of the
CAD-derived model plus exact depth maps for every tour spot (equirectangular) and still
camera (perspective). RealVisXL V5 repaints materials and lighting in img2img mode while two
ControlNets (xinsir depth + canny, fed from the Blender depth and edges) hold walls, openings
and furniture to the rendered geometry. Nothing is generated from a text prompt alone.

    python finish_ai.py --inputs vibgyor_ai_inputs --out results
    python finish_ai.py --inputs vibgyor_ai_inputs --out results --only pano_type_a_1_drawing_room
    python finish_ai.py --inputs vibgyor_ai_inputs --out results --dry-run   # CPU check, no AI

This file is self-contained (numpy, opencv, pillow; torch + diffusers only for the real
run) because it is copied into the handoff zip and executed outside the repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

MODELS = {
    "base": "SG161222/RealVisXL_V5.0",
    "vae": "madebyollin/sdxl-vae-fp16-fix",
    "controlnet_depth": "xinsir/controlnet-depth-sdxl-1.0",
    "controlnet_canny": "xinsir/controlnet-canny-sdxl-1.0",
    # Optional style reference (look of the AI stills the client approved); geometry still comes from the model
    "ip_adapter": "h94/IP-Adapter",
    "ip_adapter_weight": "sdxl_models/ip-adapter_sdxl_vit-h.safetensors",
    "ip_adapter_encoder": "models/image_encoder",
}

NEGATIVE_PROMPT = (
    "cartoon, illustration, cgi, 3d render, video game, plastic, toy, lowres, blurry, noisy, "
    "concentric circles, ripples, swirl pattern, banding, frosted glass, opaque windows, "
    "deformed, warped walls, bent lines, extra windows, extra doors, people, text, watermark, logo"
)

DEFAULTS = {
    "pano": {
        "work_width": 2048,       # main AI pass on a 2048 x 1024 equirect
        "pad": 128,               # horizontal wrap padding so both 360° edges see each other
        "strength": 0.70,
        "steps": 30,
        "guidance": 5.0,
        "depth_scale": 0.50,
        "canny_scale": 0.45,
        "control_end": 0.8,       # let the last 20% of steps add surface detail without the depth lock
        "seam_strength": 0.45,
        "cap_strength": 0.40,     # ceiling / floor redone as undistorted cube faces
        "refine_strength": 0.30,  # tiled detail pass at output resolution
        "refine_steps": 20,
        "out_width": 6144,
        "style_scale": 0.35,      # weight of the job's style reference image (0 = off)
    },
    "still": {
        "work_size": [1360, 768],
        "strength": 0.70,
        "steps": 30,
        "guidance": 5.0,
        "depth_scale": 0.50,
        "canny_scale": 0.45,
        "control_end": 0.8,       # let the last 20% of steps add surface detail without the depth lock
        "refine_strength": 0.30,
        "refine_steps": 20,
        "out_size": [2560, 1440],
        "style_scale": 0.35,
    },
}

# enhance(image, depth_control, canny_control, prompt, strength, steps, seed) -> image
Enhancer = Callable[..., np.ndarray]


# ---------------------------------------------------------------------------
# Control maps
# ---------------------------------------------------------------------------
def load_depth_m(path: Path) -> np.ndarray:
    """Blender depth PNG (uint16 centimetres, 0 = no geometry / sky) -> metres."""
    d = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if d is None:
        raise FileNotFoundError(path)
    if d.ndim == 3:
        d = d[..., 0]
    return d.astype(np.float32) / 100.0


def depth_control(depth_m: np.ndarray) -> np.ndarray:
    """Metric depth -> ControlNet depth image (near = white, sky = black)."""
    hit = depth_m > 0.01
    inv = np.zeros_like(depth_m, dtype=np.float32)
    inv[hit] = 1.0 / np.maximum(depth_m[hit], 0.1)
    if hit.any():
        lo, hi = np.percentile(inv[hit], [1, 99])
        inv = np.clip((inv - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    inv[~hit] = 0.0
    # Dither before quantising: 8-bit steps across a flat wall form rings the depth ControlNet paints as ripples
    noise = np.random.default_rng(0).uniform(-0.5, 0.5, inv.shape).astype(np.float32)
    g = np.clip(inv * 255 + noise, 0, 255).round().astype(np.uint8)
    return np.dstack([g, g, g])


def canny_control(rgb: np.ndarray, depth_ctl: np.ndarray) -> np.ndarray:
    """Edges of the rendered image plus depth discontinuities, so geometry edges always survive."""
    gray = cv2.bilateralFilter(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 7, 40, 7)
    edges = cv2.Canny(gray, 60, 140) | cv2.Canny(depth_ctl[..., 0], 12, 36)
    return np.dstack([edges, edges, edges])


# ---------------------------------------------------------------------------
# Equirectangular <-> perspective geometry (lon 0 at image centre, +y up)
# ---------------------------------------------------------------------------
def _rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    return ry @ rx


def latitudes(height: int) -> np.ndarray:
    return math.pi / 2 - (np.arange(height) + 0.5) / height * math.pi


def equi_to_persp(equi: np.ndarray, yaw: float, pitch: float, fov: float, size: int,
                  interp: int = cv2.INTER_CUBIC) -> np.ndarray:
    h, w = equi.shape[:2]
    t = math.tan(math.radians(fov) / 2)
    s = ((np.arange(size) + 0.5) / size * 2 - 1) * t
    xx, yy = np.meshgrid(s, -s)
    dirs = np.stack([xx, yy, np.ones_like(xx)], -1) @ _rotation(yaw, pitch).T
    lon = np.arctan2(dirs[..., 0], dirs[..., 2])
    lat = np.arcsin(np.clip(dirs[..., 1] / np.linalg.norm(dirs, axis=-1), -1, 1))
    mx = ((lon + math.pi) / (2 * math.pi) * w - 0.5).astype(np.float32)
    my = np.clip((math.pi / 2 - lat) / math.pi * h - 0.5, 0, h - 1).astype(np.float32)
    return cv2.remap(equi, mx, my, interp, borderMode=cv2.BORDER_WRAP)


def persp_to_equi(face: np.ndarray, yaw: float, pitch: float, fov: float,
                  width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Project a square perspective face back onto an equirect canvas; returns (image, valid mask)."""
    size = face.shape[0]
    t = math.tan(math.radians(fov) / 2)
    lon = (np.arange(width) + 0.5) / width * 2 * math.pi - math.pi
    lon_g, lat_g = np.meshgrid(lon.astype(np.float32), latitudes(height).astype(np.float32))
    d = np.stack([np.cos(lat_g) * np.sin(lon_g), np.sin(lat_g), np.cos(lat_g) * np.cos(lon_g)], -1)
    c = d @ _rotation(yaw, pitch).astype(np.float32)
    z = c[..., 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = c[..., 0] / z / t
        v = c[..., 1] / z / t
    valid = (z > 1e-6) & (np.abs(u) <= 1) & (np.abs(v) <= 1)
    mx = np.where(valid, (u + 1) / 2 * size - 0.5, 0).astype(np.float32)
    my = np.where(valid, (1 - v) / 2 * size - 0.5, 0).astype(np.float32)
    out = cv2.remap(face, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, valid


def _smoothstep(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _blend(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> np.ndarray:
    w = w.astype(np.float32)
    if w.ndim == 2:
        w = w[..., None]
    return np.clip(a.astype(np.float32) * (1 - w) + b.astype(np.float32) * w, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Tiled detail pass
# ---------------------------------------------------------------------------
def _positions(length: int, tile: int, overlap: int, wrap: bool) -> list[int]:
    if wrap:
        n = math.ceil(length / (tile - overlap))
        return [round(i * length / n) for i in range(n)]
    if length <= tile:
        return [0]
    n = math.ceil((length - overlap) / (tile - overlap))
    return [round(x) for x in np.linspace(0, length - tile, n)]


def refine_tiles(img: np.ndarray, dctl: np.ndarray, cctl: np.ndarray, enhance: Enhancer, *,
                 prompt: str, strength: float, steps: int, seed: int,
                 tile: int = 1024, overlap: int = 192, wrap_x: bool = False) -> np.ndarray:
    h, w = img.shape[:2]
    tile_h, tile = min(tile, h), min(tile, w)

    def ramp(n: int) -> np.ndarray:
        r = np.minimum(np.arange(n) + 1, np.arange(n)[::-1] + 1) / overlap
        return np.clip(r, 0.02, 1.0).astype(np.float32)

    win = (ramp(tile_h)[:, None] * ramp(tile)[None, :])[..., None]
    acc = np.zeros((h, w, 3), np.float32)
    wsum = np.zeros((h, w, 1), np.float32)
    k = 0
    for y in _positions(h, tile_h, overlap, wrap=False):
        for x in _positions(w, tile, overlap, wrap=wrap_x):
            cols = np.arange(x, x + tile) % w
            rows = slice(y, y + tile_h)
            out = enhance(img[rows][:, cols], dctl[rows][:, cols], cctl[rows][:, cols],
                          prompt=prompt, strength=strength, steps=steps, seed=seed + k)
            acc[rows, cols] += out.astype(np.float32) * win
            wsum[rows, cols] += win
            k += 1
    return np.clip(acc / np.maximum(wsum, 1e-6), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def finish_pano(job: dict, root: Path, enhance: Enhancer, cfg: dict) -> np.ndarray:
    base_full = read_rgb(root / job["base"])
    depth_full = load_depth_m(root / job["depth"])
    prompt, seed = job["prompt"], int(job["seed"])
    W = cfg["work_width"]
    H = W // 2
    base = cv2.resize(base_full, (W, H), interpolation=cv2.INTER_AREA)
    dctl = depth_control(cv2.resize(depth_full, (W, H), interpolation=cv2.INTER_NEAREST))
    cctl = canny_control(base, dctl)
    gen = dict(prompt=prompt, steps=cfg["steps"])

    # 1. Main pass on the full equirect, padded with its own opposite edge so the wrap is coherent
    p = cfg["pad"]
    wrap = lambda a: np.concatenate([a[:, -p:], a, a[:, :p]], axis=1)  # noqa: E731
    img = enhance(wrap(base), wrap(dctl), wrap(cctl), strength=cfg["strength"], seed=seed, **gen)[:, p:p + W]

    # 2. Seam: regenerate a square window centred on the 0/360° edge and feather it in
    shift = W // 2
    r_img, r_d, r_c = (np.roll(a, shift, axis=1) for a in (img, dctl, cctl))
    x0 = shift - H // 2
    win = (slice(None), slice(x0, x0 + H))
    fixed = enhance(r_img[win], r_d[win], r_c[win], strength=cfg["seam_strength"], seed=seed + 1, **gen)
    dist = np.abs(np.arange(H) - H / 2) / H
    wx = 1 - _smoothstep(dist, 0.15, 0.45)
    r_img[win] = _blend(r_img[win], fixed, np.broadcast_to(wx[None, :], (H, H)))
    img = np.roll(r_img, -shift, axis=1)

    # 3. Ceiling and floor: redo as undistorted 90° cube faces, blended in above |lat| 50°
    lat = np.degrees(latitudes(H))
    for pitch, extra in ((90, 2), (-90, 3)):
        face = equi_to_persp(img, 0, pitch, 90, H)
        fbase = equi_to_persp(base, 0, pitch, 90, H)
        fd = equi_to_persp(dctl, 0, pitch, 90, H, interp=cv2.INTER_LINEAR)
        out = enhance(face, fd, canny_control(fbase, fd), strength=cfg["cap_strength"], seed=seed + extra, **gen)
        back, valid = persp_to_equi(out, 0, pitch, 90, W, H)
        wy = _smoothstep(np.sign(pitch) * lat, 50, 62)
        img = _blend(img, back, valid * wy[:, None])

    # 4. Upscale and add detail tile by tile at output size (band only; poles stay smooth)
    OW = cfg["out_width"]
    OH = OW // 2
    up = cv2.resize(img, (OW, OH), interpolation=cv2.INTER_LANCZOS4)
    base_up = cv2.resize(base_full, (OW, OH), interpolation=cv2.INTER_CUBIC)
    dctl_up = depth_control(cv2.resize(depth_full, (OW, OH), interpolation=cv2.INTER_NEAREST))
    refined = refine_tiles(up, dctl_up, canny_control(base_up, dctl_up), enhance, prompt=prompt,
                           strength=cfg["refine_strength"], steps=cfg["refine_steps"], seed=seed + 10,
                           wrap_x=True)
    band = 1 - _smoothstep(np.abs(np.degrees(latitudes(OH))), 55, 68)
    out = _blend(up, refined, np.broadcast_to(band[:, None], (OH, OW)))
    out[:, -1] = out[:, 0] = ((out[:, 0].astype(np.uint16) + out[:, -1]) // 2).astype(np.uint8)
    return out


def finish_still(job: dict, root: Path, enhance: Enhancer, cfg: dict) -> np.ndarray:
    base_full = read_rgb(root / job["base"])
    depth_full = load_depth_m(root / job["depth"])
    prompt, seed = job["prompt"], int(job["seed"])
    ww, wh = cfg["work_size"]
    base = cv2.resize(base_full, (ww, wh), interpolation=cv2.INTER_AREA)
    dctl = depth_control(cv2.resize(depth_full, (ww, wh), interpolation=cv2.INTER_NEAREST))
    img = enhance(base, dctl, canny_control(base, dctl), prompt=prompt, strength=cfg["strength"],
                  steps=cfg["steps"], seed=seed)

    rw, rh = ww * 2, wh * 2
    up = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
    base_up = cv2.resize(base_full, (rw, rh), interpolation=cv2.INTER_CUBIC)
    dctl_up = depth_control(cv2.resize(depth_full, (rw, rh), interpolation=cv2.INTER_NEAREST))
    refined = refine_tiles(up, dctl_up, canny_control(base_up, dctl_up), enhance, prompt=prompt,
                           strength=cfg["refine_strength"], steps=cfg["refine_steps"], seed=seed + 10)
    return cv2.resize(refined, tuple(cfg["out_size"]), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# Enhancers
# ---------------------------------------------------------------------------
def dry_run_enhancer(img: np.ndarray, dctl: np.ndarray, cctl: np.ndarray, **_: object) -> np.ndarray:
    """Stand-in for the GPU model: returns the input so geometry, seams and I/O can be checked on CPU."""
    return img.copy()


def build_diffusers_enhancer(models: dict = MODELS, pipe=None, use_style: bool = False) -> Enhancer:
    import torch
    from diffusers import (AutoencoderKL, ControlNetModel, DPMSolverMultistepScheduler,
                           StableDiffusionXLControlNetImg2ImgPipeline)

    style_ready = False
    if pipe is None:
        dtype = torch.float16
        controlnets = [ControlNetModel.from_pretrained(models[k], torch_dtype=dtype)
                       for k in ("controlnet_depth", "controlnet_canny")]
        vae = AutoencoderKL.from_pretrained(models["vae"], torch_dtype=dtype)
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
            models["base"], controlnet=controlnets, vae=vae, torch_dtype=dtype, variant="fp16")
        if use_style:
            subfolder, weight = models["ip_adapter_weight"].rsplit("/", 1)
            try:
                pipe.load_ip_adapter(models["ip_adapter"], subfolder=subfolder, weight_name=weight,
                                     image_encoder_folder=models["ip_adapter_encoder"])
                style_ready = True
            except Exception as exc:  # style is optional: carry on with geometry + prompt only
                print(f"[finish] style reference disabled, IP-Adapter failed to load: {exc}", flush=True)
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 2**30
        if vram_gb < 20:
            pipe.enable_model_cpu_offload()
        else:
            pipe.to("cuda")
        pipe.vae.enable_tiling()  # pipeline-level enable_vae_tiling() was removed in diffusers 0.42
        pipe.set_progress_bar_config(disable=True)

    neutral = Image.new("RGB", (224, 224), (128, 128, 128))

    def enhance(img: np.ndarray, dctl: np.ndarray, cctl: np.ndarray, *, prompt: str, strength: float,
                steps: int, seed: int, guidance: float = 5.0, depth_scale: float = 0.5,
                canny_scale: float = 0.45, control_end: float = 1.0, style: np.ndarray | None = None,
                style_scale: float = 0.0) -> np.ndarray:
        extra = {}
        if style_ready:
            # Once loaded, the adapter needs an image every call; scale 0 turns it off for jobs without a reference
            pipe.set_ip_adapter_scale(style_scale if style is not None else 0.0)
            extra["ip_adapter_image"] = Image.fromarray(style) if style is not None else neutral
        result = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            image=Image.fromarray(img),
            control_image=[Image.fromarray(dctl), Image.fromarray(cctl)],
            strength=strength,
            num_inference_steps=steps,
            guidance_scale=guidance,
            controlnet_conditioning_scale=[depth_scale, canny_scale],
            control_guidance_end=[control_end, control_end],
            generator=torch.Generator("cpu").manual_seed(seed),
            **extra,
        ).images[0]
        out = np.asarray(result.convert("RGB"))
        if out.shape[:2] != img.shape[:2]:
            out = cv2.resize(out, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LANCZOS4)
        return out

    return enhance


def _bind(enhance: Enhancer, cfg: dict, style: np.ndarray | None) -> Enhancer:
    """Bind per-kind guidance, ControlNet weights and the job's style image so job code only passes what varies."""
    def bound(img, dctl, cctl, **kw):
        kw.setdefault("guidance", cfg["guidance"])
        kw.setdefault("depth_scale", cfg["depth_scale"])
        kw.setdefault("canny_scale", cfg["canny_scale"])
        kw.setdefault("control_end", cfg["control_end"])
        kw.setdefault("style", style)
        kw.setdefault("style_scale", cfg["style_scale"])
        return enhance(img, dctl, cctl, **kw)
    return bound


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(inputs: Path, out_dir: Path, only: list[str] | None, dry_run: bool, skip_existing: bool = False) -> dict:
    jobs = json.loads((inputs / "jobs.json").read_text(encoding="utf-8"))
    settings = {kind: {**DEFAULTS[kind], **jobs.get("settings", {}).get(kind, {})} for kind in DEFAULTS}
    use_style = any(job.get("style") and settings[kind]["style_scale"] > 0
                    for kind in DEFAULTS for job in jobs[kind + "s"])
    enhance_raw = dry_run_enhancer if dry_run else build_diffusers_enhancer(use_style=use_style)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"models": MODELS, "items": {}}
    manifest["dry_run"] = dry_run

    for kind, folder, finish in (("pano", "panoramas", finish_pano), ("still", "stills", finish_still)):
        cfg = settings[kind]
        for job in jobs[kind + "s"]:
            if only and job["id"] not in only:
                continue
            dest = out_dir / folder / f"{job['id']}.png"
            if skip_existing and dest.exists() and job["id"] in manifest["items"]:
                print(f"[finish] {job['id']}: already done", flush=True)
                continue
            t0 = time.time()
            style = read_rgb(inputs / job["style"]) if job.get("style") else None
            out = finish(job, inputs, _bind(enhance_raw, cfg, style), cfg)
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(out).save(dest)
            manifest["items"][job["id"]] = {
                "kind": kind,
                "output": f"{folder}/{dest.name}",
                "size": [out.shape[1], out.shape[0]],
                "base_sha256": _sha256(inputs / job["base"]),
                "depth_sha256": _sha256(inputs / job["depth"]),
                "prompt": job["prompt"],
                "style_ref": job.get("style"),
                "seed": job["seed"],
                "settings": cfg,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"[finish] {job['id']}: {out.shape[1]}x{out.shape[0]} in {time.time() - t0:.0f}s", flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="AI finishing pass for Blender base renders of the Vibgyor model.")
    parser.add_argument("--inputs", type=Path, required=True, help="Unzipped vibgyor_ai_inputs folder")
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--only", nargs="*", help="Job ids to run (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Skip the model; check geometry and I/O on CPU")
    parser.add_argument("--skip-existing", action="store_true", help="Resume: keep outputs already in the manifest")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run(args.inputs, args.out, args.only, args.dry_run, args.skip_existing)


if __name__ == "__main__":
    main()
