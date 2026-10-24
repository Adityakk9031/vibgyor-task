# Vibgyor — Automated DXF to 3D Model, Renders & Interactive Web Viewer

An end-to-end automated architectural pipeline that reads the municipal submission drawing (`SUBMISSION - 04.dxf` / `.dwg`) for **Vibgyor** (a 7-storey residential tower in Prahlad Nagar, Ahmedabad with stilt parking, $2 \times \text{4BHK}$ units per floor, and a terrace) and generates:

1. **Clean 2D Geometry (`outputs/extracted_geometry.json`)** — Reconstructed closed polygons for slabs, 23 structural columns, walls, $0.60\text{ m}$ architectural projections, windows, sliding glass doors, balconies, RERA carpet floor plates (Type A & Type B), and site/landscape layout.
2. **Generated 3D Model (`outputs/vibgyor.blend`)** — Built procedurally in headless Blender (`bpy`) with real dimensions in metres, matching the developer's exterior render (`brochure/exterior.jpg`). Includes the Type A 1st-floor interior for the $360^\circ$ panorama bonus.
3. **Photorealistic Still Renders (`outputs/*.png`)** — Rendered with Blender Cycles at $2560 \times 1440\text{ px}$ using CC0 Poly Haven HDRIs, sun lighting, procedural PBR materials, and AgX tone mapping:
   - `outputs/shot_1_eye_level_day.png`: Eye level from the $18\text{ m}$ main road (Day)
   - `outputs/shot_2_front_corner_dusk.png`: Front corner view with warm interior & facade lights on (Dusk)
   - `outputs/shot_3_aerial_day.png`: Aerial view ($\approx 45^\circ$) showing the building on its plot (Day)
   - `outputs/shot_4_entrance_closeup.png`: Close-up of the entrance canopy, wooden gate & illuminated `VIBGYOR` wall (Day)
   - `outputs/bonus_type_a_panorama_360.png`: **Bonus** $4096 \times 2048\text{ px}$ $360^\circ$ equirectangular panorama of the Type A Drawing Room.
4. **Web-Ready 3D Model (`outputs/vibgyor.glb`, $\approx 7.5\text{ MB} \le 40\text{ MB}$)** & **Interactive Web Viewer (`viewer/index.html`)** — Three.js viewer with HDRI sky, sun shadows, AgX/ACES tone mapping, camera presets, Day/Dusk toggle, and interactive floor & flat (Type A / Type B) selection.

---

## Quick Start

### 1. Prerequisites & Setup

Requires **Python 3.11 – 3.13** (on macOS, Linux, or Windows). Headless Blender (`bpy`) is installed directly via `pip`:

```bash
pip install -r requirements.txt
```

### 2. Run the Full Pipeline (One Command)

Produces all outputs (`outputs/extracted_geometry.json`, `outputs/vibgyor.blend`, `outputs/vibgyor.glb`, and all renders in `outputs/`):

```bash
python build.py
# or on macOS / Linux:
make all
```

### 3. Run Individual Pipeline Stages

Each stage can be run independently:

```bash
# Stage 1: Extract clean 2D geometry JSON from SUBMISSION - 04.dxf
python build.py extract      # or: make extract

# Stage 2: Build 3D Blender scene (outputs/vibgyor.blend)
python build.py build        # or: make build

# Stage 3: Render 4 still views (2560x1440) + Bonus 360° panorama (4096x2048)
python build.py render       # or: make render

# Stage 4: Export web-ready glTF binary (outputs/vibgyor.glb <= 40 MB)
python build.py export       # or: make export
```

### 4. Run Extraction Unit Tests (Bonus)

```bash
python -m pytest -v          # or: make test
```

### 5. Launch the Interactive Web Viewer

Serve the `viewer/` directory over local HTTP and open `http://localhost:8080` in your browser:

```bash
python -m http.server 8080 --directory viewer
# or: make serve
```

---

## Repository Structure

```text
.
├── config.json                 # Documented config: heights from Section A-A, DXF regions, layers & PBR materials
├── build.py                    # Single-command CLI entry point (extract | build | render | export | all)
├── Makefile                    # make all | extract | build | render | export | test | serve
├── requirements.txt            # Python dependencies (ezdxf, shapely, trimesh, bpy, pytest)
├── NOTES.md                    # Engineering notes: DXF parsing, config design, edge cases & next steps
├── pipeline/
│   ├── extract.py              # Stage 1: DXF -> outputs/extracted_geometry.json
│   ├── build_model.py          # Stage 2: 2D JSON -> outputs/vibgyor.blend
│   ├── render.py               # Stage 3: Cycles rendering (4 shots @ 2560x1440 + 360° panorama @ 4096x2048)
│   ├── export.py               # Stage 4: .blend -> outputs/vibgyor.glb (7.5 MB)
│   └── assets.py               # Auto-downloads CC0 Poly Haven HDRIs (Kloppenheim Day & Venice Sunset)
├── viewer/
│   ├── index.html              # Interactive Three.js web viewer (HDRI, shadows, AgX, floor & flat picking)
│   └── vibgyor.glb             # Copy of exported .glb for instant serving
├── tests/
│   └── test_extract.py         # Pytest suite verifying DXF extraction accuracy
└── outputs/
    ├── extracted_geometry.json # Clean 2D polygons & metadata in metres
    ├── vibgyor.blend           # Generated Blender 3D scene
    ├── vibgyor.glb             # Generated web model (7.5 MB)
    ├── shot_1_eye_level_day.png
    ├── shot_2_front_corner_dusk.png
    ├── shot_3_aerial_day.png
    ├── shot_4_entrance_closeup.png
    └── bonus_type_a_panorama_360.png
```
