from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage

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


def _pil_rgba(image: QImage) -> Image.Image:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (rgba.width(), rgba.height()),
                           rgba.constBits().tobytes())


def save_run_gif(widget: PixelPetWidget) -> None:
    """Capture one bounded, deterministic lateral run in the transparent mode."""
    widget.set_mode("pet")
    widget.motion = widget.motion.__class__(pivot=widget.motion.pivot)
    widget.render_frame(6.0, datetime(2026, 11, 5, 12, 30))
    widget.request_move("right", "run")
    frames: list[Image.Image] = []
    for index in range(34):
        frame = widget.render_frame(6.05 + index / 20.0,
                                    datetime(2026, 11, 5, 12, 30))
        rgba = _pil_rgba(frame)
        background = Image.new("RGBA", rgba.size, (255, 0, 255, 255))
        background.alpha_composite(rgba)
        indexed = background.convert("RGB").quantize(colors=255)
        palette = indexed.getpalette() or []
        palette += [0] * (768 - len(palette))
        palette[255 * 3:255 * 3 + 3] = [255, 0, 255]
        indexed.putpalette(palette)
        alpha = rgba.getchannel("A")
        indexed.paste(255, mask=alpha.point(lambda value: 255 if value < 128 else 0))
        frames.append(indexed)
    frames[0].save(OUTPUT / "piu-animacao.gif", save_all=True,
                   append_images=frames[1:], duration=50, loop=0,
                   transparency=255, disposal=2, optimize=False)


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
    save_run_gif(pet)
    pet.close()
    print(f"Pixel previews saved in {OUTPUT}")


if __name__ == "__main__":
    main()
