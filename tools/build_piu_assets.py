from __future__ import annotations

"""Package the approved Piu contact sheets as editable transparent sprite sheets."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "mockups" / "piu" / "vistas_etapa1"
V03_SOURCE = ROOT / "docs" / "mockups" / "piu" / "v03_stage1" / "sprites"
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

V03_ROUTES = {
    "actions": {
        "away": {"animation": "corrida_costas", "mode": "stride", "match_lod": True},
        "return": {"animation": "corrida_frente", "mode": "stride", "match_lod": True},
        "walk": {"animation": "corrida_perfil", "mode": "stride", "match_lod": True},
        "run": {"animation": "corrida_perfil", "mode": "stride", "match_lod": True},
        "dance_sway": {"animation": "danca_balanco", "mode": "time_loop"},
        "dance_hop": {"animation": "danca_pulinho", "mode": "time_loop"},
        "dance_head": {"animation": "danca_cabecada", "mode": "time_loop"},
        "think": {"animation": "pensando", "frame": "pensando", "match_lod": True},
        "rest": {"animation": "descansando", "frame": "descansando", "match_lod": True},
        "listen": {"animation": "ouvindo", "frame": "ouvindo", "match_lod": True},
        "caught": {"animation": "pego_no_alto", "frame": "pego_no_alto", "match_lod": True},
        "fall": {"animation": "queda_pancada", "frame": "queda_pancada", "match_lod": True},
        "peek": {"animation": "espiando", "frame": "espiando", "match_lod": True},
    },
    "emotions": {
        "curioso": {"animation": "pensando", "frame": "pensando", "match_lod": True},
        "dormindo": {"animation": "descansando", "frame": "descansando", "match_lod": True},
        "sonolento": {"animation": "cansado_frente", "frame": "cansado_frente", "match_lod": True},
        "ouvindo": {"animation": "ouvindo", "frame": "ouvindo", "match_lod": True},
    },
    "views": {
        "back": {"animation": "idle_costas", "frame": "idle", "match_lod": True},
        "front": {"animation": "idle_frente", "frame": "idle", "match_lod": True},
        "profile": {"animation": "idle_perfil", "frame": "idle", "match_lod": True},
    },
    "default": {"animation": "idle_perfil", "frame": "idle", "match_lod": True},
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


def _native_frame_specs() -> dict[str, list[tuple[str, int, str, int]]]:
    """Map runtime animation names to editable PNG names and frame metadata."""
    groups: dict[str, list[tuple[str, int, str, int]]] = {}
    for view in ("perfil", "frente", "costas"):
        idle_name = {"perfil": "idle_perfil", "frente": "idle_frente",
                     "costas": "idle_costas"}[view]
        run_name = {"perfil": "corrida_perfil", "frente": "corrida_frente",
                    "costas": "corrida_costas"}[view]
        groups[idle_name] = [(f"{view}_{size}_idle.png", size, view, 1000)
                             for size in (48, 32, 20)]
        groups[run_name] = [
            (f"{view}_{size}_run_{phase:02d}.png", size, view, 100)
            for size in (48, 32, 20) for phase in range(4)]

    poses = {
        "pensando": ("pensando", "frente", 1),
        "cansado_perfil": ("cansado_perfil", "perfil", 1),
        "cansado_frente": ("cansado_frente", "frente", 1),
        "descansando": ("descansando", "frente", 1),
        "ouvindo": ("ouvindo", "frente", 1),
        "pego_no_alto": ("pego_no_alto", "frente", 1),
        "queda_pancada": ("queda_pancada", "perfil", 1),
        "espiando": ("espiando", "frente", 1),
        "danca_balanco": ("danca_balanco", "frente", 3),
        "danca_pulinho": ("danca_pulinho", "frente", 4),
        "danca_cabecada": ("danca_cabecada", "perfil", 3),
    }
    for name, (source_name, view, count) in poses.items():
        groups[name] = [(f"pose_{source_name}_{frame:02d}.png", 48, view, 120)
                        for frame in range(count)]
    return groups


def package_native_sprites() -> dict[str, object]:
    """Pack approved 48/32/20 px source frames without resampling them."""
    packed: dict[str, object] = {}
    for name, specs in _native_frame_specs().items():
        columns = 4
        rows = (len(specs) + columns - 1) // columns
        atlas = Image.new("RGBA", (columns * 48, rows * 48), (0, 0, 0, 0))
        frames = []
        for index, (filename, size, view, duration) in enumerate(specs):
            source = Image.open(V03_SOURCE / filename).convert("RGBA")
            if source.size != (size, size):
                raise ValueError(f"{filename}: esperado {size}x{size}, recebido {source.size}")
            column, row = index % columns, index // columns
            x, y = column * 48, row * 48
            atlas.alpha_composite(source, (x, y))
            box = source.getchannel("A").getbbox() or (0, 0, size, size)
            label_key = ("idle" if "_idle" in filename else
                         f"step_{filename[-6:-4]}" if "_run_" in filename else
                         name if len(specs) == 1 else f"{name}_{index}")
            pivot_y = round(44 * size / 48)
            frames.append({
                "label": label_key,
                "label_key": label_key,
                "rect": [x, y, size, size],
                "native_size": size,
                "view": view,
                "pivot": [size // 2, pivot_y],
                "hitbox": list(box),
                "duration_ms": duration,
                "loop": name.startswith(("corrida_", "danca_")),
            })
        atlas.save(DESTINATION / f"{name}.png", optimize=True)
        packed[name] = {"sheet": f"{name}.png", "frames": frames}
        if name.startswith("corrida_"):
            packed[name]["distance_per_cycle_px"] = 24
            packed[name]["distance_is_tunable_estimate"] = True
    return packed


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
    native_animations = package_native_sprites()
    animations.update(native_animations)
    routes = dict(source_manifest.get("routes", ANIMATION_ROUTES))
    # Preserve the legacy routes as a fallback while making the approved
    # 0.3 artwork the active default for supported views and actions.
    for family, mappings in V03_ROUTES.items():
        routes.setdefault(family, {})
        routes[family].update(mappings)
    manifest = {
        "schema_version": 2,
        "source": ["docs/mockups/piu/vistas_etapa1/inventario_frames.json",
                   "docs/mockups/piu/v03_stage1/sprites/"],
        "canvas": source_manifest["canvas"],
        "pivot_canvas": source_manifest["pivot_canvas"],
        "transparent_key_removed": "#24365E",
        "animations": animations,
        "routes": routes,
        "lod": package_lod(),
        "native_lod_sizes": [48, 32, 20],
    }
    package_pixel_ui_frame()
    (DESTINATION / "animations.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    total = sum(len(item["frames"]) for item in animations.values())
    print(f"Packaged {total} frames into {DESTINATION}")


if __name__ == "__main__":
    main()
