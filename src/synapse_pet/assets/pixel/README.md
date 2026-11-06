# Piu pixel-art assets

The transparent sprite sheets include the approved 0.2 sheets from
`docs/mockups/piu/vistas_etapa1/` and the detailed 0.3 source frames in
`docs/mockups/piu/v03_stage1/sprites/`. The 0.3 sources are individual PNGs
with transparent backgrounds, drawn natively at 48, 32, or 20 pixels; they are
not scaled copies. `animations.json` stores each atlas rectangle, native size,
view, duration, loop flag, pivot, hitbox, and route.

Each frame records duration, loop metadata, native size, pivot, hitbox, and a
label. The renderer uses route data for emotion poses, movement cycles, and
time-based loops; a new pose can be added by adding its sprite frames and a
route in the source JSON. The renderer does not need a new emotion branch for
that mapping. Movement *semantics* (for example adding a new controller action)
still belong in the motion controller.

Routes are data-driven. Idle/profile, front, and back views plus walking,
running, away/return, thinking, tired, resting, listening, caught, fall, peek,
and three dance cycles use the 0.3 atlas. Older poses remain packaged as
fallbacks. To edit artwork, change the corresponding PNG under
`docs/mockups/piu/v03_stage1/sprites/` (or regenerate the original sheets),
then rebuild the atlases:

```powershell
.\.venv\Scripts\python.exe tools\build_piu_assets.py
```

The builder removes the documented navy contact-sheet background from the 0.2
review sheets and packs 0.3 transparent sources without resampling. The legacy
`lod.png` (32, 24, 16 pixels) remains for compatibility; the active 0.3 routes
use 48, 32, and 20 pixel frames. Keep pivots aligned with the feet (the 48 px
source uses `(24, 44)`) to prevent jumps between LODs. When reordering frames,
rebuild the atlases so rectangles and labels stay synchronized, review the
contact sheets, and run the asset and renderer tests.
