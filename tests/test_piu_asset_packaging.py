from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "synapse_pet" / "assets" / "pixel"


def test_approved_piu_frames_are_packed_with_native_lod_metadata():
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    assert sum(len(animation["frames"])
               for animation in manifest["animations"].values()) == 51
    run = manifest["animations"]["corrida_lateral"]
    assert all(frame["pivot"] == [16, 40] for frame in run["frames"])
    assert all("hitbox" in frame and "duration_ms" in frame for frame in run["frames"])
    assert run["distance_per_cycle_px"] == 24
    assert run["distance_is_tunable_estimate"] is True
    assert manifest["lod"]["sizes"] == [32, 24, 16]
    assert all(entry["native_draw"]
               for rows in manifest["lod"]["entries"].values() for entry in rows)


def test_contact_sheet_border_is_not_baked_into_character_pixels():
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    for name, animation in manifest["animations"].items():
        sheet = np.asarray(Image.open(ASSETS / animation["sheet"]).convert("RGBA"))
        for frame in animation["frames"]:
            x, y, width, _height = frame["rect"]
            assert not sheet[y, x:x + width, 3].any()
