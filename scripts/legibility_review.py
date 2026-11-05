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
OUTPUT = ROOT / "docs" / "screenshots" / "legibility"
PHOTO = OUTPUT / "assets" / "lake_mountain_landscape.jpg"
SIZE = (320, 180)
STAMP = datetime(2026, 7, 1, 12, 0, 0).astimezone()


def _backgrounds() -> dict[str, Image.Image]:
    width, height = SIZE
    result = {
        "preto": Image.new("RGB", SIZE, (0, 0, 0)),
        "branco": Image.new("RGB", SIZE, (255, 255, 255)),
        "cinza_medio": Image.new("RGB", SIZE, (128, 128, 128)),
        "azul_escuro": Image.new("RGB", SIZE, (7, 20, 47)),
    }

    rng = np.random.default_rng(451)
    noise = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    yy, xx = np.indices((height, width))
    checker = ((xx // 12 + yy // 12) % 2).astype(bool)
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
        left = (scaled.width - width) // 2
        top = (scaled.height - height) // 2
        result["foto_paisagem"] = scaled.crop((left, top, left + width, top + height))
    return result


def _eye_widget() -> AnimatedAsciiEyeWidget:
    ensure_application()
    widget = AnimatedAsciiEyeWidget(columns=40, rows=22, scene_time="day",
                                    compact=True, max_columns=48, max_rows=30)
    widget.resize(*SIZE)
    # QWidget resize events are deferred in Qt's offscreen platform; make the
    # headless benchmark use the same internal resolution as a visible window.
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


def _render(widget: AnimatedAsciiEyeWidget) -> Image.Image:
    widget._last_time = 1_000.0
    frame = widget.render_frame(now=1_000.0,
                                local_time=STAMP)
    if hasattr(widget, "_composite_pet_plate"):
        frame = widget._composite_pet_plate(frame)
    pixels = frame.bits().tobytes()
    rgba = Image.frombytes("RGBA", (frame.width(), frame.height()), pixels)
    return rgba.resize(SIZE, Image.Resampling.NEAREST)


def _composite(eye: Image.Image, background: Image.Image) -> Image.Image:
    return Image.alpha_composite(background.convert("RGBA"), eye).convert("RGB")


def _relative_luminance(rgb: tuple[int, int, int] | np.ndarray) -> float | np.ndarray:
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055) ** 2.4)
    luminance = (0.2126 * linear[..., 0] + 0.7152 * linear[..., 1]
                 + 0.0722 * linear[..., 2])
    return float(luminance) if luminance.ndim == 0 else luminance


def _contrast(first: float, second: float) -> float:
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def _palette_colors(widget: AnimatedAsciiEyeWidget) -> tuple[tuple[int, int, int],
                                                              tuple[int, int, int]]:
    palette, *_ = widget._cycle(STAMP)
    return palette["pupil"], palette["iris"]


def _contrast_rows(backgrounds: dict[str, Image.Image],
                   widget: AnimatedAsciiEyeWidget) -> list[dict[str, object]]:
    pupil_color, iris_color = _palette_colors(widget)
    pupil_iris = _contrast(_relative_luminance(pupil_color),
                           _relative_luminance(iris_color))
    dark_outline = getattr(widget, "outline_dark", (5, 12, 20))
    light_outline = getattr(widget, "outline_light", None)
    rows = []
    for name, background in backgrounds.items():
        rgb = np.asarray(background, dtype=np.uint8)
        y0, y1 = round(SIZE[1] * 0.22), round(SIZE[1] * 0.78)
        x0, x1 = round(SIZE[0] * 0.16), round(SIZE[0] * 0.84)
        sample = rgb[y0:y1, x0:x1]
        bg_luminance = _relative_luminance(sample)
        dark_lum = _relative_luminance(dark_outline)
        dark_contrast = ((np.maximum(bg_luminance, dark_lum) + 0.05)
                         / (np.minimum(bg_luminance, dark_lum) + 0.05))
        if light_outline is None:
            local_best = dark_contrast
        else:
            light_lum = _relative_luminance(light_outline)
            light_contrast = ((np.maximum(bg_luminance, light_lum) + 0.05)
                              / (np.minimum(bg_luminance, light_lum) + 0.05))
            local_best = np.maximum(dark_contrast, light_contrast)
        rows.append({
            "fundo": name,
            "contorno_duplo_p05": round(float(np.percentile(local_best, 5)), 2),
            "contorno_duplo_mediana": round(float(np.median(local_best)), 2),
            "pupila_vs_iris": round(pupil_iris, 2),
        })
    return rows


