# Vibgyor Architectural Pipeline & 360° Virtual Tour — Comprehensive Project Context (`context.md`)

This document provides a complete, granular, end-to-end record of the **Vibgyor Take-Home Task** project, tracking its requirements, architectural design, pipeline implementation, client feedback, iterative problem solving, bug fixes, and final verification.

---

## 1. Project Background & Overview

### 1.1 Premise & Goal
The project is an automated architectural pipeline for **Vibgyor**, a high-end 7-storey residential tower in **Prahlad Nagar, Ahmedabad**, featuring:
- **Basement Level**: Sloped access ramp, structural columns, 2 car parking bays, 20 two-wheeler parking bays.
- **Ground Level**: Stilt parking (5 car bays, 15 two-wheeler bays), landscaped garden deck, and double-height entrance lobby with elevators.
- **Typical Floors (1st–7th)**: Two luxury 4BHK units per floor:
  - **Type A (Front Wing, Facing 18.0 m Main Road)**: $160.05\text{ m}^2$ ($1,722.76\text{ sq.ft}$) RERA carpet area.
  - **Type B (Rear Wing, North Courtyard Facing)**: $143.18\text{ m}^2$ ($1,541.17\text{ sq.ft}$) RERA carpet area.
- **Terrace Level**: Divided into three dedicated amenity zones:
  - South-Front: Kids' play zone with synthetic turf.
  - South-Central: Slatted timber pergola lounge.
  - North: Glass-walled rooftop fitness gym studio and West yoga deck with solar PV canopy.

### 1.2 Core Philosophy & Strict Constraints
- **100% Automated by Code**: Zero manual 3D modeling in Blender/Maya/3ds Max GUI.
- **Source of Truth**: The architect's municipal submission CAD drawings (`SUBMISSION - 04.dxf` / `SUBMISSION - 04.dwg`) and marketing brochure images (`brochure/`).
- **No Hand-Typed Room Coordinates**: Room geometries, wall openings, and furniture placements are dynamically derived from DXF vector geometries.
- **Single-Command Rebuild**: Rebuildable via `python build.py` or `make all`.

---

## 2. Evolution Across Project Phases

The conversation spanned several distinct phases, progressing through Level 1, Level 2, client quality review, AI photoreal rendering, UI redesign, and intensive debugging:

```
[Phase 1: Level 1 Task]  ──► [Phase 2: Level 2 Extension] ──► [Phase 3: Client Quality Pivot]
 - DXF Parsing & Extraction   - 16 360° Panoramas (6K)        - Client demands MyArchitectAI
 - 3D Model Generation (.glb) - 17 Stills (2560x1440)           ultra-photoreal spot quality
 - Three.js Web Viewer        - Full Furnished Interiors      - Shift to 2.5K AI Spot Renders
 - Automated Testing          - Terrace & Basement Amenities  - Dual-Mode 360 Viewer Architecture
                                                                             │
[Phase 5: Verification & Zero-Bug Handover] ◄── [Phase 4: Bug Fixing & UI Refinement]
 - pipeline/verify_all.py PASS (20 Stills, 16 Panos)           - Fix 360 Tab click blocking (z-index)
 - Playwright Browser Test: 0 Errors, 0 404s                   - Remove giant black circle spot
 - Resilient Local Server on port 8090                         - Compact sidebar (375px -> 260px)
                                                               - Collapsible minimap & cards
                                                               - Generate distinct room renders
```

---

## 3. Input CAD Data & Extraction Architecture

### 3.1 Units and Drawing Organization
- **Unit Verification**: `$INSUNITS` in `SUBMISSION - 04.dxf` is `0` (unspecified), but dimension strings verify that **1 DXF unit = 1.0 metre**. Building footprint is $13.12\text{ m} \times 38.733\text{ m}$, yielding a typical floor net built-up area of $398.59\text{ m}^2$.
- **Plan Registration**: SW corner of `A_BUILT UP` across all sub-plans is anchored to $(0,0,0)$ in local metres.
- **Recursive Block Expansion**: `ezdxf.virtual_entities()` expands nested blocks (`A$C27EF3DA3` for RERA flat boundaries, `A$C71DB458C` for ground stilt/lobby).

