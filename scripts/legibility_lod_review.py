from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from statistics import median

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from synapse_pet.runtime.visual_state import StateAnimator, VisualState
from synapse_pet.ui.ascii_runtime import AnimatedAsciiEyeWidget
from synapse_pet.ui.qt_app import ensure_application
from legibility_review_round2 import BASE_SIZE, PHOTO, STAMP, _benchmark

OUT = ROOT / "docs" / "screenshots" / "legibility" / "lod_final"
HEIGHTS = (48, 64, 96, 128, 192, 256)
BACKGROUNDS = ("preto", "branco", "cinza_medio", "azul_escuro",
               "xadrez_ruido", "foto_paisagem")
BENCHMARK_REPETITIONS = 3


def benchmark_median(widget: AnimatedAsciiEyeWidget, fps: int) -> dict[str, object]:
    samples = [_benchmark(widget, fps) for _ in range(BENCHMARK_REPETITIONS)]
    result: dict[str, object] = {
        "target_fps": fps,
        "repetitions": BENCHMARK_REPETITIONS,
        "actual_fps": round(median(float(sample["actual_fps"])
                                    for sample in samples), 2),
        "cpu_percent_one_core": round(median(
            float(sample["cpu_percent_one_core"]) for sample in samples), 2),
        "cpu_ms_per_frame": round(median(
            float(sample["cpu_ms_per_frame"]) for sample in samples), 3),
        "samples_cpu_ms_per_frame": [sample["cpu_ms_per_frame"]
                                     for sample in samples],
    }
    return result


