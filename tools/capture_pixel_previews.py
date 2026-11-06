from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime
from pathlib import Path

from synapse_pet.runtime.visual_state import VisualState
from synapse_pet.ui.pixel_renderer import PixelPetWidget
from synapse_pet.ui.qt_app import ensure_application


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "screenshots" / "piu"


def save(widget: PixelPetWidget, filename: str, now: float,
         state: VisualState, local_time: datetime) -> None:
    widget.set_state(state)
    image = widget.render_frame(now, local_time)
    image.save(str(OUTPUT / filename))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ensure_application()
    widget = PixelPetWidget(seed=41)
    widget.resize(960, 540)
    widget.show()
    ensure_application().processEvents()
    save(widget, "piu-cenario-dia.png", 2.0,
         VisualState(), datetime(2026, 11, 5, 12, 30))
    save(widget, "piu-cenario-feliz.png", 3.0,
         VisualState(happiness=0.91, affection=0.82, dopamine=0.18),
         datetime(2026, 11, 5, 16, 20))
    save(widget, "piu-cenario-sono.png", 4.0,
         VisualState(expression_override="dormindo", energy=0.03),
         datetime(2026, 11, 5, 23, 40))
    widget.close()

    pet = PixelPetWidget(compact=True, seed=41)
    pet.resize(320, 180)
    pet.set_mode("pet")
    pet.show()
    ensure_application().processEvents()
    image = pet.render_frame(5.0, datetime(2026, 11, 5, 12, 30))
    image.save(str(OUTPUT / "piu-flutuante.png"))
    pet.close()
    print(f"Pixel previews saved in {OUTPUT}")


if __name__ == "__main__":
    main()
