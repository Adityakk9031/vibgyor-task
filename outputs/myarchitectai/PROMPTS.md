# MyArchitectAI still renders

For each row: **Render** → upload the file from `inputs/` → choose the mode → paste the prompt →
keep creativity / variation **low** so walls, doors and furniture stay where they are → generate →
download at the highest resolution → save it in `results/` with the **same file name** (any of .png / .jpg / .webp).

Then run `python -m pipeline.import_external_stills` to layout-check and import them.

| # | Upload file | Mode | Prompt |
|:-:|:---|:---|:---|
| 1 | `01_amenity_3_entrance_lobby.jpg` | Interior | luxury residential entrance lobby, travertine marble walls and floor, fluted walnut panels, bronze elevator doors, ring chandelier, lounge seating |
| 2 | `02_type_a_1_drawing_room.jpg` | Interior | living room, sofa, coffee table, fluted wood TV wall, large clear glass sliding door to a sunny balcony, light oak herringbone floor, boucle upholstery, sheer curtains |
| 3 | `03_type_a_2_kitchen_dining.jpg` | Interior | open kitchen and dining room, quartz countertops, wooden dining table and chairs, pendant lights, light oak floor |
| 4 | `04_type_a_3_master_bedroom.jpg` | Interior | master bedroom, upholstered king bed with linen bedding, fluted wood headboard wall, bedside tables and lamps, wardrobe, light oak floor, sheer curtains |
| 5 | `05_type_b_1_drawing_room.jpg` | Interior | living room, sofa, coffee table, fluted wood TV wall, large clear glass sliding door to a sunny balcony, light oak herringbone floor, boucle upholstery, sheer curtains |
| 6 | `06_type_b_2_kitchen_dining.jpg` | Interior | open kitchen and dining room, quartz countertops, wooden dining table and chairs, pendant lights, light oak floor |
| 7 | `07_type_b_3_master_bedroom.jpg` | Interior | master bedroom, upholstered king bed with linen bedding, fluted wood headboard wall, bedside tables and lamps, wardrobe, light oak floor, sheer curtains |
| 8 | `08_type_a_4_second_bedroom.jpg` | Interior | bedroom, upholstered bed with linen bedding, wood panel headboard wall, bedside tables, wardrobe, light oak floor, sheer curtains |
| 9 | `09_type_b_4_second_bedroom.jpg` | Interior | bedroom, upholstered bed with linen bedding, wood panel headboard wall, bedside tables, wardrobe, light oak floor, sheer curtains |
| 10 | `10_type_a_5_third_bedroom.jpg` | Interior | bedroom, upholstered bed with linen bedding, wood panel headboard wall, bedside tables, wardrobe, light oak floor, sheer curtains |
| 11 | `11_type_b_5_third_bedroom.jpg` | Interior | bedroom, upholstered bed with linen bedding, wood panel headboard wall, bedside tables, wardrobe, light oak floor, sheer curtains |
| 12 | `12_amenity_5_terrace_amenities.jpg` | Exterior | rooftop terrace of a residential tower, slatted timber pergola lounge, outdoor sofas, artificial turf play area, planters, blue sky |
| 13 | `13_amenity_6_terrace_gym.jpg` | Interior | rooftop glass fitness studio, gym equipment, rubber floor, floor-to-ceiling glass walls, skyline view, daylight |
| 14 | `14_amenity_1_basement_parking.jpg` | Interior | underground residential car park, parked cars and scooters, grey epoxy floor, yellow parking bay lines, concrete columns with yellow and black safety bands, linear LED ceiling lights |
| 15 | `15_amenity_2_stilt_parking.jpg` | Interior | covered stilt parking under a residential tower, parked cars, concrete columns, paved driveway, parking bay markings, landscaped garden edge, daylight |
| 16 | `16_amenity_4_landscape_drive.jpg` | Exterior | landscaped garden deck beside a residential tower, timber benches, planter beds with tropical shrubs, paved driveway, bollard lights, daylight |
| 17 | `17_shot_1_eye_level_day.jpg` | Exterior | modern seven storey residential apartment tower, street view, glass balconies, white and concrete facade, trees, clear daylight |
| 18 | `18_shot_4_entrance_closeup.jpg` | Exterior | entrance gate of a modern residential tower, canopy with timber soffit, stone compound wall, security cabin, granite driveway, tropical planting, bright daylight |
| 19 | `19_shot_2_front_corner_dusk.jpg` | Exterior | modern seven storey residential apartment tower at dusk, warm interior lights glowing, glass balconies, deep blue sky |
| 20 | `20_shot_3_aerial_day.jpg` | Exterior | aerial view of a modern residential tower and its site, rooftop terrace, landscaped grounds, road, daylight |