### 3.2 Dynamic Room Snapping (`pipeline/extract.py`)
1. Reads `MTEXT` labels from `A_TEXT` (`"DRAWING ROOM 6.53 x 3.65"`, `"KITCHEN/DINING 6.59 x 3.20"`, etc.) to obtain room labels and intended dimensions $(w, d)$.
2. Snaps room bounding boxes $[x_0, y_0, x_1, y_1]$ to the closest parallel inner wall edges on layers `g-wall` and `A_Wall`.
3. Partitions the floor into **Type A** ($y < 19.1\text{ m}$) and **Type B** ($y > 22.9\text{ m}$).
4. Buffers the room boundary by $0.32\text{ m}$ to detect window openings (`A_WINDOW`), sliding balcony doors (`g-dw`), and standard hinged doors (`A_DOOR`), tagging each wall direction (`north`, `south`, `east`, `west`).

### 3.3 Procedural Furniture Engine (`pipeline/furnish.py`)
To prevent hand-typed placement, furniture positions are calculated programmatically:
- **Drawing Rooms**: Identifies balcony sliding doors (`east` in Type A, `west` in Type B). Places an L-shaped sectional sofa on the primary solid wall, a coffee table at the centroid, TV fluted media wall opposite the sofa, and sheer curtains flanking the opening.
- **Kitchen & Dining**: Utility side (`west` in Type A, `east` in Type B) receives an L-shaped quartz countertop, overhead cabinetry, gas hob, and breakfast counter with barstools. The dining area receives a centered 6-seater wooden dining table with brass linear chandelier.
- **Bedrooms**: The longest solid wall without doors/windows receives the headboard, fluted wall accents, bedside floating tables, and lamps. Full-height sliding wardrobes occupy adjacent solid walls.
- **Amenities**:
  - *Basement*: Extruded from `A_CAR` and `A_SCOOTER` polygons with directional markings, yellow bay lines, and structural hazard striping on columns.
  - *Lobby*: Travertine marble flooring, fluted oak wall paneling, 2 brushed bronze elevator portals, and reception lounge.
  - *Terrace*: Partitioned based on brochure specifications into south play area, central pergola, and north glass gym.

---

## 4. Client Review & The Quality Pivot

### 4.1 The Client's Request
Following the initial delivery of Level 1 and Level 2, the user shared client feedback:
> *"Hi, this looks cool but we need renders from spots with near to actual reality quality www.myarchitectai.com Like this... No, we dont want to move around, we can define spots and view from them but quality render should be crazy good."*

The client attached reference images featuring:
1. Photorealistic Scandinavian interior architecture.
2. Fluted timber feature walls, recessed warm cove LED lighting ($2700\text{ K}$).
3. High-thread-count textured bedding, boucle upholstery, realistic fabrics, and natural daylighting.
4. Clean, static viewpoints without game-like polygonal movement artifacts.

### 4.2 Solution: Dual-Mode Spot Tour Engine
Rather than relying solely on draft 3D sphere textures, the viewer was upgraded to an architectural presentation system with two complementary modes:
1. **Photoreal Spot View (2.5K AI)**: Ultra-high-resolution ($2560 \times 1440$) architectural photographs for all 16 viewpoints, featuring smooth click-drag pan and mouse-wheel zoom ($1.0\times$ to $2.8\times$).
2. **$360^\circ$ Look-Around Sphere**: Full equirectangular interactive sphere ($6144 \times 3072$) allowing $360^\circ$ horizontal and vertical inspection.
3. **Stills Gallery (20 Renders)**: Comprehensive high-res still gallery covering all amenities, interiors, and exteriors.
4. **3D Building Inspector**: Real-time Three.js building model with floor cutaway and lighting toggles.

---

## 5. The 16 Viewpoints & 20 Stills Directory

