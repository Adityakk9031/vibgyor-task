"""
Asset helper: Downloads free CC0 Poly Haven HDRIs (and fallback procedural generation)
for realistic lighting and PBR rendering.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path


POLYHAVEN_HDRIS = {
    "day": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/kloppenheim_06_puresky_1k.hdr",
    "dusk": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/venice_sunset_1k.hdr",
    "interior": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/photo_studio_loft_hall_1k.hdr",
}


def ensure_assets(assets_dir: str | Path = "assets") -> dict[str, Path]:
    base = Path(assets_dir)
    hdri_dir = base / "hdri"
    hdri_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for key, url in POLYHAVEN_HDRIS.items():
        fname = url.split("/")[-1]
        target = hdri_dir / fname
        if not target.exists() or target.stat().st_size < 10000:
            try:
                print(f"[assets] Downloading CC0 Poly Haven HDRI ({key}): {fname} ...")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp, open(target, "wb") as f:
                    f.write(resp.read())
                print(f"[assets] Downloaded {target} ({target.stat().st_size // 1024} KB)")
            except Exception as exc:
                print(f"[assets] Warning: Could not download {url} ({exc}); will use procedural sky.")
        if target.exists() and target.stat().st_size >= 10000:
            paths[key] = target.resolve()
    return paths


if __name__ == "__main__":
    ensure_assets()
