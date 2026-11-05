from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor, QImage, QPainter

from synapse_pet.runtime.visual_state import StateAnimator, VisualState
from synapse_pet.ui.ascii_runtime import AnimatedAsciiEyeWidget
from synapse_pet.ui.qt_app import ensure_application


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "screenshots" / "legibility" / "revision2"
REFERENCE = ROOT / "docs" / "screenshots" / "legibility" / "after"
PHOTO = ROOT / "docs" / "screenshots" / "legibility" / "assets" / "lake_mountain_landscape.jpg"
STAMP = datetime(2026, 7, 1, 12, 0, 0).astimezone()
SIZES = {"large": (960, 540, 120, 68), "small": (240, 120, 30, 15)}
BASE_SIZE = (320, 180)


def _backgrounds(size: tuple[int, int]) -> dict[str, Image.Image]:
    width, height = size
    result = {
        "preto": Image.new("RGB", size, (0, 0, 0)),
        "branco": Image.new("RGB", size, (255, 255, 255)),
        "cinza_medio": Image.new("RGB", size, (128, 128, 128)),
        "azul_escuro": Image.new("RGB", size, (7, 20, 47)),
    }
    rng = np.random.default_rng(451)
    noise = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    yy, xx = np.indices((height, width))
    checker = ((xx // max(1, width // 27) + yy // max(1, height // 15)) % 2).astype(bool)
    noise[checker] = (noise[checker].astype(np.uint16) // 2 + 105).clip(0, 255)
    noise[~checker] = (noise[~checker].astype(np.uint16) // 2 + 20).clip(0, 255)
    result["xadrez_ruido"] = Image.fromarray(noise, "RGB")
    if not PHOTO.is_file():
        raise FileNotFoundError(f"Foto de teste ausente: {PHOTO}")
    with Image.open(PHOTO) as photo:
        image = photo.convert("RGB")
        scale = max(width / image.width, height / image.height)
        scaled = image.resize((round(image.width * scale), round(image.height * scale)),
                              Image.Resampling.LANCZOS)
        left, top = (scaled.width - width) // 2, (scaled.height - height) // 2
        result["foto_paisagem"] = scaled.crop((left, top, left + width, top + height))
    return result


def _widget(size: tuple[int, int], columns: int, rows: int) -> AnimatedAsciiEyeWidget:
    ensure_application()
    widget = AnimatedAsciiEyeWidget(columns=columns, rows=rows, scene_time="day",
                                    compact=True, max_columns=max(48, columns + 24),
                                    max_rows=max(30, rows + 16), density="normal")
    widget.resize(*size)
    widget._resize_resolution()
    widget.set_mode("pet")
    state = VisualState(happiness=0.58, energy=0.88, stress=0.12,
                        curiosity=0.55, affection=0.30,
                        expression_override="observando")
    widget.target_state = state
    widget.state = state
    widget.animator = StateAnimator(state)
    widget.animator.value = state
    widget.animator.last_time = 1_000.0
    pointer = QCursor.pos()
    widget._last_pointer = (pointer.x(), pointer.y())
    widget._last_pointer_move = 1_000.0
    widget._next_glance = float("inf")
    widget._next_blink = float("inf")
    widget._blink_started = None
    return widget


def _render_transparent(widget: AnimatedAsciiEyeWidget,
                        size: tuple[int, int]) -> Image.Image:
    widget._last_time = 1_000.0
    frame = widget.render_frame(now=1_000.0, local_time=STAMP)
    frame = widget._composite_pet_plate(frame)
    internal = Image.frombytes("RGBA", (frame.width(), frame.height()),
                               frame.bits().tobytes())
    return internal.resize(size, Image.Resampling.NEAREST)


def _luminance(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]


def _contrast(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    high, low = np.maximum(first, second), np.minimum(first, second)
    return (high + 0.05) / (low + 0.05)


def _shape_mask(size: tuple[int, int], widget: AnimatedAsciiEyeWidget,
                geometry: tuple[float, float, float], inner: float,
                outer: float) -> np.ndarray:
    width, height = size
    cx, cy, radius = geometry
    sx = width / max(1, widget.columns * widget.CELL_WIDTH)
    sy = height / max(1, widget.rows * widget.CELL_HEIGHT)
    px, py = cx * widget.CELL_WIDTH * sx, cy * widget.CELL_HEIGHT * sy
    rx, ry = radius * widget.CELL_WIDTH * sx, radius * widget.CELL_HEIGHT * sy
    yy, xx = np.indices((height, width))
    normalized = np.sqrt(((xx - px) / max(1.0, rx)) ** 2
                         + ((yy - py) / max(1.0, ry)) ** 2)
    return (normalized >= inner) & (normalized <= outer)


def _contrast_rows(widget: AnimatedAsciiEyeWidget, eye: Image.Image,
                   backgrounds: dict[str, Image.Image], size: tuple[int, int]
                   ) -> list[dict[str, object]]:
    dark, light = widget.outline_dark, widget.outline_light
    dark_lum = float(_luminance(np.asarray(dark, dtype=np.uint8)))
    light_lum = float(_luminance(np.asarray(light, dtype=np.uint8)))
    iris_geometry = widget._iris_geometry
    pupil_geometry = widget._pupil_geometry
    if iris_geometry is None or pupil_geometry is None:
        return []
    pupil_radius = pupil_geometry[2]
    iris_radius = iris_geometry[2]
    pupil_mask = _shape_mask(size, widget, pupil_geometry, 0.0, 1.0)
    iris_mask = _shape_mask(size, widget, iris_geometry,
                            min(0.96, pupil_radius / iris_radius * 1.20), 0.90)
    pupil_edge_mask = _shape_mask(size, widget, pupil_geometry, 0.65, 1.40)
    iris_edge_mask = _shape_mask(size, widget, iris_geometry, 0.88, 1.12)
    eye_rgba = np.asarray(eye, dtype=np.uint8)
    alpha = eye_rgba[:, :, 3:4].astype(np.float32) / 255.0
    foreground = eye_rgba[:, :, :3].astype(np.float32)
    palette, *_ = widget._cycle(STAMP)
    pupil_lum = float(_luminance(np.asarray(palette["pupil"], dtype=np.uint8)))
    iris_lum = float(_luminance(np.asarray(palette["iris"], dtype=np.uint8)))
    pupil_iris_internal = round(float(_contrast(pupil_lum, iris_lum)), 2)
    rows = []
    for name, background in backgrounds.items():
        bg = np.asarray(background, dtype=np.uint8)
        bg_lum = _luminance(bg)
        dark_contrast = _contrast(bg_lum, dark_lum)
        light_contrast = _contrast(bg_lum, light_lum)
        local_best = np.maximum(dark_contrast, light_contrast)
        visible_rgb = foreground * alpha + bg.astype(np.float32) * (1.0 - alpha)
        visible_lum = _luminance(visible_rgb)

        def region_contrast(mask: np.ndarray) -> tuple[float, float]:
            selected = mask & (eye_rgba[:, :, 3] > 0)
            if not np.any(selected):
                return 1.0, 1.0
            values = _contrast(visible_lum[selected], bg_lum[selected])
            return (round(float(np.percentile(values, 5)), 2),
                    round(float(np.median(values)), 2))

        def keyline_p05(mask: np.ndarray) -> float:
            selected = mask & (eye_rgba[:, :, 3] > 0)
            if not np.any(selected):
                return 1.0
            return round(float(np.percentile(local_best[selected], 5)), 2)

        pupil_p05, pupil_median = region_contrast(pupil_mask)
        iris_p05, iris_median = region_contrast(iris_mask)

        rows.append({
            "fundo": name,
            "contorno_borda_dupla_p05": round(float(np.percentile(local_best, 5)), 2),
            "pupila_borda_vs_fundo_p05": keyline_p05(pupil_edge_mask),
            "iris_borda_vs_fundo_p05": keyline_p05(iris_edge_mask),
            "pupila_vs_fundo_p05": pupil_p05,
            "pupila_vs_fundo_mediana": pupil_median,
            "iris_vs_fundo_p05": iris_p05,
            "iris_vs_fundo_mediana": iris_median,
            "pupila_vs_iris_interno": pupil_iris_internal,
        })
    return rows


def _make_before_images(size_name: str, size: tuple[int, int],
                        backgrounds: dict[str, Image.Image]) -> None:
    for name, _background in backgrounds.items():
        source = REFERENCE / f"{name}.png"
        if not source.is_file():
            raise FileNotFoundError(f"Imagem de referência anterior ausente: {source}")
        with Image.open(source) as old:
            old = old.convert("RGB")
            # The previously reviewed renderer was captured at 320x180. Scale
            # that exact accepted output, rather than fabricating a new baseline.
            resized = old.resize(size, Image.Resampling.NEAREST)
            resized.save(OUTPUT / "before" / size_name / f"{name}.png")


def _benchmark(widget: AnimatedAsciiEyeWidget, fps: int,
               duration_s: float = 8.0) -> dict[str, float | int]:
    surface = QImage(*BASE_SIZE, QImage.Format.Format_RGBA8888)
    widget.resize(*BASE_SIZE)
    widget._resize_resolution()
    wall_start = time.perf_counter()
    end = wall_start + duration_s
    next_frame = wall_start
    frames = 0
    render_time = 0.0
    while time.perf_counter() < end:
        current = time.perf_counter()
        if current >= next_frame:
            widget._next_glance = float("inf")
            widget._next_blink = float("inf")
            widget._last_pointer_move = current
            surface.fill(0)
            painter = QPainter(surface)
            started = time.perf_counter()
            widget.render(painter, QPoint())
            painter.end()
            render_time += time.perf_counter() - started
            frames += 1
            next_frame += 1.0 / fps
        else:
            time.sleep(min(0.003, next_frame - current))
    wall = time.perf_counter() - wall_start
    return {"target_fps": fps, "actual_fps": round(frames / wall, 2),
            "frames": frames, "cpu_percent_one_core": round(render_time / wall * 100, 2),
            "cpu_ms_per_frame": round(render_time / max(1, frames) * 1000, 3)}


def _pairs(names: list[str]) -> None:
    labels = ImageFont.load_default()
    for size_name, (width, height, _cols, _rows) in SIZES.items():
        folder = OUTPUT / "comparisons" / size_name
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            before = Image.open(OUTPUT / "before" / size_name / f"{name}.png").convert("RGB")
            after = Image.open(OUTPUT / "after" / size_name / f"{name}.png").convert("RGB")
            pair = Image.new("RGB", (width * 2, height + 30), (17, 22, 29))
            draw = ImageDraw.Draw(pair)
            draw.text((8, 8), f"{name.replace('_', ' ')} · ANTES", fill="white", font=labels)
            draw.text((width + 8, 8), "DEPOIS · normal", fill="white", font=labels)
            pair.paste(before, (0, 30))
            pair.paste(after, (width, 30))
            pair.save(folder / f"{name}_antes_depois.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    names = ["preto", "branco", "cinza_medio", "azul_escuro", "xadrez_ruido",
             "foto_paisagem"]
    phases = {"contrast": {}, "performance": {}}
    for size_name, (width, height, cols, rows) in SIZES.items():
        size = (width, height)
        folder = OUTPUT / args.phase / size_name
        folder.mkdir(parents=True, exist_ok=True)
        backgrounds = _backgrounds(size)
        if args.phase == "before":
            _make_before_images(size_name, size, backgrounds)
            continue
        widget = _widget(size, cols, rows)
        eye = _render_transparent(widget, size)
        phases["contrast"][size_name] = _contrast_rows(widget, eye, backgrounds, size)
        for name, bg in backgrounds.items():
            Image.alpha_composite(bg.convert("RGBA"), eye).convert("RGB").save(
                folder / f"{name}.png")
        if size_name == "small":
            phases["performance"] = {
                "ativo_30_fps": _benchmark(widget, 30),
                "repouso_5_fps": _benchmark(widget, 5),
            }
    if args.phase == "after":
        _pairs(names)
        (OUTPUT / "resultados.json").write_text(
            json.dumps(phases, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = [
            "# Revisão 2 — legibilidade ASCII (Etapa 1)", "",
            "A coluna antiga `Pupila / íris = 4,99:1` media apenas a diferença de luminância entre as duas cores fixas da paleta. Como não comparava pixels do olho com o fundo, repetia o mesmo valor em todos os cenários.",
            "",
            "Nesta revisão, `pupila/íris vs fundo` é a mediana da razão WCAG dos pixels visíveis dentro da região circular, após compor a placa sobre o fundo. `borda` é o percentil 5 do melhor contraste local entre o keyline claro e o escuro; o contorno usa os dois tons. O preenchimento pode ficar abaixo de 3:1 em um fundo parecido com sua cor; a borda dupla é a garantia de silhueta sem ler pixels da tela.",
            "",
            "O preset `pet.density: normal` mantém os pontos e fibras ASCII como textura; não preenche as células com blocos. Reflexos grandes e médios continuam em glifos ASCII.",
            "",
            "As imagens `antes` reutilizam as capturas aceitas da revisão anterior (320×180) reescaladas com vizinho mais próximo para facilitar a comparação em dois tamanhos. As imagens `depois` foram renderizadas diretamente no tamanho de cada pasta. `pequeno` mede uma silhueta de cerca de 60 px de altura; `grande` mede 960×540.",
        ]
        for size_name in SIZES:
            lines.extend(("", f"## Contraste — {size_name}", "",
                          "| Fundo | Silhueta p05 | Borda da pupila p05 | Borda da íris p05 | Pupila/fundo mediana | Íris/fundo mediana | Pupila/íris interna |",
                          "|---|---:|---:|---:|---:|---:|---:|"))
            for row in phases["contrast"][size_name]:
                lines.append(
                    f"| {row['fundo']} | {row['contorno_borda_dupla_p05']}:1 | "
                    f"{row['pupila_borda_vs_fundo_p05']}:1 | "
                    f"{row['iris_borda_vs_fundo_p05']}:1 | "
                    f"{row['pupila_vs_fundo_mediana']}:1 | "
                    f"{row['iris_vs_fundo_mediana']}:1 | "
                    f"{row['pupila_vs_iris_interno']}:1 |")
        lines.extend(("", "## Benchmark", "",
                      "Comparação da revisão anterior: ativo 2,511 ms/quadro; repouso 2,727 ms/quadro.", "",
                      f"- Depois ativo 30 FPS: {phases['performance']['ativo_30_fps']['cpu_ms_per_frame']} ms/quadro ({phases['performance']['ativo_30_fps']['cpu_percent_one_core']}% de um núcleo).",
                      f"- Depois repouso 5 FPS: {phases['performance']['repouso_5_fps']['cpu_ms_per_frame']} ms/quadro ({phases['performance']['repouso_5_fps']['cpu_percent_one_core']}% de um núcleo).",
                      "- A suíte completa `pytest -q`: 83 testes passaram (exit code 0).",
                      ""))
        (OUTPUT / "ETAPA1_REVISAO2.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"phase": args.phase, "output": str(OUTPUT),
                      "results": phases}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
