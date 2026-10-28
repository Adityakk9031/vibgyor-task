# Vibgyor — Automated DXF to 3D Model, Amenities, Interiors & 360° Virtual Tour (Level 1 + Level 2)

An end-to-end automated architectural pipeline that reads the municipal submission drawing (`SUBMISSION - 04.dxf` / `.dwg`) for **Vibgyor** (a 7-storey residential tower in Prahlad Nagar, Ahmedabad with basement + stilt parking, $2 \times \text{4BHK}$ flats per floor, entrance lobby, landscaped drive, and rooftop terrace amenities) and generates everything 100% by code:

1. **Clean 2D & Room Geometry (`outputs/extracted_geometry.json`)** — Reconstructed closed polygons for Basement parking (slab, columns, curved ramp, 2 car bays, 20 two-wheeler bays), Ground Floor Stilt Parking (5 car bays, 15 two-wheeler bays) & Entrance Lobby, 1st–7th Typical Floor slabs, 23 structural columns, walls, $0.60\text{ m}$ projections, windows, sliding doors, wall-snapped room bounds for all rooms in **Type A ($160.05\text{ m}^2$)** and **Type B ($143.18\text{ m}^2$)** flats, Terrace Amenity Zones, and Site Layout (plot boundary, $18\text{ m}$ road, 25 trees).
2. **Generated 3D Model (`outputs/vibgyor.blend`)** — Built procedurally in headless Blender (`bpy` + `trimesh` + `shapely`) with geometry-driven furniture placement (`pipeline/furnish.py`) across both Type A and Type B flats plus all 5 amenity spaces.
3. **17 Photorealistic Still Renders (`2560 × 1440 px`, Blender Cycles)**:
   - **5 Amenity Stills (`outputs/amenities/`)**:
     - `amenity_1_basement_parking.png` — Basement parking bays, two-wheelers, sloped ramp, safety columns & ceiling LEDs
     - `amenity_2_stilt_parking.png` — Ground-level stilt parking bays, cars, columns & soffit lighting
     - `amenity_3_entrance_lobby.png` — Ground-floor entrance lobby with bronze lifts, travertine marble, fluted wood, chandelier & seating
     - `amenity_4_landscape_drive.png` — West landscaped garden deck, timber benches, planter beds, bollards & entrance drive
     - `amenity_5_terrace_amenities.png` — Terrace slatted pergola seating lounge, kids' play area & glass fitness gym
   - **8 Interior Stills (`outputs/interiors/`, 4 per flat type)**:
     - **Type A (Front 4BHK)**: `type_a_1_drawing_room.png`, `type_a_2_kitchen_dining.png`, `type_a_3_master_bedroom.png`, `type_a_4_second_bedroom.png`
     - **Type B (Rear 4BHK)**: `type_b_1_drawing_room.png`, `type_b_2_kitchen_dining.png`, `type_b_3_master_bedroom.png`, `type_b_4_second_bedroom.png`
   - **4 Exterior Stills (`outputs/`)**:
     - `shot_1_eye_level_day.png`, `shot_2_front_corner_dusk.png`, `shot_3_aerial_day.png`, `shot_4_entrance_closeup.png`
4. **16 Equirectangular $360^\circ$ Panoramas (`6144 × 3072 px`, `outputs/panoramas/`)**:
   - **Building & Amenities (6)**: Entrance Gate, Entrance Lobby, Basement Parking, Garden & Stilt, Terrace Pergola & Kids' Play, Terrace Fitness Gym.
   - **Type A Interior (5)**: Drawing Room, Kitchen & Dining, Master Bedroom (SE), Second Bedroom (Mid-East), Third Bedroom (SW) & Balcony View.
   - **Type B Interior (5)**: Drawing Room, Kitchen & Dining, Master Bedroom (NE), Second Bedroom (NW), Third Bedroom (Mid-West).
5. **Interactive Web $360^\circ$ Tour, 3D Model & Stills Viewer (`viewer/index.html` + `outputs/vibgyor.glb`)**:
   - **`360° Virtual Tour (16 Views)`**: Drag to look around any of the 16 $6144 \times 3072$ equirectangular panoramas, click **3D Hotspot Portals** inside the scene to walk from room to room, or jump via the categorized list and **interactive 2D Floor/Site Minimap** with live camera FOV radar cone.
   - **`3D Building Model (.glb)`**: Orbit/pan/zoom the full building (`7.9 MB <= 40 MB`), toggle Day/Dusk lighting, click any floor (including Basement B1) or flat (`Type A` / `Type B`), and slice upper floors.
   - **`Stills Gallery (17 Renders)`**: Browse and inspect all 5 Amenity, 8 Interior, and 4 Exterior renders at full $2560 \times 1440$ resolution.

---

## Quick Start

### 1. Prerequisites & Setup

Requires **Python 3.11 – 3.13** (on macOS, Linux, or Windows). Headless Blender (`bpy`) is installed via `pip`:

```bash
pip install -r requirements.txt
```

### 2. Run the Full Pipeline (One Command)

Rebuilds all outputs (`outputs/extracted_geometry.json`, `outputs/vibgyor.blend`, `outputs/vibgyor.glb`, all 17 still renders, and all 16 $360^\circ$ panoramas) directly from `SUBMISSION - 04.dxf`:

```bash
python build.py
# or on macOS / Linux:
make all
```

### 3. Run Individual Pipeline Stages

```bash
python build.py extract                 # Stage 1: DXF -> outputs/extracted_geometry.json
python build.py build                   # Stage 2: 2D JSON -> outputs/vibgyor.blend (with amenities & interiors)
python build.py render                  # Stage 3: Render all 17 stills (2560x1440) + 16 360° panoramas (6144x3072)
python build.py render --only amenities # Render only the 5 amenity stills
python build.py render --only interiors # Render only the 8 interior stills
python build.py render --only panoramas # Render only the 16 360° panoramas
python build.py export                  # Stage 4: Export web-ready outputs/vibgyor.glb (<= 40 MB)
```

### 4. Run Extraction Unit Tests

```bash
python -m pytest -v
```

### 5. Launch the Interactive Web $360^\circ$ & 3D Viewer

```bash
python -m http.server 8080 --directory viewer
# Then open http://localhost:8080 in your browser
```
