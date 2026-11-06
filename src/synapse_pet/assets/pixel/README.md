# Piu pixel-art assets

These transparent sprite sheets are packed from the approved contact sheets in
`docs/mockups/piu/vistas_etapa1/`. `animations.json` is the editable sidecar:
each frame stores its rectangle, native drawing size, duration, loop flag, pivot,
hitbox and label. The walk cycle includes a tunable distance-per-cycle contract.

To rebuild the sheets after editing the source mockups, run
`python tools/build_piu_assets.py` from the repository root. The tool removes
the documented navy sheet background and contact-cell top border; it does not
redraw or rescale the character. `lod.png` contains sprites drawn natively at
32, 24 and 16 pixels. Keep the common pivot `(16, 40)` when adding frames.

The PNG files are ordinary RGBA sheets and can be edited in a pixel-art editor.
Update the sidecar rectangles and metadata whenever frame ordering or sheet
packing changes. The renderer reads the sidecar at runtime, so a data-only
animation addition does not require a new animation branch in the renderer.