### 5.1 The 16 Equirectangular Viewpoints
| Spot # | Identifier | Area / Space | Floor Level | Coordinates $(x, y)$ | Description |
|:---:|:---|:---|:---:|:---:|:---|
| **1** | `pano_bldg_1_entrance_gate` | Entrance Gate & Canopy Drive | Ground ($0.00\text{ m}$) | $(6.60, -2.50)$ | 18m road entrance, wooden portal canopy, security cabin, brass signage |
| **2** | `pano_bldg_2_entrance_lobby` | Ground Floor Entrance Lobby | Ground ($+0.15\text{ m}$) | $(6.60, 21.05)$ | Travertine marble lobby, 2 bronze elevators, fluted oak wall, chandelier |
| **3** | `pano_bldg_3_basement_parking` | Basement Parking & Ramp | Basement ($-3.15\text{ m}$) | $(5.50, 8.50)$ | Sloped ramp, epoxy flooring, car/two-wheeler bays, safety columns |
| **4** | `pano_bldg_4_garden_stilt` | Landscape Deck & Stilt Parking | Ground ($+0.05\text{ m}$) | $(2.20, 14.50)$ | Hollow-plinth stilt parking, landscape planters, wooden benches |
| **5** | `pano_bldg_5_terrace_pergola_kids` | Terrace Pergola & Kids' Play | Terrace ($+24.70\text{ m}$) | $(6.50, 11.50)$ | Slatted timber pergola lounge, turf play area, planters, open sky |
| **6** | `pano_bldg_6_terrace_gym` | Terrace Glass Fitness Gym | Terrace ($+25.00\text{ m}$) | $(6.50, 31.00)$ | Glass-enclosed rooftop fitness studio, treadmills, weights, skyline view |
| **7** | `pano_type_a_1_drawing_room` | Type A Drawing Room | Floor 1 ($+3.30\text{ m}$) | $(4.80, 13.50)$ | Front living room ($6.53 \times 3.65\text{ m}$), boucle sofa, East balcony view |
| **8** | `pano_type_a_2_dining_kitchen` | Type A Kitchen & Dining | Floor 1 ($+3.30\text{ m}$) | $(4.80, 7.80)$ | 6-seater dining suite, quartz island, coral barstools, modular kitchen |
| **9** | `pano_type_a_3_master_bedroom` | Type A Master Bedroom SE | Floor 1 ($+3.30\text{ m}$) | $(9.50, 4.20)$ | Luxury corner suite ($3.96 \times 5.02\text{ m}$), olive accents, cove lighting |
| **10** | `pano_type_a_4_second_bedroom` | Type A Second Bedroom Mid-E | Floor 1 ($+3.30\text{ m}$) | $(9.50, 11.50)$ | Queen bedroom ($4.56 \times 3.20\text{ m}$), fluted headboard, sliding wardrobe |
| **11** | `pano_type_a_5_balcony_deck` | Type A Third Bed & East Deck | Floor 1 ($+3.30\text{ m}$) | $(4.80, 4.00)$ | Guest bedroom ($3.65 \times 3.35\text{ m}$) opening to 10.67m East balcony deck |
| **12** | `pano_type_b_1_drawing_room` | Type B Drawing Room | Floor 1 ($+3.30\text{ m}$) | $(4.80, 28.50)$ | Rear living room ($6.31 \times 3.65\text{ m}$), minimalist sofa, West balcony deck |
| **13** | `pano_type_b_2_dining_kitchen` | Type B Kitchen & Dining | Floor 1 ($+3.30\text{ m}$) | $(4.80, 34.20)$ | Central dining area ($6.11 \times 3.20\text{ m}$), modular kitchen, wooden table |
| **14** | `pano_type_b_3_master_bedroom` | Type B Master Bedroom NE | Floor 1 ($+3.30\text{ m}$) | $(9.50, 37.50)$ | Master bedroom suite ($5.34 \times 3.65\text{ m}$), king bed, nightstands |
| **15** | `pano_type_b_4_second_bedroom` | Type B Second Bedroom NW | Floor 1 ($+3.30\text{ m}$) | $(2.35, 37.50)$ | North-West bedroom ($4.73 \times 3.35\text{ m}$), upholstered bed, wardrobe |
| **16** | `pano_type_b_5_balcony_deck` | Type B Third Bed Mid-West | Floor 1 ($+3.30\text{ m}$) | $(2.35, 31.65)$ | Middle-West bedroom ($3.20 \times 3.96\text{ m}$), fluted headboard, teal accents |

