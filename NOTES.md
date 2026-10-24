# Engineering Notes (`NOTES.md`)

## 1. How Plans and Walls Were Identified in the Drawing
- **Units & Coordinate Mapping**: `$INSUNITS` in `SUBMISSION - 04.dxf` is unset (`0`), so we verified drawing scale against `DIMENSION` entities and area calculation tables: `1 DXF unit = 1.0 metre` (building footprint is $13.12\text{ m} \times 38.733\text{ m}$, net built-up area $398.59\text{ m}^2$).
- **Expanding Block References (`INSERT`)**: Several sub-drawings (such as the RERA carpet plan `A$C27EF3DA3`, the ground floor block `A$C71DB458C`, tree symbols `TR1`, and elevation/section blocks `FRONT_TYP._ELV._13-05-22` & `typical floor_12-05-2022`) are stored inside blocks—some authored in millimetres around `(4.68e6, -1.95e6)` and inserted at `(-4350, 2032)` with `scale = 0.001`. Expanding all `INSERT` references recursively via `ezdxf`'s `virtual_entities()` maps every entity accurately into world sheet space `x = [58, 397], y = [29, 110]`.
- **Plan Alignment**: Each plan region (`LAYOUT PLAN`, `GROUND FLOOR PLAN`, `1ST TO 7TH FLOOR PLAN`, `OPEN TERRACE PLAN`) contains a closed 9-vertex `LWPOLYLINE` on `A_BUILT UP` (or `A_PARAPET` on the terrace). Using the SW corner of that footprint bbox as `(0, 0)` aligns all plans, columns, walls, and site elements into a single building-relative metre coordinate frame.
- **Wall & Projection Polygonization**: Walls on `g-wall` and `A_Wall` are drawn as parallel double lines ($0.23\text{ m}$ / $0.20\text{ m}$ exterior and $0.10\text{ m}$ interior partitions) interrupted by window/sliding-door rectangles (`A_WINDOW`, `g-dw`), structural columns (`COLUMN_BSE`, `g-r.c.c`), and door lines (`A_DOOR`). Unioning the boundary segments with Shapely (`unary_union` + `polygonize`), filtering by thickness estimate $2A/P < 0.34\text{ m}$ (which separates thin wall loops from large room interiors), and subtracting window/column cutouts yields clean, watertight 2D wall polygons. Similarly, polygonizing `A_PROJ.` lines against the `A_BUILT UP` exterior ring reconstructs all 28 cantilevered $0.60\text{ m}$ architectural projections.

## 2. What Is in `config.json` and Why
Per Rule 02, no geometry coordinates are hand-typed in `config.json`. It stores only what a 2D floor plan cannot self-describe:
- **Vertical Heights from Section A–A**: Stilt height ($3.30\text{ m}$), typical floor-to-floor height ($3.05\text{ m}$), 7th-to-terrace height ($3.10\text{ m}$), slab thickness ($0.15\text{ m}$), parapet/railing height ($1.15\text{ m}$), stair cabin ($3.00\text{ m}$), O.H.W.T. ($2.40\text{ m}$), and sill/lintel heights measured from the elevation (`a-Ele2-HM` / `a-Ele3-HM`).
- **DXF Sheet Region Bboxes & Origins**: Bounding boxes separating each plan on the multi-sheet CAD layout and their reference origin points.
- **CAD Layer Mapping & PBR Material Parameters**: Maps architect layer names (`g-wall`, `COLUMN_BSE`, `g-dw`, `A_PROJ.`, `F.P.LINE`, `A_TREE`, etc.) and defines PBR colors/roughness matching `brochure/exterior.jpg`.

## 3. What Breaks (Edge Cases & Limitations)
- **Unclosed CAD Gaps**: If an architect leaves a $>5\text{ mm}$ gap at a wall-to-window T-junction or omits a door closure line on `A_DOOR`, `shapely.ops.polygonize` will merge the wall interior with the adjacent room polygon (causing it to be filtered out by the $2A/P$ thickness check).
- **Non-Uniform Block Scaling**: The RERA plan block `A$C27EF3DA3` is inserted at `0.5x` scale on the sheet to fit beside the typical plan; reading its unscaled block definition directly (as we do) avoids half-scale distortion, but requires knowing the block name.
- **Developer Render vs. Municipal Submission Differences**: Municipal drawings (`SUBMISSION - 04.dxf`) show FSI/RERA regulatory lines and omit decorative louver fin counts or furniture models; we derive the planter zones from the DXF elevation (`a-Ele2-HM`) and generate the vertical louver clusters and Type A drawing room furniture procedurally within the extracted room/balcony bounds.

## 4. Hours Spent
- **Total**: ~6.5 hours (DXF reverse-engineering & coordinate verification: 1.5h; 2D polygon reconstruction & unit tests: 1.5h; 3D `bpy` model + Type A interior + facade detailing: 2.0h; Cycles rendering & Three.js interactive web viewer: 1.5h).

## 5. What I Would Do Next
- **Automated Text-Driven Region Discovery**: Replace the region bounding boxes in `config.json` with a spatial clustering pass anchored on title MTEXT entities (`"1ST TO 7TH FLOOR PLAN"`, `"SECTION - 'A-A'"`) and `A_BUILT UP` polylines so new DWG sheets require zero region config.
- **Snap/Buffer Tolerance for Dirty CAD Lines**: Add an endpoint-snapping pass (`shapely.snap` at $10\text{ mm}$ tolerance) before `polygonize` to handle unclosed CAD wall corners automatically across arbitrary architect drawings.
- **Full Interior Generation for All Rooms**: Extend the procedural interior furnishing from the Floor 1 Type A Drawing/Dining/Kitchen area to all bedrooms and bathrooms using DXF room label text (`BED ROOM 4.56 x 3.20`, `TOILET`) and door swing arcs to orient beds and wardrobes automatically.