def make_backgrounds(width: int, height: int) -> dict[str, Image.Image]:
    result = {
        "preto": Image.new("RGB", (width, height), (0, 0, 0)),
        "branco": Image.new("RGB", (width, height), (255, 255, 255)),
        "cinza_medio": Image.new("RGB", (width, height), (128, 128, 128)),
        "azul_escuro": Image.new("RGB", (width, height), (7, 20, 47)),
    }
    rng = np.random.default_rng(451)
    noise = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    yy, xx = np.indices((height, width))
    checker = ((xx // max(1, width // 19) + yy // max(1, height // 9)) % 2).astype(bool)
    noise[checker] = (noise[checker].astype(np.uint16) // 2 + 105).clip(0, 255)
    noise[~checker] = (noise[~checker].astype(np.uint16) // 2 + 20).clip(0, 255)
    result["xadrez_ruido"] = Image.fromarray(noise, "RGB")
    with Image.open(PHOTO) as source:
        photo = source.convert("RGB")
        scale = max(width / photo.width, height / photo.height)
        resized = photo.resize((round(photo.width * scale), round(photo.height * scale)),
                               Image.Resampling.LANCZOS)
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        result["foto_paisagem"] = resized.crop((left, top, left + width, top + height))
    return result


def new_widget(width: int, height: int) -> AnimatedAsciiEyeWidget:
    ensure_application()
    widget = AnimatedAsciiEyeWidget(
        columns=max(6, width // 8), rows=max(6, height // 8), compact=True,
        max_columns=max(64, width // 8 + 20), max_rows=max(40, height // 8 + 20),
        scene_time="day", density="normal",
        outline={"theme_auto": False, "double": True, "thickness_px": 1,
                 "font_size": 7, "dark": [7, 13, 23], "light": [250, 252, 255],
                 "plate_alpha": 0.42, "plate_dark": [12, 20, 32],
                 "plate_light": [235, 242, 246]},
    )
    widget.resize(width, height)
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
    widget._last_pointer_move = 1_000.0
    widget._next_glance = float("inf")
    widget._next_blink = float("inf")
    widget._blink_started = None
    widget._update_attention = lambda _now: None
    return widget


def render_eye(widget: AnimatedAsciiEyeWidget, width: int, height: int) -> Image.Image:
    frame = widget.render_frame(now=1_000.0, local_time=STAMP)
    frame = widget._composite_pet_plate(frame)
    image = Image.frombytes("RGBA", (frame.width(), frame.height()),
                            frame.bits().tobytes())
    return image.resize((width, height), Image.Resampling.LANCZOS)


def save_contact(folder: Path, images: dict[str, Image.Image], width: int,
                 height: int, *, scale: int = 1) -> None:
    columns, rows = 3, 2
    sheet = Image.new("RGB", (columns * width * scale, rows * height * scale),
                      (10, 13, 20))
    for index, name in enumerate(BACKGROUNDS):
        image = images[name].convert("RGB")
        if scale != 1:
            image = image.resize((width * scale, height * scale), Image.Resampling.NEAREST)
        x = (index % columns) * width * scale
        y = (index // columns) * height * scale
        sheet.paste(image, (x, y))
    sheet.save(folder)


def luminance(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]


def contrast(first, second):
    high, low = np.maximum(first, second), np.minimum(first, second)
    return (high + 0.05) / (low + 0.05)


def contrast_metrics(widget: AnimatedAsciiEyeWidget, eye: Image.Image,
                     backgrounds: dict[str, Image.Image],
                     composed: dict[str, Image.Image]) -> list[dict[str, object]]:
    width, height = eye.size
    yy, xx = np.indices((height, width))
    gx = (xx + 0.5) * widget.columns / width
    gy = (yy + 0.5) * widget.rows / height
    cx, cy, rx, ry, opening = widget._eye_geometry
    eye_radius = np.sqrt(((gx - cx) / max(0.1, rx)) ** 2
                         + ((gy - cy) / max(0.1, ry * opening)) ** 2)
    edge = np.abs(eye_radius - 1.0) <= 0.13
    ix, iy, iris_radius = widget._iris_geometry
    _, _, pupil_radius = widget._pupil_geometry
    pupil_region = np.hypot(gx - ix, gy - iy) <= pupil_radius
    iris_distance = np.hypot(gx - ix, gy - iy)
    iris_region = (iris_distance > pupil_radius + 0.3) & (iris_distance <= iris_radius)
    palette, *_ = widget._cycle(STAMP)
    dark_luma = float(luminance(np.asarray(widget.outline_dark)))
    light_luma = float(luminance(np.asarray(widget.outline_light)))
    pupil_iris = float(contrast(luminance(np.asarray(palette["pupil"])),
                                luminance(np.asarray(palette["iris"]))))
    iris_sclera = float(contrast(luminance(np.asarray(palette["iris"])),
                                 luminance(np.asarray(palette["sclera"]))))
    highlight_sclera = float(contrast(luminance(np.asarray(palette["white"])),
                                      luminance(np.asarray(palette["sclera"]))))
    rows = []
    for name in BACKGROUNDS:
        bg = np.asarray(backgrounds[name], dtype=np.uint8)
        background_luma = luminance(bg)
        actual = np.asarray(composed[name], dtype=np.uint8)
        actual_luma = luminance(actual)
        # The continuous silhouette has two keylines. At each edge point the
        # stronger of the two is the visible stroke against that local pixel.
        edge_values = np.maximum(contrast(background_luma, dark_luma),
                                 contrast(background_luma, light_luma))[edge]
        pupil_values = contrast(actual_luma[pupil_region],
                                background_luma[pupil_region])
        iris_values = contrast(actual_luma[iris_region],
                               background_luma[iris_region])
        rows.append({
            "background": name,
            "silhouette_vs_background_p05": round(float(np.percentile(edge_values, 5)), 2),
            "pupil_vs_iris": round(pupil_iris, 2),
            "iris_vs_sclera": round(iris_sclera, 2),
            "pupil_vs_background_median": round(float(np.median(pupil_values)), 2),
            "iris_vs_background_median": round(float(np.median(iris_values)), 2),
            "reflection_vs_sclera": round(highlight_sclera, 2),
            "pass": bool(np.percentile(edge_values, 5) >= 3.0
                         and pupil_iris >= 3.0 and highlight_sclera >= 3.0),
        })
    return rows


def save_comparisons(height: int, width: int, output: Path) -> None:
    before_root = OUT / "before" / f"{height}px"
    after_root = OUT / "after" / f"{height}px"
    pair_root = output / f"{height}px"
    pair_root.mkdir(parents=True, exist_ok=True)
    paired = {}
    for name in BACKGROUNDS:
        before = Image.open(before_root / f"{name}.png").convert("RGB")
        after = Image.open(after_root / f"{name}.png").convert("RGB")
        pair = Image.new("RGB", (width * 2, height), (12, 16, 23))
        pair.paste(before, (0, 0))
        pair.paste(after, (width, 0))
        pair.save(pair_root / f"{name}_antes_depois_1x.png")
        paired[name] = pair
    save_contact(output / f"contato_{height}px_comparacao_1x.png",
                 paired, width * 2, height)
    save_contact(output / f"contato_{height}px_comparacao_ampliado_3x.png",
                 paired, width * 2, height, scale=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("after",), default="after",
        help="renderiza a versão atual; as capturas históricas de antes são preservadas",
    )
    args = parser.parse_args()
    phase_root = OUT / "after"
    phase_root.mkdir(parents=True, exist_ok=True)
    metadata = {"phase": "after", "heights_px": list(HEIGHTS),
                "aspect_ratio": 1.9, "scale": "direct render to native output dimensions",
                "backgrounds": list(BACKGROUNDS), "lod": {}, "contrast": {},
                "performance": {}}
    for height in HEIGHTS:
        width = round(height * 1.9)
        widget = new_widget(width, height)
        eye = render_eye(widget, width, height)
        backgrounds = make_backgrounds(width, height)
        composed = {name: Image.alpha_composite(bg.convert("RGBA"), eye).convert("RGB")
                    for name, bg in backgrounds.items()}
        metadata["contrast"][str(height)] = contrast_metrics(
            widget, eye, backgrounds, composed)
        folder = phase_root / f"{height}px"
        folder.mkdir(parents=True, exist_ok=True)
        for name, image in composed.items():
            image.save(folder / f"{name}.png")
        save_contact(phase_root / f"contato_{height}px_1x.png", composed, width, height)
        save_contact(phase_root / f"contato_{height}px_ampliado_3x.png", composed,
                     width, height, scale=3)
        save_comparisons(height, width, OUT / "comparacao")
        metadata["lod"][str(height)] = {
            "width_px": width,
            "grid_columns": widget.columns,
            "grid_rows": widget.rows,
            "lod_level": getattr(widget, "lod_level", "legacy"),
        }
    benchmark_widget = new_widget(*BASE_SIZE)
    metadata["performance"] = {
        "active_30_fps": benchmark_median(benchmark_widget, 30),
        "idle_5_fps": benchmark_median(benchmark_widget, 5),
    }
    lines = [
        "# LOD ASCII — legibilidade por altura e fundo", "",
        "As capturas são renders headless do próprio widget, compostos sobre fundos de teste. Cada arquivo `*_1x` mantém a resolução física indicada no nome; os arquivos `ampliado_3x` usam nearest-neighbor apenas para inspeção visual. A foto é um recurso local de teste e nenhuma tela do usuário é lida.", "",
        "Silhueta é o percentil 5 do melhor contraste WCAG entre os dois filetes configurados (escuro e claro) contra cada pixel do fundo na borda geométrica fechada. Pupila/íris, íris/esclera e reflexo/esclera comparam as cores efetivas da paleta; por isso estes valores internos são iguais nos seis fundos. Pupila/fundo e íris/fundo usam pixels renderizados nas regiões do olho e variam conforme o fundo; valores baixos em fundos de luminância semelhante indicam mistura da cor preenchida, não perda da borda dupla.", "",
        f"O custo é a mediana de {BENCHMARK_REPETITIONS} medições do mesmo widget offscreen por quadro nos timers ativos (30 FPS) e em repouso (5 FPS). A linha anterior do mesmo benchmark foi 2,511 ms/quadro ativo e 2,727 ms/quadro em repouso.", "",
        "| Altura | Fundo | Silhueta/fundo p05 | Pupila/íris | Íris/esclera | Pupila/fundo mediana | Íris/fundo mediana | Reflexo/esclera | Resultado |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for height in HEIGHTS:
        for row in metadata["contrast"][str(height)]:
            lines.append(
                    f"| {height} px | {row['background']} | "
                f"{row['silhouette_vs_background_p05']}:1 | {row['pupil_vs_iris']}:1 | "
                f"{row['iris_vs_sclera']}:1 | {row['pupil_vs_background_median']}:1 | "
                f"{row['iris_vs_background_median']}:1 | "
                f"{row['reflection_vs_sclera']}:1 | "
                f"{'PASSA' if row['pass'] else 'FALHA'} |")
    active = metadata["performance"]["active_30_fps"]
    idle = metadata["performance"]["idle_5_fps"]
    active_delta = (active["cpu_ms_per_frame"] / 2.511 - 1.0) * 100.0
    idle_delta = (idle["cpu_ms_per_frame"] / 2.727 - 1.0) * 100.0
    lines.extend(("", "## Desempenho", "",
                  "| Fase | Linha anterior (ms/quadro) | Atual (ms/quadro) | Delta | FPS medido | Dentro de 10% |",
                  "|---|---:|---:|---:|---:|---|",
                  f"| Ativo | 2,511 | {active['cpu_ms_per_frame']} | {active_delta:+.1f}% | {active['actual_fps']} | {'SIM' if abs(active_delta) <= 10 else 'NÃO'} |",
                  f"| Repouso | 2,727 | {idle['cpu_ms_per_frame']} | {idle_delta:+.1f}% | {idle['actual_fps']} | {'SIM' if abs(idle_delta) <= 10 else 'NÃO'} |"))
    (OUT / "RELATORIO_CONTRASTE.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    (phase_root / "capturas.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