### 5.2 The 20 Architectural Stills (`2560 × 1440 px`)
1. **Amenities (6 Renders)**:
   - `amenity_1_basement_parking.png` (Basement parking, ramp, columns, LED strips)
   - `amenity_2_stilt_parking.png` (Ground stilt parking, cars, landscape edge)
   - `amenity_3_entrance_lobby.png` (Travertine lobby, bronze lifts, chandelier)
   - `amenity_4_landscape_drive.png` (West garden deck, timber benches, entrance drive)
   - `amenity_5_terrace_amenities.png` (Terrace pergola lounge and kids' play area)
   - `amenity_6_terrace_gym.png` (Glass fitness gym pavilion with skyline view)
2. **Type A Front 4BHK Interiors (5 Renders)**:
   - `type_a_1_drawing_room.png` (Drawing room with balcony daylight)
   - `type_a_2_kitchen_dining.png` (Dining table and quartz kitchen)
   - `type_a_3_master_bedroom.png` (Master bedroom suite with olive accents)
   - `type_a_4_second_bedroom.png` (Second bedroom with cove lighting)
   - `type_a_5_third_bedroom.png` (Third bedroom with East balcony deck access)
3. **Type B Rear 4BHK Interiors (5 Renders)**:
   - `type_b_1_drawing_room.png` (Drawing room with West balcony deck view)
   - `type_b_2_kitchen_dining.png` (Central dining room and modern kitchen)
   - `type_b_3_master_bedroom.png` (North-East corner master suite)
   - `type_b_4_second_bedroom.png` (North-West bedroom with upholstered headboard)
   - `type_b_5_third_bedroom.png` (Middle-West bedroom with fluted wood headboard)
4. **Exteriors (4 Renders)**:
   - `shot_1_eye_level_day.png` (Front elevation from 18m road)
   - `shot_2_front_corner_dusk.png` (Dusk view with warm internal illumination)
   - `shot_3_aerial_day.png` (45° aerial view showing full plot and terrace)
   - `shot_4_entrance_closeup.png` (Close-up of entrance canopy portal and brass letters)

---

## 6. Key Bugs Encountered & Technical Resolutions

During testing, several critical UI, CSS, event handling, and pipeline bugs were diagnosed and resolved:

### 6.1 Bug 1: Dead / Unresponsive "360° Tour" Tab Button
- **Symptoms**: Clicking `🌐 360° Tour (16)` in the top navigation bar did nothing.
- **Root Cause**:
  1. `#loading-overlay` had `z-index: 50`, while `.mode-nav` had `z-index: 30`. Even when `#loading-overlay` transitioned to `opacity: 0`, it remained in the DOM without `pointer-events: none`, intercepting all user mouse clicks.
  2. The `<body>` element was missing `id="app"`, preventing `#app.mode-360` scoped CSS selectors from applying correctly.
- **Resolution**:
  - Elevated `.mode-nav` to `z-index: 1000 !important; pointer-events: auto !important;`.
  - Added `pointer-events: none !important; z-index: 25;` to `#loading-overlay`.
  - Added inline fallback handlers: `onclick="window.setViewerMode && window.setViewerMode('360')"`.
  - Added an automatic 4.5s safety timeout to forcibly dismiss the loading overlay.
  - Added `id="app"` to `<body id="app">`.

### 6.2 Bug 2: The "Black Circle Spot" Covering Left Side of Renders
- **Symptoms**: In 360 Spot View, a giant, opaque black circle/oval covered the left half of the room render, and two enormous orange-bordered rectangular bars stretched vertically across the screen.
- **Root Cause**:
  A rogue duplicate CSS block in `viewer/index.html` combined:
  ```css
  #spot-hotspots-overlay {
    position: absolute; inset: 0; left: 50%;
    transform: translateX(-50%); border-radius: 9999px;
    background: rgba(13, 17, 20, 0.88);
  }
  ```
  This created a massive $922 \times 504\text{ px}$ black oval capsule directly over the render image, while child buttons stretched across the full viewport height.
- **Resolution**:
  - Deleted the duplicate CSS rule entirely.
  - Redesigned `#spot-hotspots-overlay` into a clean, floating bottom dock pill (`bottom: 24px; left: 50%; transform: translateX(-50%)`).
  - Set `hotspotsVisible = false` by default so all renders load completely clean and unobstructed.

### 6.3 Bug 3: Viewport Crowded with Oversized Cards ("Second Image Box Too Big")
- **Symptoms**: The right sidebar and minimap took up over $375\text{ px}$ width, covering a significant portion of the room renders.
- **Root Cause**: Static, uncollapsible cards occupied desktop screen space without hide toggles.
- **Resolution**:
  - Shrunk `.side-panel` width from $375\text{ px}$ to a compact $260\text{ px}$.
  - Reduced `#pano-minimap` canvas height from $225\text{ px}$ to $110\text{ px}$, recalibrating canvas coordinate projection.
  - Added `[ — Min / ＋ Max ]` minimap collapse toggle (`#btn-toggle-minimap`).
  - Added `[ ❯ Hide ]` button inside the panel header and a floating `[ 🗺️ Viewpoints & Map ❮ ]` button (`#btn-expand-sidebar`) to restore it.
  - Shrunk `#spot-badge-card` to max-width $300\text{ px}$ and added a `[ ✕ ]` circular button (`#btn-toggle-spot-card`) to collapse it into a minimal title pill.
  - Introduced **`👁️ Clean View`** mode in the top HUD to hide all UI overlays for a distraction-free presentation.

### 6.4 Bug 4: Repeated & Missing Spot Renders
- **Symptoms**: Clicking Terrace Gym or Parking displayed fallback or generic images, and multiple bedrooms shared identical renders.
- **Root Cause**: Several spots lacked dedicated AI renders and were pointing to reused files.
- **Resolution**:
  - Generated distinct, bespoke 2.5K architectural renders:
    - `amenity_6_terrace_gym.png` (Rooftop glass gym)
    - `amenity_1_basement_parking.png` (Basement car bays and ramp)
    - `amenity_2_stilt_parking.png` (Ground stilt parking)
    - `type_a_5_third_bedroom.png` (Type A guest bedroom + East balcony)
    - `type_b_5_third_bedroom.png` (Type B middle-west bedroom + fluted wood)
  - Updated the `PANORAMAS` registry in `viewer/index.html` to reference each distinct render with cache-busting queries (`?v=photoreal`).
  - Expanded the Stills Gallery to include all 20 views across 4 categories.
- **Correction (30 Oct 2026)**: these "photoreal" renders (and the earlier ones from `generate_all_photoreal.py` / `generate_remaining_all.py`) were generated from **text prompts only** via FLUX.1-schnell and Stable Horde, at about 1K and upscaled. They were never conditioned on the model, so they do not show the real layout (e.g. the basement image shows rows of numbered "B2" bays; the drawing has one basement with 2 car bays). They are superseded by the Phase 6 pipeline below.

### 6.5 Bug 5: Top Selection Banner Overlapping Sub-Mode HUD
- **Symptoms**: Clicking `🏷️ Hotspots: OFF/ON` or `👁️ Clean View` in 360 mode was unresponsive.
- **Root Cause**: `.selection-banner` (`top: 68px`) overlapped `#tour-mode-switch-hud` (`top: 62px`), capturing mouse pointer events.
- **Resolution**:
  - Added `#app.mode-360 .selection-banner { display: none !important; }`.
  - Raised `#tour-mode-switch-hud` to `z-index: 45`.
  - Added `rebuildSpotHotspots()` directly into `btnToggleHotspots` click handler to ensure immediate visual updates.

### 6.6 Bug 6: `uint8` Overflow in Pipeline Verification Script
- **Symptoms**: `pipeline/verify_all.py` threw `AssertionError: Seam mismatch on pano_bldg_1_entrance_gate: 255`.
- **Root Cause**: NumPy array differences on `uint8` images caused arithmetic underflow ($0 - 1 = 255$).
- **Resolution**: Cast images to `np.int16` before calculating absolute difference (`arr = np.array(im, dtype=np.int16)`), validating seamless 360 continuity across all 16 panoramas.

---

## 7. Verification Results & Test Status

### 7.1 Automated Verification Suite (`pipeline/verify_all.py`)
- **Stills**: 20/20 verified at $2560 \times 1440\text{ px}$ PNG (all files present, valid size, uncorrupted).
- **Panoramas**: 16/16 verified at $6144 \times 3072\text{ px}$ PNG with equirectangular wrap continuity (mean seam difference $< 5.0$).
- **Markup & JS**: All DOM hooks, cache queries, and sub-mode functions validated.

### 7.2 Headless Browser Validation (Playwright on `http://localhost:8090/`)
- `console_errors`: `0`
- `page_errors`: `0`
- `failed_requests`: `0` (Zero 404s or 500s across `.glb`, 16 panoramas, and 20 stills)
- **Interactive UI Verification**:
  - All 16 spot buttons load valid $2560 \times 1440$ images.
  - Minimap minimize/expand functions properly (`minimap_minimized: True`).
  - Sidebar hide and floating restore button work cleanly (`sidebar_collapsed: True`, `sidebar_restored: True`).
  - Stills gallery loads all 20 images (`{'total': 20, 'broken': []}`).
  - Hotspot toggle shows and hides doorway buttons cleanly.

---

## 8. Summary of File Modifications

| File Path | Description of Changes |
|:---|:---|
| [`viewer/index.html`](file:///d:/vibgyor-task/viewer/index.html) | Main web viewer. Implemented 3 tabs (3D Building, 360 Tour, Stills Gallery), 2.5K Photoreal Spot engine, pan/zoom controls, non-obtrusive bottom dock hotspots, collapsible minimap and sidebar, clean view mode, and cache-busted asset paths. |
| [`pipeline/verify_all.py`](file:///d:/vibgyor-task/pipeline/verify_all.py) | Verification harness. Verifies all 20 stills and 16 panoramas with signed `np.int16` seam continuity checks and DOM validation. |
| [`config.json`](file:///d:/vibgyor-task/config.json) | Central parameters for heights (from Section A-A), DXF bounding box regions, CAD layer maps, and PBR materials. |
| [`pipeline/extract.py`](file:///d:/vibgyor-task/pipeline/extract.py) | Automated DXF geometry parser, block expander, and wall-snapping room extractor. |
| [`pipeline/furnish.py`](file:///d:/vibgyor-task/pipeline/furnish.py) | Geometry-driven furniture placement engine for Type A, Type B, and shared amenities. |
| [`pipeline/build_model.py`](file:///d:/vibgyor-task/pipeline/build_model.py) | Procedural Blender 3D building builder with PBR materials and cutaway support. |
| [`pipeline/render.py`](file:///d:/vibgyor-task/pipeline/render.py) | Headless Blender Cycles rendering pipeline for stills and panoramas. |
| [`pipeline/export.py`](file:///d:/vibgyor-task/pipeline/export.py) | Web-optimized glTF/GLB exporter (< 40 MB). |
| [`NOTES.md`](file:///d:/vibgyor-task/NOTES.md) | Official documentation answering all technical prompts required by the brief. |
| [`README.md`](file:///d:/vibgyor-task/README.md) | Project overview, setup instructions, and CLI build commands. |
| `viewer/panoramas/` & `outputs/panoramas/` | 16 equirectangular 360° panoramas ($6144 \times 3072\text{ px}$). |
| `viewer/interiors/`, `amenities/`, `exteriors/` | 20 photorealistic architectural spot renders ($2560 \times 1440\text{ px}$). |

---

## 9. How to Run the Project

### Start Local Web Viewer
To launch the interactive web application:
```bash
python -m http.server 8090 --directory viewer
```
Then navigate to `http://localhost:8090/` in any modern web browser.

### Run Extraction Unit Tests
```bash
python -m pytest -v
```

### Run Full Verification Suite
```bash
python pipeline/verify_all.py
```

---

## 10. Phase 6: Layout-Accurate Photoreal Pipeline (30 Oct 2026)

### 10.1 Client Feedback
> *"Rendered images are good but we need 360 view on those renders. Also please confirm if those renders are based on layout of 3d model only."*

Review found that the 360° sphere still showed the plain Cycles panoramas while the spot view showed prompt-only AI images, so the two modes showed different rooms and neither the stills nor any 360° was photoreal *and* model-based. Turning the existing AI stills into 360s was ruled out: they cover ~90° each, and filling the rest would either smear (stretching) or invent walls and openings (outpainting).

### 10.2 New Pipeline
| Step | Where | File | Output |
|:---|:---|:---|:---|
| Base renders: beauty + exact depth (cm) for 16 spots (3072 × 1536 equirect) and 20 still cameras (1600 × 900) | Local CPU, ~2.5 h | `pipeline/render_ai_bases.py` | `outputs/ai_bases/` |
| Package with prompts, seeds, style refs | Local | `pipeline/package_ai_inputs.py` | `outputs/ai_handoff/vibgyor_ai_inputs.zip` (~40 MB) |
| AI finishing: RealVisXL V5 img2img + xinsir depth & canny ControlNets (+ optional IP-Adapter style ref 0.35); equirect wrap padding, seam regeneration, cube-face ceiling/floor, tiled detail pass to 6144 × 3072 | Free Kaggle/Colab T4, ~2–3 h | `pipeline/finish_ai.py`, `notebooks/vibgyor_ai_finish.ipynb` | `vibgyor_ai_results.zip` |
| Import: base/depth hash check, layout-match score, copy to `outputs/` + `viewer/` | Local | `pipeline/import_ai_results.py` | `outputs/ai_manifest.json` |
| Verify: sizes, seams, manifest membership, output hashes, layout match ≥ 0.30 | Local | `pipeline/verify_all.py` | pass/fail |

- **Decision (30 Oct)**: the 20 existing AI stills are kept as *concept* images (labelled "AI concept still · not to exact layout" in the viewer); only the 16 360° spots go through the model-based pipeline (`render_ai_bases --panos-only`, `package_ai_inputs --panos-only`). `verify_all.py` enforces model provenance for the 360s only.
- Preview runs on Kaggle T4 (~16 min per spot): preview 1 showed ring artifacts (8-bit depth banding copied by the depth ControlNet) and an opaque balcony door; preview 2 (dithered depth, depth weight 0.5, control released at 80%, strength 0.7) fixed the rings. The door was traced to glazing being solid in the depth pass; `Mat_Window_Glass` / `Mat_Railing_Glass` are now see-through in depth.
- New still cameras added to `render.py` for `amenity_6_terrace_gym`, `type_a_5_third_bedroom`, `type_b_5_third_bedroom`.
- The images the client liked are kept in `outputs/ai_style_refs/` and used only as a style reference (interiors and amenities; exteriors take none because those images show a different building).
- Viewer: tour opens in the 360° view; *Still Photo* shows the room's still; labels say "rendered from the 3D model"; `ASSET_VERSION` cache-busting.
- Prompt-only scripts moved to `legacy/prompt_only/` (not used).
- Layout-match metric calibration on the Type A drawing room: raw model render 0.59, same view rotated 90° −0.01, the prompt-only AI still −0.10.

- **Delivered (30 Oct)**: all 16 360° spots (Kaggle T4, layout match 0.57-0.93) and all 20 stills (MyArchitectAI renders of the model, layout match 0.38-0.91) imported with provenance in `outputs/ai_manifest.json`; `verify_all.py` and 20 tests pass. Known gaps: 10 stills (files 10-19 in `outputs/myarchitectai/results/`) carry the MyArchitectAI watermark (free-plan test images); stills are 1344x756 upscaled to 2560x1440; sign text in exterior stills is misspelled ("VISCTOR"); model's blob trees and boxy cars carry into renders; 360s are softer and more beige than the stills; weakest layout matches are type_b_3_master_bedroom (0.38), type_a_5_third_bedroom (0.50), type_a_3_master_bedroom (0.52).
