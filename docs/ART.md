# Piu pixel-art guide

Piu's approved mockups in `docs/mockups/piu/vistas_etapa1/` are the visual
source of truth. The packaged sheets use the same canary silhouette, limited
palette, pixel outline, crest, wing, beak, cheek, and light direction. Do not
redraw the character when adding a view.

## Files and build

| File | Purpose |
| --- | --- |
| `docs/mockups/piu/vistas_etapa1/*.png` | Approved editable contact sheets and source art. |
| `docs/mockups/piu/vistas_etapa1/inventario_frames.json` | Source animation frames, labels, pivots, hitboxes, durations, and visual routes. |
| `src/synapse_pet/assets/pixel/*.png` | Runtime RGBA sprite atlases, including native-size depth sprites. |
| `src/synapse_pet/assets/pixel/animations.json` | Generated packed rectangles plus the animation and route metadata. |
| `src/synapse_pet/assets/pixel/ui_frame.png` | Nine-slice frame for pixel-theme cards and dialogs. |
| `src/synapse_pet/assets/fonts/silkscreen/` | Bundled Silkscreen font and its OFL license. |

After editing source sprites or their inventory, rebuild from the repository
root:

```powershell
.\.venv\Scripts\python.exe tools\build_piu_assets.py
.\.venv\Scripts\python.exe tools\capture_pixel_previews.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_piu_asset_packaging.py tests\test_pixel_renderer.py
```

The builder extracts transparent sprites from the approved contact sheets; it
does not redraw or rescale the bird. Keep the common foot pivot at `(16, 40)`.
Animation metadata includes duration, loop, hitbox, label, native size, and
distance-per-cycle where relevant. The active 0.3 depth routes use individually
drawn 48, 32, and 20 pixel sprites. The older `lod.png` (32, 24, and 16 pixel
drawings) remains packaged for compatibility. The renderer chooses a native
view with hysteresis and enlarges by nearest-neighbor integer steps.

## Add a pose or animation route

1. Draw the new frames in the matching source contact sheet, preserving the
   approved palette and pivot.
2. Add the frames and metadata to `inventario_frames.json`.
3. Add an entry under `routes.emotions`, `routes.actions`, or `routes.views`.
   A fixed pose uses `{"animation": "frente", "frame": "feliz"}`; a timed
   loop uses `{"animation": "nome", "mode": "time_loop"}`. Stride and
   progress routes are available for existing movement actions.
4. Rebuild the atlas, inspect regenerated screenshots, and run the asset and UI
   tests.

The renderer resolves pose routes from the JSON, so adding an emotion-to-frame
mapping does not require an emotion-specific code branch. A new movement action
with new behavior still needs to be defined in `ui/pet_motion.py`.

## Scene and interface

The panel and full-screen view use a pixel-art scene with local-time day,
dusk, and night palettes. The floating mode shows only Piu. Panel cards use a
nine-slice border; progress bars are segmented; post-its use square corners and
the bundled pixel font. Existing eye styles remain selectable in
`pet.render_style`.

The v0.3 scene interpolates five local periods (dawn, morning, afternoon, dusk,
and night) and adds layered hills, a house, trees, a fence, a stream, flowers,
and time-dependent sky details. Manual latitude/longitude values can refine
sunrise and sunset locally; no location lookup or weather service is used.
Optional rain, fog, or wind effects are decorative. Audio listening and dance
routes are selected from the same animation JSON; no raw sound is part of an
art asset.

## Current visual limits

The pixel sheets are crisp at integer scale. Their individual pose variety is
limited to the frames in the approved source pack; the moving scene and several
secondary effects are drawn by QPainter rather than authored as separate
sprites. Offline captures do not validate transparency, click-through shape,
color management, or mixed-DPI layout on a physical Windows desktop.
