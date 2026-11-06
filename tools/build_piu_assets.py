from __future__ import annotations

"""Package the approved Piu contact sheets as editable transparent sprite sheets."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "mockups" / "piu" / "vistas_etapa1"
DESTINATION = ROOT / "src" / "synapse_pet" / "assets" / "pixel"
KEY = (36, 54, 94)  # The mockup's documented night-blue sheet background.
FRAME_SIZE = (32, 44)
LOD_ROWS = (
    ("profile", "idle"), ("profile", "run"),
    ("front", "idle"), ("front", "run"),
    ("back", "idle"), ("back", "run"),
)
LOD_SIZES = (32, 24, 16)
ANIMATION_ROUTES = {
    "actions": {
        "away": {"animation": "corrida_para_fundo", "mode": "stride",
                 "match_lod": True},
        "return": {"animation": "volta_para_camera", "mode": "stride",
                   "match_lod": True},
        "walk": {"animation": "corrida_lateral", "mode": "stride"},
        "run": {"animation": "corrida_lateral", "mode": "stride"},
        "jump": {"animation": "pulo", "mode": "progress"},
        "fly": {"animation": "pulo", "mode": "progress"},
    },
    "emotions": {
        "alegre": {"animation": "frente", "frame": "feliz"},
        "assustado": {"animation": "frente", "frame": "susto"},
        "cantando": {"animation": "frente", "frame": "cantar"},
        "curioso": {"animation": "frente", "frame": "p/cima"},
        "curioso_esquerda": {"animation": "virada_vistas", "frame": "p_3/4_a"},
        "curioso_direita": {"animation": "virada_vistas", "frame": "p_3/4_b"},
        "dormindo": {"animation": "frente", "frame": "dormir"},
        "piscar": {"animation": "frente", "frame": "piscar"},
        "sonolento": {"animation": "frente", "frame": "dormir"},
        "estressado": {"animation": "frente", "frame": "susto"},
        "triste": {"animation": "frente", "frame": "idle"},
    },
    "views": {
        "back": {"animation": "costas", "frame": "idle"},
        "front": {"animation": "frente", "frame": "idle"},
        "profile": {"animation": "virada_vistas", "frame": "perfil"},
    },
    "default": {"animation": "virada_vistas", "frame": "perfil"},
}


def transparent_crop(sheet: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    sprite = sheet.crop(box).convert("RGBA")
    pixels = sprite.load()
    for y in range(sprite.height):
        for x in range(sprite.width):
            r, g, b, _ = pixels[x, y]
            if (r, g, b) == KEY:
                pixels[x, y] = (r, g, b, 0)
            elif y == 0 and (r, g, b) == (255, 243, 160):
                # Contact cells have a pale top border that touches the sprite crop.
                # The original actor canvas has transparent padding above its crest.
                pixels[x, y] = (r, g, b, 0)
    return sprite


def package_animations(source_manifest: dict) -> dict:
    packed: dict[str, object] = {}
    for name, animation in source_manifest["animations"].items():
        columns = 4
        rows = (len(animation["frames"]) + columns - 1) // columns
        atlas = Image.new("RGBA", (columns * 32, rows * 44), (0, 0, 0, 0))
        frames = []
        sheet = Image.open(SOURCE / f"{name}_1x.png").convert("RGB")
        for index, item in enumerate(animation["frames"]):
            x, y, _, _ = item["contact_cell_1x"]
            sprite = transparent_crop(sheet, (x + 8, y, x + 40, y + 44))
            column, row = index % columns, index // columns
            atlas.paste(sprite, (column * 32, row * 44), sprite)
            frame = {key: value for key, value in item.items()
                     if key != "contact_cell_1x"}
            frame.update({"rect": [column * 32, row * 44, 32, 44],
                          "label_key": item["label"].lower().replace(" ", "_")})
            frames.append(frame)
        atlas.save(DESTINATION / f"{name}.png", optimize=True)
        packed[name] = {"sheet": f"{name}.png", "frames": frames}
    return packed


def package_lod() -> dict:
    source = Image.open(SOURCE / "niveis_profundidade_1x.png").convert("RGB")
    atlas = Image.new("RGBA", (len(LOD_SIZES) * 32, len(LOD_ROWS) * 44),
                      (0, 0, 0, 0))
    entries: dict[str, object] = {}
    # The source contact sheet uses left=76, cell width=52, row height=48,
    # header=18, and centers each 32x44 native render inside each cell.
    for row, (view, action) in enumerate(LOD_ROWS):
        entries[f"{view}_{action}"] = []
        for column, size in enumerate(LOD_SIZES):
            x = 76 + column * 52 + 10
            y = 18 + row * 48 + 2
            sprite = transparent_crop(source, (x, y, x + 32, y + 44))
            atlas.paste(sprite, (column * 32, row * 44), sprite)
            entries[f"{view}_{action}"].append({
                "size": size, "rect": [column * 32, row * 44, 32, 44],
                "pivot": [16, 40], "native_draw": True,
            })
    atlas.save(DESTINATION / "lod.png", optimize=True)
    return {"sheet": "lod.png", "sizes": list(LOD_SIZES),
            "entries": entries}


def package_pixel_ui_frame() -> None:
    """Create a small nine-slice pixel border for cards and dialog frames."""
    frame = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
    pixels = frame.load()
    dark = (75, 59, 60, 255)
    brown = (114, 83, 62, 255)
    gold = (255, 217, 59, 255)
    for start_x, start_y in ((0, 0), (6, 0), (0, 6), (6, 6)):
        for y in range(start_y, start_y + 3):
            for x in range(start_x, start_x + 3):
                pixels[x, y] = brown
        pixels[start_x, start_y] = gold
        pixels[start_x + 1, start_y] = gold
        pixels[start_x, start_y + 1] = gold
        pixels[start_x + 1, start_y + 1] = dark
    for value in range(3, 6):
        pixels[value, 0] = gold
        pixels[value, 8] = dark
        pixels[0, value] = gold
        pixels[8, value] = dark
    frame.save(DESTINATION / "ui_frame.png", optimize=True)


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads(
        (SOURCE / "inventario_frames.json").read_text(encoding="utf-8"))
    animations = package_animations(source_manifest)
    # A full-body stride is the initial distance contract (three quarters of
    # the 32 px source body); tune it in JSON if motion profiling changes it.
    animations["corrida_lateral"]["distance_per_cycle_px"] = 24
    animations["corrida_lateral"]["distance_is_tunable_estimate"] = True
    manifest = {
        "schema_version": 1,
        "source": "docs/mockups/piu/vistas_etapa1/inventario_frames.json",
        "canvas": source_manifest["canvas"],
        "pivot_canvas": source_manifest["pivot_canvas"],
        "transparent_key_removed": "#24365E",
        "animations": animations,
        "routes": source_manifest.get("routes", ANIMATION_ROUTES),
        "lod": package_lod(),
    }
    package_pixel_ui_frame()
    (DESTINATION / "animations.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    total = sum(len(item["frames"]) for item in animations.values())
    print(f"Packaged {total} frames into {DESTINATION}")


if __name__ == "__main__":
    main()
