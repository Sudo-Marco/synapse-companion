from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.qt_app import configure_opengl
from synapse_pet.ui.gl_renderer import EyeCanvas


STATES = {
    "observando": VisualState(),
    "alegre": VisualState(happiness=0.94, energy=0.88, stress=0.05,
                           curiosity=0.84, boredom=0.06),
    "estressado": VisualState(happiness=0.24, energy=0.52, stress=0.91,
                               curiosity=0.65, boredom=0.40),
    "triste": VisualState(happiness=0.16, energy=0.42, stress=0.16,
                          curiosity=0.20, boredom=0.91),
    "curioso": VisualState(happiness=0.62, energy=0.80, stress=0.10,
                           curiosity=0.97, boredom=0.10),
    "sonolento": VisualState(happiness=0.44, energy=0.10, stress=0.10,
                             curiosity=0.18, boredom=0.48),
    "dormindo": VisualState(happiness=0.48, energy=0.02, stress=0.04,
                            curiosity=0.12, boredom=0.34,
                            expression_override="dormindo"),
    "carinho": VisualState(happiness=0.91, energy=0.82, stress=0.04,
                           curiosity=0.33, affection=0.96, boredom=0.04),
    "aberto": VisualState(expression_override="aberto"),
    "semicerrado": VisualState(expression_override="semicerrado"),
    "arregalado": VisualState(expression_override="arregalado"),
    "piscar": VisualState(expression_override="piscar"),
}


def settle(app: QApplication, duration: float = 0.22) -> None:
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture renderer and emotion screenshots")
    parser.add_argument("--renderer", choices=("ascii", "cpu", "auto"), default="ascii")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    configure_opengl()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    window = QMainWindow()
    canvas = EyeCanvas(args.renderer, 960, 540, 100, 56,
                       "cyan_amber_white", 48, window)
    window.setCentralWidget(canvas)
    window.resize(1000, 600)
    window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
    window.show()
    args.output.mkdir(parents=True, exist_ok=True)
    settle(app, 1.4)
    print(f"backend={canvas.current_renderer}; frames={canvas.rendered_frames}; "
                f"gl_valid={canvas._gl.isValid() if canvas._gl else 'n/a'}; "
          f"gl_error={canvas._gl._error if canvas._gl else ''}")

    references: dict[str, np.ndarray] = {}
    for name, state in STATES.items():
        canvas.set_state(state)
        for mode in ("ascii", "hud"):
            canvas.set_mode(mode)
            settle(app, 0.5)
            image = canvas.current_frame()
            pixels = np.frombuffer(image.constBits(), dtype=np.uint8,
                                    count=image.sizeInBytes())
            if mode == "ascii" and name == "observando":
                print(f"first frame pixels: min={pixels.min()} max={pixels.max()} "
                      f"mean={pixels.mean():.1f} paint_count={canvas.rendered_frames}")
                if pixels.max() == 0:
                    raise RuntimeError("The renderer produced a black screenshot.")
            reference = references.get(mode)
            if reference is None:
                references[mode] = pixels.copy()
            else:
                difference = float(np.mean(np.abs(
                    pixels.astype(np.int16) - reference.astype(np.int16))))
                print(f"{name}_{mode}: mean image difference {difference:.2f}")
                if difference < 0.25:
                    raise RuntimeError(f"State {name!r} did not visibly change in {mode} mode.")
            path = args.output / f"{name}_{mode}.png"
            if not image.save(str(path), "PNG"):
                raise RuntimeError(f"Could not write screenshot: {path}")
            print(f"{path.name}: {image.width()}x{image.height()} · {canvas.current_renderer}")
    canvas.set_state(STATES["observando"])
    canvas.set_mode("hud")
    settle(app)
    path = args.output / "observando_hud.png"
    canvas.current_frame().save(str(path), "PNG")
    print(f"{path.name}: {canvas.current_renderer}")
    window.close()
    settle(app, 0.1)


if __name__ == "__main__":
    main()
