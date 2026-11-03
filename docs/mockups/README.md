# Synapse Pet ASCII eye — design review

These six static sheets are the design comparison for the avatar. Each sheet shows
the same complete nocturnal ASCII scene twice so the eye designs can be compared:

- **A — rounded:** larger, rounder iris and a softer eye silhouette.
- **B — nocturne:** slightly elongated eye and stronger, more noticeable lashes.

The revised direction uses a soft almond outline, a blue-green shell instead
of a stark white eyeball, smaller dark pupils, fine luminous iris fibres, warm
highlights, and gentle blush/heart accents. This keeps the terminal-art mood
of the reference while making the companion feel more welcoming.

The sheets cover neutral, happy, sad, sleeping, scared, and petting expressions.
They remain static references. The live app now uses the direct ASCII renderer
with smooth blinking, breathing, cursor gaze, a local-time sky cycle, drifting
clouds, twinkling stars, and animated water. Design A is the default; set
`visual.eye_design: B` in `configs/default.yaml` to preview the elongated eye.

## Regenerate

From the project root, run:

```powershell
.\.venv\Scripts\python.exe tools\generate_ascii_eye_mockups.py
```

The generator uses the project's existing Pillow and NumPy dependencies and
writes the six PNGs into this folder. The preview canvas uses a 160 × 90
character grid with 2× supersampling before converting the artwork into glyphs.
The palette can be changed with `--palette moonlit`; the two available palettes
are `nocturne` and `moonlit`.

The live renderer uses the existing PySide6 window and does not alter the SNN
or its persistence format.
