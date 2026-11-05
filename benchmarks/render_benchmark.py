from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import psutil
import yaml
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.gl_renderer import EyeCanvas
from synapse_pet.ui.qt_app import configure_opengl


def vram_snapshot() -> tuple[int | None, str]:
    pid = os.getpid()
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=False)
        for line in result.stdout.splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) >= 2 and fields[0].isdigit() and int(fields[0]) == pid:
                return int(fields[1]), "process_mib"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    # WDDM exposes per-process memory for AMD and NVIDIA adapters. `typeperf`
    # reads that Windows performance counter without requiring a GPU vendor CLI.
    try:
        result = subprocess.run(
            ["typeperf", r"\GPU Process Memory(*)\Dedicated Usage", "-sc", "1"],
            capture_output=True, text=True, timeout=6, check=False)
        rows = [row for row in csv.reader(io.StringIO(result.stdout)) if row]
        if result.returncode == 0 and len(rows) >= 2:
            total_bytes = 0.0
            found = False
            for header, value in zip(rows[0][1:], rows[1][1:]):
                match = re.search(r"pid_(\d+)_", header, flags=re.IGNORECASE)
                if match and int(match.group(1)) == pid:
                    total_bytes += float(value)
                    found = True
            if found:
                return round(total_bytes / (1024 * 1024)), "process_dedicated_mib"
    except (OSError, ValueError, subprocess.TimeoutExpired, csv.Error):
        pass

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=False)
        first = result.stdout.splitlines()[0].strip()
        return int(first), "system_gpu_mib"
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None, "unavailable"


def measure_phase(app: QApplication, canvas: EyeCanvas, seconds: float,
                  fps_target: int, active: bool) -> dict[str, object]:
    canvas.set_state(VisualState(happiness=0.68, energy=0.77, stress=0.14,
                                 curiosity=0.74, boredom=0.24, active=active))
    before_frames = canvas.rendered_frames
    process = psutil.Process()
    process.cpu_percent(None)
    renderer_label = canvas.current_renderer.lower()
    cpu_renderer = ("cpu" in renderer_label or "ascii direto" in renderer_label
                    or "qpainter" in renderer_label)
    vram, vram_scope = ((0, "cpu_renderer_no_opengl") if cpu_renderer
                        else vram_snapshot())
    timer_ticks = 0
    renderer_widget = canvas._stack.currentWidget()

    def request_frame() -> None:
        nonlocal timer_ticks
        timer_ticks += 1
        renderer_widget.update()

    timer = QTimer()
    timer.setInterval(round(1000 / fps_target))
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    # Trigger the active child renderer. Updating only the container widget does
    # not make QOpenGLWidget repaint when the app is used outside its main loop.
    timer.timeout.connect(request_frame)
    timer.start()
    samples: list[float] = []
    next_sample = time.monotonic() + 0.3
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        app.processEvents()
        now = time.monotonic()
        if now >= next_sample:
            samples.append(process.cpu_percent(None))
            next_sample = now + 0.3
        time.sleep(0.002)
    app.processEvents()
    elapsed = time.monotonic() - start
    timer.stop()
    frames = canvas.rendered_frames - before_frames
    after_vram, after_scope = ((0, "cpu_renderer_no_opengl") if cpu_renderer
                               else vram_snapshot())
    cpu_average = sum(samples) / len(samples) if samples else 0.0
    return {
        "fps_target": fps_target,
        "fps_measured": round(frames / max(elapsed, 0.001), 2),
        "timer_callbacks_per_second": round(timer_ticks / max(elapsed, 0.001), 2),
        "cpu_percent_average": round(cpu_average, 2),
        "vram_mib_before": vram,
        "vram_mib_after": after_vram,
        "vram_scope": after_scope if after_vram is not None else vram_scope,
    }


def main() -> None:
    def parse_size(value: str) -> tuple[int, int]:
        try:
            width, height = (int(part) for part in value.lower().split("x", 1))
        except (ValueError, TypeError):
            raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT, por exemplo 1920x1080")
        if width < 700 or height < 390:
            raise argparse.ArgumentTypeError("A janela precisa ter pelo menos 700x390")
        return width, height

    parser = argparse.ArgumentParser(description="Benchmark CPU, VRAM and FPS by eye mode")
    parser.add_argument("--seconds", type=float, default=3.0,
                        help="duration per mode and activity phase")
    parser.add_argument("--renderer", choices=("ascii", "cpu", "auto"), default="ascii")
    parser.add_argument("--render-style", choices=("spectral", "ascii", "vector"),
                        default=None,
                        help="estilo do olho; por padrão usa pet.render_style do YAML")
    parser.add_argument("--size", type=parse_size, default=(1000, 600),
                        metavar="WIDTHxHEIGHT",
                        help="tamanho da janela; use a resolução da tela para testar tela cheia")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "render_benchmark.json")
    args = parser.parse_args()
    configure_opengl()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    config = yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
    visual = config.get("visual", {})
    pet = config.get("pet", {})
    render_style = args.render_style or str(pet.get("render_style", "spectral"))
    window = QMainWindow()
    canvas = EyeCanvas(args.renderer,
                       int(visual.get("width", 800)), int(visual.get("height", 450)),
                       int(visual.get("ascii_columns", 300)),
                       int(visual.get("ascii_rows", 100)),
                       str(visual.get("palette", "cyan_amber_white")),
                       int(visual.get("max_particles", 48)), window,
                       ascii_max_columns=int(visual.get("ascii_max_columns", 170)),
                       ascii_max_rows=int(visual.get("ascii_max_rows", 96)),
                       render_style=render_style,
                       spectral_config=pet.get("spectral", {}))
    window.setCentralWidget(canvas)
    window.resize(*args.size)
    window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
    window.show()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    result: dict[str, object] = {
        "renderer_requested": args.renderer,
        "render_style": render_style,
        "renderer_used": canvas.current_renderer,
        "window_size": list(args.size),
        "opengl_driver": (canvas._gl._ctx.info.get("GL_RENDERER")
                          if canvas._gl and canvas._gl._ctx else None),
        "opengl_vendor": (canvas._gl._ctx.info.get("GL_VENDOR")
                          if canvas._gl and canvas._gl._ctx else None),
        "internal_resolution": ([canvas._ascii_eye.columns, canvas._ascii_eye.rows]
                                if canvas._ascii_eye else
                                [canvas._gl.internal_width, canvas._gl.internal_height]
                                if canvas._gl else [visual.get("width", 800),
                                                   visual.get("height", 450)]),
        "seconds_per_phase": args.seconds,
        "modes": {},
    }
    for mode in ("ascii", "hud"):
        canvas.set_mode(mode)
        phases = {}
        for name, fps, active in (("active", 30, True), ("idle", 5, False)):
            phases[name] = measure_phase(app, canvas, args.seconds, fps, active)
        result["modes"][mode] = phases
        print(f"{mode.upper():6} active {phases['active']['fps_measured']:5} fps, "
              f"CPU {phases['active']['cpu_percent_average']:5}%  |  idle "
              f"{phases['idle']['fps_measured']:5} fps, "
              f"CPU {phases['idle']['cpu_percent_average']:5}%")
    result["renderer_used"] = canvas.current_renderer
    result["gpu_vram_note"] = (
        "process_dedicated_mib comes from WDDM; process_mib is NVIDIA per-process; "
        "system_gpu_mib is a whole-adapter total. cpu_renderer_no_opengl excludes Windows composition.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Renderer: {canvas.current_renderer}")
    print(f"Report: {args.output}")
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
