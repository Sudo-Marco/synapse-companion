from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage

from synapse_pet.runtime.engine import PetEngine
from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.qt_app import PetWindow, ensure_application


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the floating pet with Qt offscreen.")
    parser.add_argument("--output", type=Path,
                        default=Path("docs/screenshots/floating_pet_offscreen.png"))
    args = parser.parse_args()
    app = ensure_application()
    with tempfile.TemporaryDirectory(prefix="synapse_pet_capture_") as temporary:
        engine = PetEngine(seed=41, data_dir=Path(temporary))
        engine.set_autonomy_enabled(False)
        window = PetWindow(engine)
        window._enter_floating_mode()
        window.last_state = VisualState(happiness=0.82, energy=0.88, curiosity=0.72)
        window.canvas.set_state(window.last_state)
        loop = QEventLoop()
        QTimer.singleShot(900, loop.quit)
        loop.exec()
        pixmap = window.grab()
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(args.output), "PNG"):
            raise RuntimeError(f"could not save screenshot to {args.output}")
        engine.stop()
        window._really_close = True
        window.close()
    app.quit()
    print(f"Saved offscreen pet render: {args.output}")


if __name__ == "__main__":
    main()
