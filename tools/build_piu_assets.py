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
        "lod": package_lod(),
    }
    (DESTINATION / "animations.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    total = sum(len(item["frames"]) for item in animations.values())
    print(f"Packaged {total} frames into {DESTINATION}")


if __name__ == "__main__":
    main()
