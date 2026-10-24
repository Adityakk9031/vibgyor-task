"""
Vibgyor Automated Pipeline Entry Point (build.py).

Usage:
    python build.py              # Run all stages: extract -> build -> render -> export
    python build.py extract      # Stage 1: DXF to clean 2D geometry JSON
    python build.py build        # Stage 2: 2D geometry JSON to 3D .blend model
    python build.py render       # Stage 3: Render 4 photorealistic views (>=2560px) + 360° panorama
    python build.py export       # Stage 4: Export web-ready .glb (<=40 MB)
"""

from __future__ import annotations

import argparse
import sys
import time

from pipeline.extract import extract_geometry
from pipeline.build_model import build_model
from pipeline.render import render_all
from pipeline.export import export_glb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vibgyor automated DXF -> 3D Model -> Renders -> Interactive Web Viewer pipeline."
    )
    parser.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=["all", "extract", "build", "render", "export"],
        help="Pipeline stage to execute (default: all)",
    )
    parser.add_argument(
        "--skip-panorama",
        action="store_true",
        help="Skip rendering the bonus 4096x2048 360° interior panorama",
    )
    args = parser.parse_args(argv)

    t0 = time.time()
    stage = args.stage

    if stage in ("all", "extract"):
        print("\n=== STAGE 1: EXTRACT (DXF -> Clean 2D Geometry JSON) ===")
        extract_geometry()

    if stage in ("all", "build"):
        print("\n=== STAGE 2: BUILD (2D Geometry -> 3D Blender Model) ===")
        build_model()

    if stage in ("all", "export"):
        print("\n=== STAGE 4: EXPORT (3D Model -> Web .glb <= 40 MB) ===")
        export_glb()

    if stage in ("all", "render"):
        print("\n=== STAGE 3: RENDER (Photorealistic Still Renders >= 2560 px + 360° Panorama) ===")
        render_all(render_bonus_panorama=not args.skip_panorama)

    elapsed = time.time() - t0
    print(f"\n[pipeline] Completed '{stage}' in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
