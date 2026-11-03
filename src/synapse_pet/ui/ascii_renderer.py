from __future__ import annotations

import math
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtGui import QImage


def qimage_rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    height, width = image.height(), image.width()
    rows = np.frombuffer(image.constBits(), dtype=np.uint8,
                         count=image.sizeInBytes()).reshape(height, image.bytesPerLine())
    return rows[:, :width * 3].reshape(height, width, 3).copy()


def array_qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
    height, width, _ = rgb.shape
    return QImage(rgb.data, width, height, width * 3,
                  QImage.Format.Format_RGB888).copy()


class AsciiRenderer:
    """Pillow-created monospace glyph atlas and vectorized per-cell postprocess."""

    DENSITY_GLYPHS = " .,:;irsXA253hMHGS#9B&@"
    EDGE_GLYPHS = "/\\|-"
    PALETTES = {
        "cyan_amber_white": ((44, 204, 219), (238, 176, 48), (219, 237, 239)),
        "cyan_white": ((38, 184, 205), (66, 205, 218), (225, 242, 242)),
        "amber_white": ((183, 119, 31), (235, 177, 54), (255, 241, 208)),
        "monochrome": ((68, 188, 198), (150, 211, 214), (238, 247, 244)),
    }

    def __init__(self, columns: int = 300, rows: int = 100,
                 palette: str = "cyan_amber_white", source_width: int = 960,
                 source_height: int = 540) -> None:
        self.columns = max(40, int(columns))
        self.rows = max(20, int(rows))
        self.palette_name = palette
        # Render one atlas cell at about the source-pixel size it occupies on
        # screen. A 300x100 grid no longer creates a 1800x1000 intermediate.
        self.cell_width = max(1, math.ceil(int(source_width) / self.columns))
        self.cell_height = max(1, math.ceil(int(source_height) / self.rows))
        self.font_size = max(4, self.cell_height)
        self.font = self._font()
        self.glyphs, self.atlas, self.density = self._build_atlas()
        self.edge_masks = {char: self._raster_glyph(char) for char in self.EDGE_GLYPHS}
        self.rain_phase = np.random.default_rng(9137).uniform(0, self.rows, self.columns)
        self.rain_char = np.random.default_rng(23).integers(1, len(self.glyphs), self.columns)
        self.palette = np.asarray(self.PALETTES.get(
            palette, self.PALETTES["cyan_amber_white"]), dtype=np.float32)
        self.frame = 0

    def _font(self) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for path in (windows / "consola.ttf", windows / "cour.ttf"):
            if path.exists():
                return ImageFont.truetype(str(path), self.font_size)
        try:
            return ImageFont.truetype("DejaVuSansMono.ttf", self.font_size)
        except OSError:
            return ImageFont.load_default()

    def _build_atlas(self) -> tuple[str, np.ndarray, np.ndarray]:
        # Keep directional marks out of the brightness ramp: otherwise "|" is
        # naturally selected for every bright cell and obscures the image.
        chars = list(dict.fromkeys(self.DENSITY_GLYPHS))
        masks: list[np.ndarray] = []
        densities: list[float] = []
        for char in chars:
            mask = self._raster_glyph(char)
            masks.append(mask)
            densities.append(float(mask.mean()))
        order = np.argsort(np.asarray(densities), kind="stable")
        ordered_chars = "".join(chars[i] for i in order)
        return ordered_chars, np.stack(masks)[order], np.asarray(densities)[order]

    def _raster_glyph(self, char: str) -> np.ndarray:
        glyph = Image.new("L", (self.cell_width, self.cell_height), 0)
        ImageDraw.Draw(glyph).text((0, -1), char, fill=255, font=self.font)
        return np.asarray(glyph, dtype=np.uint8) > 32

    def render(self, source: QImage, now: float | None = None) -> QImage:
        self.frame += 1
        now = time.monotonic() if now is None else now
        image = Image.fromarray(qimage_rgb(source), "RGB")
        small = image.resize((self.columns, self.rows), Image.Resampling.BOX)
        cells = np.asarray(small, dtype=np.float32)
        luminance = (cells[..., 0] * 0.2126 + cells[..., 1] * 0.7152
                     + cells[..., 2] * 0.0722) / 255.0

        # 3x3 Sobel suppresses the shader's fine scanlines before edge glyph mapping.
        left = np.roll(luminance, 1, axis=1)
        right = np.roll(luminance, -1, axis=1)
        top = np.roll(luminance, 1, axis=0)
        bottom = np.roll(luminance, -1, axis=0)
        top_left = np.roll(left, 1, axis=0)
        top_right = np.roll(right, 1, axis=0)
        bottom_left = np.roll(left, -1, axis=0)
        bottom_right = np.roll(right, -1, axis=0)
        gx = (top_right + 2.0 * right + bottom_right
              - top_left - 2.0 * left - bottom_left) * 0.125
        gy = (bottom_left + 2.0 * bottom + bottom_right
              - top_left - 2.0 * top - top_right) * 0.125
        magnitude = np.hypot(gx, gy)
        density_index = np.searchsorted(self.density, luminance, side="left")
        density_index = np.clip(density_index, 0, len(self.glyphs) - 1)
        edge = magnitude > 0.20
        horizontal = np.abs(gx) > np.abs(gy) * 1.8
        vertical = np.abs(gy) > np.abs(gx) * 1.8
        diagonal_back = gx * gy < 0.0
        edge_horizontal = edge & horizontal
        edge_vertical = edge & vertical
        edge_slash = edge & ~horizontal & ~vertical & diagonal_back
        edge_backslash = edge & ~horizontal & ~vertical & ~diagonal_back

        darkness = luminance < 0.10
        for column in range(0, self.columns, 13):
            head = int((self.rain_phase[column] + now * 5.0) % self.rows)
            if darkness[head, column]:
                density_index[head, column] = self.rain_char[column]

        # Preserve source hue while quantizing toward the chosen cybernetic palette.
        amber = (cells[..., 0] > cells[..., 2] * 1.12) & (cells[..., 0] > 72)
        white = luminance > 0.78
        palette_index = np.where(white, 2, np.where(amber, 1, 0))
        palette_color = self.palette[palette_index]
        source_mix = np.clip(luminance[..., None] * 0.30, 0.0, 0.30)
        color = palette_color * (1.0 - source_mix) + cells * source_mix
        color *= (0.30 + 0.70 * luminance[..., None])
        color[white] = np.maximum(color[white], 216.0)

        glyph_cells = self.atlas[density_index].copy()
        glyph_cells[edge_horizontal] = self.edge_masks["|"]
        glyph_cells[edge_vertical] = self.edge_masks["-"]
        glyph_cells[edge_slash] = self.edge_masks["/"]
        glyph_cells[edge_backslash] = self.edge_masks["\\"]
        # Atlas indices are [row, column, glyph-y, glyph-x]; transpose the two
        # cell axes before flattening so each text cell stays in its grid slot.
        mask = glyph_cells.transpose(0, 2, 1, 3).reshape(
            self.rows * self.cell_height, self.columns * self.cell_width)
        # Quantize before expanding to pixels to avoid several full-frame float
        # arrays in this CPU post-process.
        color += np.clip((color - 205.0) * 0.10, 0.0, 20.0)
        color[1::2] *= 0.93
        cell_colors = np.repeat(np.repeat(np.clip(color, 0, 255).astype(np.uint8),
                                          self.cell_height, axis=0),
                                self.cell_width, axis=1)
        output = np.empty((*mask.shape, 3), dtype=np.uint8)
        output[:] = (3, 10, 14)
        output[mask] = cell_colors[mask]
        return array_qimage(output)
