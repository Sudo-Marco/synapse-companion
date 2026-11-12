from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "synapse_pet" / "assets" / "pixel"
PET_ASSETS = ROOT / "src" / "synapse_pet" / "assets" / "pet"


def test_approved_piu_frames_are_packed_with_native_lod_metadata():
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert sum(len(animation["frames"])
               for animation in manifest["animations"].values()) == 114
    legacy_count = sum(len(manifest["animations"][name]["frames"])
                       for name in ("frente", "costas", "virada_vistas", "pulo",
                                    "corrida_lateral", "corrida_para_fundo",
                                    "volta_para_camera"))
    assert legacy_count == 51
    run = manifest["animations"]["corrida_lateral"]
    assert all(frame["pivot"] == [16, 40] for frame in run["frames"])
    assert all("hitbox" in frame and "duration_ms" in frame for frame in run["frames"])
    assert run["distance_per_cycle_px"] == 24
    assert run["distance_is_tunable_estimate"] is True
    assert manifest["lod"]["sizes"] == [32, 24, 16]
    assert manifest["native_lod_sizes"] == [48, 32, 20]
    assert [frame["native_size"] for frame in
            manifest["animations"]["idle_perfil"]["frames"]] == [48, 32, 20]
    assert all(frame["pivot"] == [frame["native_size"] // 2,
                                   round(44 * frame["native_size"] / 48)]
               for group in ("idle_perfil", "corrida_perfil", "idle_frente",
                             "idle_costas")
               for frame in manifest["animations"][group]["frames"])
    assert {route["animation"] for route in
            manifest["routes"]["views"].values()} == {
                "idle_perfil", "idle_frente", "idle_costas"}
    assert all(entry["native_draw"]
               for rows in manifest["lod"]["entries"].values() for entry in rows)
    for family in ("actions", "emotions", "views"):
        for route in manifest["routes"][family].values():
            animation = manifest["animations"][route["animation"]]
            if "frame" in route:
                assert route["frame"] in {frame["label_key"]
                                           for frame in animation["frames"]}


def test_contact_sheet_border_is_not_baked_into_character_pixels():
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    legacy = {"frente", "virada_vistas", "pulo", "corrida_lateral",
              "corrida_para_fundo", "volta_para_camera"}
    for name in legacy:
        animation = manifest["animations"][name]
        sheet = np.asarray(Image.open(ASSETS / animation["sheet"]).convert("RGBA"))
        for frame in animation["frames"]:
            x, y, width, _height = frame["rect"]
            assert not sheet[y, x:x + width, 3].any()


def test_v03_atlases_keep_native_pixels_and_transparent_padding():
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    for group in ("idle_perfil", "idle_frente", "idle_costas",
                  "corrida_perfil", "corrida_frente", "corrida_costas"):
        animation = manifest["animations"][group]
        sheet = Image.open(ASSETS / animation["sheet"]).convert("RGBA")
        for frame in animation["frames"]:
            x, y, width, height = frame["rect"]
            assert (width, height) == (frame["native_size"],) * 2
            assert sheet.crop((x + width, y, x + 48, y + height)).getchannel("A").getbbox() is None
    for name in ("pensando", "cansado_perfil", "cansado_frente", "descansando",
                 "ouvindo", "pego_no_alto", "queda_pancada", "espiando",
                 "danca_balanco", "danca_pulinho", "danca_cabecada"):
        assert manifest["animations"][name]["frames"]


def test_pixel_ui_frame_asset_is_a_small_transparent_nine_slice():
    frame = Image.open(ASSETS / "ui_frame.png").convert("RGBA")
    assert frame.size == (9, 9)
    assert frame.getpixel((4, 4))[3] == 0
    assert frame.getpixel((0, 0))[3] > 0


def test_new_desktop_sprite_sheet_matches_its_row_atlas_and_mapping():
    atlas = json.loads((PET_ASSETS / "pet_atlas.json").read_text(encoding="utf-8"))
    mapping = json.loads((PET_ASSETS / "sprite_mapping.json").read_text(
        encoding="utf-8"))
    sheet = Image.open(PET_ASSETS / atlas["sheet"]).convert("RGBA")
    assert sheet.size == (384, 1296)
    assert (atlas["frame_width"], atlas["frame_height"]) == (48, 48)
    assert (atlas["columns"], atlas["rows"]) == (8, 27)
    assert (atlas["anchor_x"], atlas["anchor_y"]) == (24, 43)
    assert len(atlas["animations"]) == 27
    referenced = set()

    def collect_names(value):
        if isinstance(value, dict):
            for nested in value.values():
                collect_names(nested)
        elif isinstance(value, str):
            referenced.add(value)

    for section in ("emotions", "actions", "views", "drag", "transient"):
        collect_names(mapping[section])
    collect_names(mapping["non_loop_fallback"])
    assert referenced <= set(atlas["animations"])
    assert (PET_ASSETS / "README.md").is_file()