def _benchmark(widget: AnimatedAsciiEyeWidget, fps: int,
               duration_s: float = 8.0) -> dict[str, float | int]:
    surface = QImage(*SIZE, QImage.Format.Format_RGBA8888)
    wall_start = time.perf_counter()
    end = wall_start + duration_s
    next_frame = wall_start
    frames = 0
    render_time = 0.0
    while True:
        current = time.perf_counter()
        if current >= end:
            break
        if current >= next_frame:
            widget._next_glance = float("inf")
            widget._next_blink = float("inf")
            widget._last_pointer_move = current
            surface.fill(0)
            painter = QPainter(surface)
            frame_start = time.perf_counter()
            widget.render(painter, QPoint())
            painter.end()
            render_time += time.perf_counter() - frame_start
            frames += 1
            next_frame += 1.0 / fps
        else:
            time.sleep(min(0.003, next_frame - current))
    wall = time.perf_counter() - wall_start
    return {
        "target_fps": fps,
        "actual_fps": round(frames / wall, 2),
        "frames": frames,
        "cpu_percent_one_core": round(render_time / wall * 100.0, 2),
        "cpu_ms_per_frame": round(render_time / max(1, frames) * 1000.0, 3),
    }


def _contact_sheet(phase: str, names: list[str]) -> None:
    labels = ImageFont.load_default()
    sheet = Image.new("RGB", (SIZE[0] * 3, (SIZE[1] + 26) * 2), (17, 22, 29))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(names):
        image_path = OUTPUT / phase / f"{name}.png"
        image = Image.open(image_path).convert("RGB")
        x = (index % 3) * SIZE[0]
        y = (index // 3) * (SIZE[1] + 26)
        draw.text((x + 8, y + 6), name.replace("_", " "), fill=(235, 240, 245), font=labels)
        sheet.paste(image, (x, y + 26))
    sheet.save(OUTPUT / f"contact_{phase}.png")


def _comparison_sheet(names: list[str]) -> None:
    labels = ImageFont.load_default()
    cell_width, cell_height = SIZE[0] * 2, SIZE[1] + 32
    sheet = Image.new("RGB", (cell_width * 3, cell_height * 2), (17, 22, 29))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(names):
        x = (index % 3) * cell_width
        y = (index // 3) * cell_height
        draw.text((x + 8, y + 4), name.replace("_", " "),
                  fill=(235, 240, 245), font=labels)
        before = Image.open(OUTPUT / "before" / f"{name}.png").convert("RGB")
        after = Image.open(OUTPUT / "after" / f"{name}.png").convert("RGB")
        draw.text((x + 8, y + 18), "ANTES", fill=(235, 240, 245), font=labels)
        draw.text((x + SIZE[0] + 8, y + 18), "DEPOIS", fill=(235, 240, 245), font=labels)
        sheet.paste(before, (x, y + 32))
        sheet.paste(after, (x + SIZE[0], y + 32))
    sheet.save(OUTPUT / "comparativo_6_fundos.png")


def _write_reports(phase: str, contrast_rows: list[dict[str, object]],
                   benchmarks: dict[str, object]) -> None:
    payload = {"phase": phase, "contrast": contrast_rows,
               "performance": benchmarks}
    (OUTPUT / f"{phase}_metrics.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    headers = ("Fundo", "Contorno p05", "Contorno mediana", "Pupila / íris")
    lines = ["| " + " | ".join(headers) + " |",
             "|---|---:|---:|---:|"]
    for row in contrast_rows:
        lines.append(
            f"| {row['fundo']} | {row['contorno_duplo_p05']}:1 | "
            f"{row['contorno_duplo_mediana']}:1 | {row['pupila_vs_iris']}:1 |")
    lines.extend(("", "CPU (média de 8 s por modo):"))
    for mode, data in benchmarks.items():
        lines.append(f"- {mode}: {data}")
    (OUTPUT / f"{phase}_relatorio.md").write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / args.phase).mkdir(exist_ok=True)
    backgrounds = _backgrounds()
    widget = _eye_widget()
    eye = _render(widget)
    for name, background in backgrounds.items():
        _composite(eye, background).save(OUTPUT / args.phase / f"{name}.png")
    _contact_sheet(args.phase, list(backgrounds))
    contrast_rows = _contrast_rows(backgrounds, widget)
    benchmarks = {
        "ativo_30_fps": _benchmark(widget, 30),
        "repouso_5_fps": _benchmark(widget, 5),
    }
    _write_reports(args.phase, contrast_rows, benchmarks)
    if args.phase == "after" and all(
            (OUTPUT / "before" / f"{name}.png").is_file() for name in backgrounds):
        _comparison_sheet(list(backgrounds))
    print(json.dumps({"phase": args.phase, "contrast": contrast_rows,
                      "performance": benchmarks,
                      "output": str(OUTPUT)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
