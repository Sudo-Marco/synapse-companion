# Piu pixel-art assets

The transparent sprite sheets are built from the approved contact sheets in
`docs/mockups/piu/vistas_etapa1/`. The source `inventario_frames.json` describes
each animation and its routes from movement/emotion keys to an animation or
frame. The generated `animations.json` adds packed rectangles for every PNG.

Each frame records duration, loop metadata, native size, pivot, hitbox, and a
label. The renderer uses route data for emotion poses, movement cycles, and
time-based loops; a new pose can be added by adding its sprite frames and a
route in the source JSON. The renderer does not need a new emotion branch for
that mapping. Movement *semantics* (for example adding a new controller action)
still belong in the motion controller.

To rebuild the atlases and metadata after editing the source sheets/manifest:

```powershell
.\.venv\Scripts\python.exe tools\build_piu_assets.py
```

The builder removes the documented navy contact-sheet background; it does not
redraw the character. `lod.png` contains the approved native drawings at 32,
24, and 16 pixels. Keep the shared foot pivot `(16, 40)` to avoid visual jumps.
PNG sheets are ordinary RGBA images and can be edited in a pixel-art editor.
When reordering frames, update rectangles and labels by rebuilding the atlas;
review the generated preview images and run the asset/UI tests.
