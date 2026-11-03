from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True, slots=True)
class EyeState:
    key: str
    label: str
    openness: float = 0.88
    gaze: tuple[float, float] = (0.0, 0.0)
    pupil: str = "round"
    lid: str = "open"
    tear: bool = False
    sweat: bool = False
    blush: bool = False
    hearts: bool = False
    zzz: bool = False
    sparkles: bool = False
    brow: str = ""


STATES: tuple[EyeState, ...] = (
    EyeState("neutro", "NEUTRO", openness=0.86, gaze=(0.0, 0.0), blush=True),
    EyeState("feliz", "FELIZ", openness=0.73, gaze=(0.0, -0.5),
             lid="happy", blush=True, sparkles=True),
    EyeState("triste", "TRISTE", openness=0.58, gaze=(0.0, 2.2),
             lid="sad", tear=True, brow="sad"),
    EyeState("dormindo", "DORMINDO", openness=0.06, lid="closed", zzz=True),
    EyeState("assustado", "ASSUSTADO", openness=1.0, gaze=(0.0, 0.0),
             pupil="small", sweat=True, brow="raised"),
    EyeState("carinho", "CARINHO", openness=0.76, pupil="heart", lid="soft",
             blush=True, hearts=True, sparkles=True),
)


VARIANTS = {
    "A": {"name": "IRIS MAIOR · REDONDO", "rx": 27.0, "ry": 22.5,
          "iris": 14.0, "lashes": 2},
    "B": {"name": "OLHO ALONGADO · CILIOS", "rx": 30.0, "ry": 19.5,
          "iris": 12.5, "lashes": 4},
}


PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "nocturne": {
        "night": (7, 17, 31),
        # Colored shell keeps the eye in the luminous ASCII creature style;
        # reserve near-white for its tiny catchlights so it feels gentler.
        "sclera": (79, 145, 158),
        "iris": (62, 185, 196),
        "amber": (246, 198, 112),
        "rose": (236, 151, 178),
        "white": (255, 253, 244),
        "ink": (48, 91, 106),
        "pupil": (20, 53, 68),
    },
    "moonlit": {
        "night": (11, 18, 40),
        "sclera": (83, 137, 173),
        "iris": (91, 180, 219),
        "amber": (244, 211, 143),
        "rose": (229, 160, 190),
        "white": (255, 255, 249),
        "ink": (52, 84, 119),
        "pupil": (23, 50, 76),
    },
}


class _VectorLayer:
    """Transparent vector buffer, supersampled 2x per terminal cell."""

    def __init__(self, width: int, height: int, scale: int = 2) -> None:
        self.width, self.height, self.scale = width, height, scale
        self.image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    def _box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return tuple(round(value * self.scale) for value in box)

    def ellipse(self, box, fill=None, outline=None, width: float = 1.0) -> None:
        self.draw.ellipse(self._box(box), fill=fill, outline=outline,
                          width=max(1, round(width * self.scale)))

    def polygon(self, points: Iterable[tuple[float, float]], fill) -> None:
        scaled = [(round(x * self.scale), round(y * self.scale)) for x, y in points]
        self.draw.polygon(scaled, fill=fill)

    def line(self, points: Iterable[tuple[float, float]], fill,
             width: float = 1.0, joint: str = "curve") -> None:
        scaled = [(round(x * self.scale), round(y * self.scale)) for x, y in points]
        self.draw.line(scaled, fill=fill, width=max(1, round(width * self.scale)), joint=joint)

    def arc(self, box, start: float, end: float, fill,
            width: float = 1.0) -> None:
        self.draw.arc(self._box(box), start, end, fill=fill,
                      width=max(1, round(width * self.scale)))

    def cells(self, palette: dict[str, tuple[int, int, int]],
              glyphs: str, glyph_density: np.ndarray) -> tuple[np.ndarray, ...]:
        rgba = np.asarray(self.image, dtype=np.float32).reshape(
            self.height, self.scale, self.width, self.scale, 4)
        alpha_samples = rgba[..., 3] / 255.0
        alpha_sum = alpha_samples.sum(axis=(1, 3))
        coverage = alpha_sum / float(self.scale * self.scale)
        rgb_sum = (rgba[..., :3] * alpha_samples[..., None]).sum(axis=(1, 3))
        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        np.divide(rgb_sum, alpha_sum[..., None], out=rgb,
                  where=alpha_sum[..., None] > 0.0001)

        luma = (rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152
                + rgb[..., 2] * 0.0722) / 255.0
        density = coverage * (0.20 + 0.80 * (1.0 - luma))
        glyph_index = np.searchsorted(glyph_density, density, side="left")
        glyph_index = np.clip(glyph_index, 0, len(glyphs) - 1)
        chars = np.asarray(list(glyphs), dtype="<U1")[glyph_index]
        chars[coverage < 0.055] = " "

        gx = np.roll(coverage, -1, axis=1) - np.roll(coverage, 1, axis=1)
        gy = np.roll(coverage, -1, axis=0) - np.roll(coverage, 1, axis=0)
        edge = (np.hypot(gx, gy) > 0.40) & (coverage > 0.035)
        horizontal_gradient = np.abs(gx) > np.abs(gy) * 1.6
        vertical_gradient = np.abs(gy) > np.abs(gx) * 1.6
        diagonal_back = gx * gy < 0.0
        chars[edge & horizontal_gradient] = "|"
        chars[edge & vertical_gradient] = "-"
        chars[edge & ~horizontal_gradient & ~vertical_gradient & diagonal_back] = "/"
        chars[edge & ~horizontal_gradient & ~vertical_gradient & ~diagonal_back] = "\\"
        chars[coverage < 0.055] = " "

        palette_names = tuple(palette)
        palette_rgb = np.asarray([palette[name] for name in palette_names], dtype=np.float32)
        distance = ((rgb[..., None, :] - palette_rgb[None, None, :, :]) ** 2).sum(axis=3)
        color_ids = np.argmin(distance, axis=2).astype(np.uint8)
        tones = np.where(luma < 0.20, 0, np.where(luma < 0.58, 1, 2)).astype(np.uint8)
        tones[coverage < 0.055] = 0
        return chars, color_ids, tones, coverage


class AsciiEyeMockupRenderer:
    """Static ASCII eye and night-scene compositor used for design approval sheets."""

    GRID_WIDTH = 160
    GRID_HEIGHT = 90
    PANEL_WIDTH = 79
    CELL_WIDTH = 10
    CELL_HEIGHT = 10
    SUPERSAMPLE = 2
    DENSITY_RAMP = " .,:;irsXA253hMHGS#9B&@"
    EDGE_GLYPHS = "/\\|-"
    TONE_FACTORS = (0.70, 0.87, 1.0)

    def __init__(self, palette_name: str = "nocturne") -> None:
        if palette_name not in PALETTES:
            raise ValueError(f"Unknown palette {palette_name!r}; choose from {', '.join(PALETTES)}")
        self.palette_name = palette_name
        self.palette = PALETTES[palette_name]
        self.palette_names = tuple(self.palette)
        self.palette_rgb = np.asarray([self.palette[key] for key in self.palette_names],
                                      dtype=np.float32)
        self.font = self._load_font()
        self.glyphs, self.glyph_density, self.glyph_masks = self._build_glyph_atlas()
        self.shades = self._build_shades()

    @staticmethod
    def _load_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("consola.ttf", "cour.ttf", "lucon.ttf"):
            path = font_root / name
            if path.exists():
                return ImageFont.truetype(str(path), 10)
        try:
            return ImageFont.truetype("DejaVuSansMono.ttf", 10)
        except OSError:
            return ImageFont.load_default()

    def _mask_for_glyph(self, char: str) -> np.ndarray:
        tile = Image.new("L", (self.CELL_WIDTH, self.CELL_HEIGHT), 0)
        ImageDraw.Draw(tile).text((1, -1), char, fill=255, font=self.font)
        return np.asarray(tile, dtype=np.uint8) > 32

    def _build_glyph_atlas(self) -> tuple[str, np.ndarray, dict[str, np.ndarray]]:
        chars = list(dict.fromkeys(self.DENSITY_RAMP + self.EDGE_GLYPHS))
        masks = {char: self._mask_for_glyph(char) for char in chars}
        density_chars = list(dict.fromkeys(self.DENSITY_RAMP))
        density = np.asarray([masks[char].mean() for char in density_chars])
        order = np.argsort(density, kind="stable")
        ordered = "".join(density_chars[index] for index in order)
        return ordered, density[order], masks

    def _build_shades(self) -> np.ndarray:
        base = self.palette_rgb[:, None, :] * np.asarray(
            self.TONE_FACTORS, dtype=np.float32)[None, :, None]
        return np.clip(base, 0, 255).astype(np.uint8)

    @staticmethod
    def _bezier(points: tuple[tuple[float, float], ...], steps: int = 30):
        p0, p1, p2, p3 = (np.asarray(point, dtype=np.float32) for point in points)
        for t in np.linspace(0.0, 1.0, steps):
            u = 1.0 - t
            point = u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3
            yield float(point[0]), float(point[1])

    def _scene_layer(self, seed: int) -> _VectorLayer:
        layer = _VectorLayer(self.PANEL_WIDTH, self.GRID_HEIGHT, self.SUPERSAMPLE)
        night = self.palette["night"]
        moon = self.palette["sclera"]
        cyan = self.palette["iris"]
        amber = self.palette["amber"]
        dim_sclera = self._shade("sclera", 0.60)
        dim_iris = self._shade("iris", 0.62)

        # Crescent moon and soft, outlined craters.
        mx, my, mr = 12.5, 16.0, 7.2
        layer.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=moon + (170,))
        layer.ellipse((mx - mr + 3.5, my - mr - 2.0,
                       mx + mr + 3.5, my + mr - 2.0), fill=night + (255,))
        layer.ellipse((mx - 2.6, my - 1.5, mx - 0.8, my + 0.3),
                      outline=dim_sclera + (210,), width=0.9)
        layer.ellipse((mx + 1.4, my + 2.0, mx + 2.5, my + 3.1),
                      outline=dim_sclera + (195,), width=0.8)

        # Two cloud outlines drift across the high sky (fixed in these stills).
        cloud_color = dim_iris + (205,)
        for x, y, width in ((43.0, 15.0, 24.0), (52.0, 22.0, 18.0)):
            points = []
            points.extend(self._bezier(((x, y + 3), (x + 2, y - 2),
                                        (x + 7, y - 2), (x + 9, y + 2)), 10))
            points.extend(self._bezier(((x + 9, y + 2), (x + 12, y - 4),
                                        (x + 19, y - 2), (x + 20, y + 2)), 12))
            points.extend(((x + width, y + 3), (x, y + 3)))
            layer.line(points, cloud_color, width=0.95)

        # Distant hills are two separate silhouettes with clean edges.
        hill_far = [(0, 68), (9, 61), (18, 67), (27, 58), (38, 68),
                    (49, 60), (61, 68), (70, 62), (79, 68), (79, 90), (0, 90)]
        hill_near = [(0, 75), (12, 69), (23, 76), (35, 68), (48, 77),
                     (60, 70), (72, 77), (79, 73), (79, 90), (0, 90)]
        layer.polygon(hill_far, self._shade("iris", 0.28) + (205,))
        layer.line(hill_far[:9], dim_iris + (220,), width=1.15)
        layer.polygon(hill_near, self._shade("night", 2.3) + (238,))
        layer.line(hill_near[:8], dim_sclera + (145,), width=0.8)

        # A thin water horizon, short ripples, and the moon's broken reflection.
        layer.line(((0, 76), (79, 76)), dim_iris + (210,), width=0.9)
        for row, spans in ((79, ((3, 12), (23, 30), (46, 53), (65, 76))),
                           (82, ((12, 20), (32, 40), (56, 65), (72, 78))),
                           (85, ((1, 9), (24, 35), (44, 51), (60, 70))),
                           (88, ((8, 18), (30, 41), (50, 58), (69, 77)))):
            for left, right in spans:
                layer.line(((left, row), (right, row)), dim_iris + (185,), width=0.75)
        for row, half_width in ((79, 2.0), (82, 3.4), (85, 2.5), (88, 4.0)):
            layer.line(((mx - half_width, row), (mx + half_width, row)),
                       amber + (145,), width=0.7)

        # Fireflies and scene stars are deterministic per state sheet.
        rng = np.random.default_rng(seed)
        for index in range(5):
            x = float(rng.integers(4, self.PANEL_WIDTH - 4))
            y = float(rng.integers(37, 84))
            color = amber if index % 2 == 0 else cyan
            layer.ellipse((x - 0.45, y - 0.45, x + 0.45, y + 0.45),
                          fill=color + (190,))
        return layer

    def _shade(self, name: str, amount: float) -> tuple[int, int, int]:
        return tuple(int(max(0, min(255, channel * amount)))
                     for channel in self.palette[name])

    def _eye_layer(self, variant: str, state: EyeState) -> _VectorLayer:
        layer = _VectorLayer(self.PANEL_WIDTH, self.GRID_HEIGHT, self.SUPERSAMPLE)
        design = VARIANTS[variant]
        cx, cy = 39.5, 49.0
        rx, ry = float(design["rx"]), float(design["ry"]) * state.openness
        if state.lid == "closed":
            self._draw_closed_eye(layer, cx, cy, float(design["rx"]),
                                  float(design["ry"]),
                                  int(design["lashes"]), state)
            return layer

        night = self.palette["night"]
        sclera = self.palette["sclera"]
        iris = self.palette["iris"]
        amber = self.palette["amber"]
        white = self.palette["white"]
        rose = self.palette["rose"]
        xoff, yoff = state.gaze
        ix, iy = cx + xoff, cy + yoff
        # A soft almond silhouette echoes the reference's ASCII eye and avoids
        # the oversized round eyeball that made the first concept feel stern.
        eye_top = ((cx - rx, cy), (cx - rx * 0.66, cy - ry * 0.96),
                   (cx + rx * 0.66, cy - ry * 0.96), (cx + rx, cy))
        eye_bottom = ((cx + rx, cy), (cx + rx * 0.66, cy + ry * 0.96),
                      (cx - rx * 0.66, cy + ry * 0.96), (cx - rx, cy))
        top_points = list(self._bezier(eye_top, 36))
        bottom_points = list(self._bezier(eye_bottom, 36))
        layer.polygon(top_points + bottom_points, sclera + (255,))
        layer.line(top_points, self.palette["ink"] + (245,), width=1.6)
        layer.line(bottom_points, self.palette["ink"] + (245,), width=1.6)
        for sign in (-1, 1):
            end_x = cx + sign * (rx - 0.6)
            layer.ellipse((end_x - 1.0, cy - 1.1, end_x + 1.0, cy + 1.1),
                          fill=sclera + (255,))
        radius = float(design["iris"])
        if state.pupil == "small":
            radius *= 0.93
        ir = (ix - radius, iy - radius, ix + radius, iy + radius)
        layer.ellipse(ir, fill=iris + (255,), outline=night + (255,), width=1.5)
        layer.ellipse((ix - radius * 0.91, iy - radius * 0.91,
                       ix + radius * 0.91, iy + radius * 0.91),
                      outline=white + (165,), width=0.45)
        ring = radius * 0.69
        layer.ellipse((ix - ring, iy - ring, ix + ring, iy + ring),
                      outline=amber + (235,), width=0.9)

        # Fine radial iris fibres add a hand-crafted starburst at ASCII scale.
        for index in range(32):
            angle = (2.0 * math.pi * index / 32.0) + 0.035 * math.sin(index * 2.7)
            start = radius * (0.53 + 0.035 * (index % 3))
            end = radius * (0.88 + 0.035 * math.sin(index * 1.9))
            color = amber if index % 5 == 0 else white if index % 7 == 0 else iris
            alpha = 190 if color == amber else 145
            layer.line(((ix + math.cos(angle) * start, iy + math.sin(angle) * start),
                        (ix + math.cos(angle) * end, iy + math.sin(angle) * end)),
                       color + (alpha,), width=0.45 if index % 4 else 0.65)

        pupil_radius = radius * (0.29 if state.pupil == "small" else 0.38)
        if state.pupil == "heart":
            self._heart(layer, ix, iy + 0.6, pupil_radius * 1.75,
                        self.palette["rose"] + (255,))
        else:
            layer.ellipse((ix - pupil_radius, iy - pupil_radius,
                           ix + pupil_radius, iy + pupil_radius),
                          fill=self.palette["pupil"] + (255,))

        # Two large, rounded catchlights and one tiny secondary glint.
        glint = max(1.5, radius * 0.19)
        layer.ellipse((ix - radius * 0.37 - glint, iy - radius * 0.43 - glint,
                       ix - radius * 0.37 + glint, iy - radius * 0.43 + glint),
                      fill=white + (255,))
        small = max(0.9, glint * 0.58)
        layer.ellipse((ix + radius * 0.33 - small, iy + radius * 0.22 - small,
                       ix + radius * 0.33 + small, iy + radius * 0.22 + small),
                      fill=white + (250,))
        tiny = 0.8
        layer.ellipse((ix + radius * 0.48 - tiny, iy - radius * 0.21 - tiny,
                       ix + radius * 0.48 + tiny, iy - radius * 0.21 + tiny),
                      fill=white + (230,))

        # Soft eyelid arcs, kept graphic and deliberately free of texture.
        if state.lid == "happy":
            upper = ((cx - rx + 3, cy - 3), (cx - rx * 0.55, cy - ry * 0.72),
                     (cx + rx * 0.28, cy - ry * 0.72), (cx + rx - 3, cy - 1))
        elif state.lid == "sad":
            upper = ((cx - rx + 2, cy - ry * 0.23), (cx - rx * 0.55, cy - ry * 0.62),
                     (cx + rx * 0.36, cy - ry * 0.10), (cx + rx - 2, cy - ry * 0.26))
        else:
            upper = ((cx - rx + 2, cy - 2), (cx - rx * 0.55, cy - ry * 1.06),
                     (cx + rx * 0.52, cy - ry * 1.04), (cx + rx - 2, cy - 2))
        lower = ((cx - rx + 3, cy + 1), (cx - rx * 0.48, cy + ry * 1.08),
                 (cx + rx * 0.48, cy + ry * 1.08), (cx + rx - 3, cy + 1))
        layer.line(self._bezier(upper, 36), self.palette["ink"] + (245,), width=1.6)
        layer.line(self._bezier(lower, 34), self._shade("iris", 0.72) + (225,), width=1.0)

        self._draw_lashes(layer, cx, cy, rx, ry, int(design["lashes"]), state.lid)
        if state.brow:
            self._draw_brow(layer, cx, cy - ry - 3.0, rx, state.brow)
        if state.blush:
            cheek_y = cy + ry * 0.58
            cheek_radius = 2.0 if variant == "A" else 2.2
            for sign in (-1, 1):
                x = cx + sign * rx * 0.80
                layer.ellipse((x - cheek_radius, cheek_y - 1.0,
                               x + cheek_radius, cheek_y + 1.2), fill=rose + (225,))
        if state.tear:
            self._drop(layer, cx + rx * 0.77, cy + ry * 0.49,
                       4.0, self.palette["iris"] + (255,))
        if state.sweat:
            self._drop(layer, cx + rx * 0.91, cy - ry * 0.15,
                       2.9, white + (255,))
        return layer

    def _draw_closed_eye(self, layer: _VectorLayer, cx: float, cy: float,
                         rx: float, ry: float, lash_count: int,
                         state: EyeState) -> None:
        center_y = cy + 2.0
        curve = ((cx - rx * 0.80, center_y - 1.0),
                 (cx - rx * 0.30, center_y - 7.5),
                 (cx + rx * 0.30, center_y - 7.5),
                 (cx + rx * 0.80, center_y - 1.0))
        layer.line(self._bezier(curve, 38), self.palette["ink"] + (255,), width=4.0)
        layer.line(self._bezier(curve, 38), self.palette["iris"] + (255,), width=2.2)
        highlight = ((cx - rx * 0.32, center_y - 3.5),
                     (cx - rx * 0.18, center_y - 6.0),
                     (cx + rx * 0.18, center_y - 6.0),
                     (cx + rx * 0.32, center_y - 3.5))
        layer.line(self._bezier(highlight, 16), self.palette["amber"] + (230,), width=0.8)
        self._draw_lashes(layer, cx, center_y, rx, ry * 0.35,
                          lash_count, "closed")

    def _draw_lashes(self, layer: _VectorLayer, cx: float, cy: float, rx: float,
                     ry: float, count: int, lid: str) -> None:
        for index in range(count):
            if count == 1:
                fraction = 0.5
            else:
                fraction = 0.16 + 0.68 * index / (count - 1)
            x = cx - rx + 5.0 + fraction * (2.0 * rx - 10.0)
            nx = (x - cx) / max(1.0, rx)
            top = cy - ry * math.sqrt(max(0.0, 1.0 - nx * nx))
            length = (1.45 if count <= 2 else 1.8) if lid != "closed" else 1.75
            direction = -1.0 if nx < -0.08 else (1.0 if nx > 0.08 else 0.0)
            layer.line(((x, top + 0.7), (x + direction * 1.0,
                                         top - length)), self.palette["ink"] + (255,),
                       width=0.72 if count <= 2 else 0.92)

    def _draw_brow(self, layer: _VectorLayer, cx: float, y: float,
                   rx: float, style: str) -> None:
        if style == "raised":
            points = ((cx - rx * 0.30, y + 1), (cx - rx * 0.13, y - 2.5),
                      (cx + rx * 0.17, y - 2.5), (cx + rx * 0.30, y + 1))
        else:
            points = ((cx - rx * 0.31, y - 2), (cx - rx * 0.13, y + 1.2),
                      (cx + rx * 0.10, y + 1.7), (cx + rx * 0.29, y - 2))
        color = self.palette["amber"] if style == "raised" else self.palette["iris"]
        layer.line(self._bezier(points, 20), color + (255,), width=1.7)

    @staticmethod
    def _drop(layer: _VectorLayer, cx: float, cy: float, size: float,
              color: tuple[int, ...]) -> None:
        points = ((cx, cy - size), (cx + size * 0.68, cy + size * 0.25),
                  (cx, cy + size), (cx - size * 0.68, cy + size * 0.25))
        layer.polygon(points, color)
        layer.ellipse((cx - size * 0.58, cy - size * 0.35,
                       cx + size * 0.58, cy + size * 0.75), fill=color)

    @staticmethod
    def _heart(layer: _VectorLayer, cx: float, cy: float, size: float,
               color: tuple[int, ...]) -> None:
        upper_left = list(AsciiEyeMockupRenderer._bezier(
            ((cx, cy + size * 0.74), (cx - size * 1.05, cy + size * 0.05),
             (cx - size * 0.84, cy - size * 0.78), (cx - size * 0.29, cy - size * 0.43)), 12))
        upper_right = list(AsciiEyeMockupRenderer._bezier(
            ((cx - size * 0.29, cy - size * 0.43), (cx + size * 0.06, cy - size * 0.98),
             (cx + size * 1.02, cy - size * 0.63), (cx + size * 0.95, cy + size * 0.05)), 12))
        lower = list(AsciiEyeMockupRenderer._bezier(
            ((cx + size * 0.95, cy + size * 0.05), (cx + size * 0.70, cy + size * 0.38),
             (cx + size * 0.30, cy + size * 0.62), (cx, cy + size * 0.93)), 10))
        layer.polygon(upper_left + upper_right[1:] + lower[1:], color)

    def _background_stars(self, grid: dict[str, np.ndarray], xoff: int,
                          state_index: int) -> None:
        rng = np.random.default_rng(400 + state_index)
        for index in range(20):
            x = int(rng.integers(1, self.PANEL_WIDTH - 1))
            y = int(rng.integers(3, 42))
            if 9 <= x <= 18 and 8 <= y <= 24:
                continue
            if index in (2, 11):
                self._put(grid, xoff + x, y, "+", "sclera", 0)
            else:
                self._put(grid, xoff + x, y, ".", "iris", 0)

    @staticmethod
    def _put(grid: dict[str, np.ndarray], x: int, y: int, char: str,
             color_name: str, tone: int) -> None:
        if 0 <= y < grid["chars"].shape[0] and 0 <= x < grid["chars"].shape[1]:
            grid["chars"][y, x] = char
            grid["color_ids"][y, x] = grid["palette_names"].index(color_name)
            grid["tones"][y, x] = tone
            grid["coverage"][y, x] = 1.0

    def _blank_grid(self) -> dict[str, np.ndarray]:
        shape = (self.GRID_HEIGHT, self.GRID_WIDTH)
        return {
            "chars": np.full(shape, " ", dtype="<U1"),
            "color_ids": np.zeros(shape, dtype=np.uint8),
            "tones": np.zeros(shape, dtype=np.uint8),
            "coverage": np.zeros(shape, dtype=np.float32),
            "palette_names": self.palette_names,
        }

    @staticmethod
    def _overlay(grid: dict[str, np.ndarray], cells: tuple[np.ndarray, ...],
                 xoff: int) -> None:
        chars, color_ids, tones, coverage = cells
        height, width = chars.shape
        dest = np.s_[0:height, xoff:xoff + width]
        mask = coverage > 0.035
        grid["chars"][dest][mask] = chars[mask]
        grid["color_ids"][dest][mask] = color_ids[mask]
        grid["tones"][dest][mask] = tones[mask]
        grid["coverage"][dest][mask] = coverage[mask]

    def _draw_panel(self, grid: dict[str, np.ndarray],
                    state: EyeState, variant: str, state_index: int) -> None:
        xoff = 0 if variant == "A" else self.PANEL_WIDTH + 2
        scene = self._scene_layer(state_index)
        self._overlay(grid, scene.cells(self.palette, self.glyphs, self.glyph_density), xoff)
        self._background_stars(grid, xoff, state_index)
        eye = self._eye_layer(variant, state)
        self._overlay(grid, eye.cells(self.palette, self.glyphs, self.glyph_density), xoff)
        cx, cy = xoff + 39, 49
        design = VARIANTS[variant]
        rx = float(design["rx"])
        if state.hearts:
            self._put(grid, int(cx - rx * 0.84), int(cy - 15), "♥", "rose", 2)
            self._put(grid, int(cx + rx * 0.77), int(cy - 12), "♥", "rose", 1)
        if state.zzz:
            for offset, char in ((0, "z"), (3, "Z"), (7, "z")):
                self._put(grid, min(xoff + self.PANEL_WIDTH - 2, cx + 17 + offset),
                          max(8, cy - 22 - offset // 2), char, "sclera", 2)
        if state.sparkles:
            for dx, dy in ((-31, -23), (29, -19), (32, 17)):
                self._put(grid, cx + dx, cy + dy, "+", "amber", 2)
        if state.sweat:
            self._put(grid, min(xoff + self.PANEL_WIDTH - 2, cx + int(rx * 0.88)),
                      cy - 13, "!", "iris", 2)

        # Compact HUD labels belong to each full-scene design panel.
        label = VARIANTS[variant]["name"]
        self._text(grid, xoff + 2, 2, f"{variant} / {label}", "iris", 1, 74)
        self._text(grid, xoff + 2, 4, f"NOCTURNE / {state.label}", "sclera", 0, 74)
        self._text(grid, xoff + 2, 84, "HUMOR 50%   ENERGIA 80%", "sclera", 1, 74)
        self._text(grid, xoff + 2, 86, "SNN LOCAL  /  ESTAVEL", "iris", 0, 74)

    def _text(self, grid: dict[str, np.ndarray], x: int, y: int,
              text: str, color: str, tone: int, limit: int) -> None:
        for index, char in enumerate(text[:limit]):
            self._put(grid, x + index, y, char, color, tone)

    def _render_cells(self, grid: dict[str, np.ndarray]) -> Image.Image:
        rows, columns = grid["chars"].shape
        pixel_height, pixel_width = rows * self.CELL_HEIGHT, columns * self.CELL_WIDTH
        bg = self.palette["night"]
        output = np.empty((pixel_height, pixel_width, 3), dtype=np.uint8)
        output[:] = bg
        expanded_colors = self.shades[grid["color_ids"], grid["tones"]]
        expanded_colors = np.repeat(np.repeat(expanded_colors, self.CELL_HEIGHT, axis=0),
                                    self.CELL_WIDTH, axis=1)
        for char in np.unique(grid["chars"]):
            if char == " ":
                continue
            positions = grid["chars"] == char
            density_mask = self.glyph_masks.get(char)
            if density_mask is None:
                density_mask = self._mask_for_glyph(char)
                self.glyph_masks[char] = density_mask
            tiled_mask = np.broadcast_to(
                density_mask, (rows, columns, self.CELL_HEIGHT, self.CELL_WIDTH))
            pixel_glyph = tiled_mask.transpose(0, 2, 1, 3).reshape(pixel_height, pixel_width)
            pixel_positions = np.repeat(np.repeat(positions, self.CELL_HEIGHT, axis=0),
                                        self.CELL_WIDTH, axis=1)
            selected = pixel_glyph & pixel_positions
            output[selected] = expanded_colors[selected]
        return Image.fromarray(output, "RGB")

    def render(self, state: EyeState, state_index: int = 0) -> Image.Image:
        grid = self._blank_grid()
        self._draw_panel(grid, state, "A", state_index)
        # Narrow quiet divider between the two design alternatives.
        for y in range(1, self.GRID_HEIGHT - 1):
            self._put(grid, self.PANEL_WIDTH, y, "│", "iris", 0)
        self._draw_panel(grid, state, "B", state_index)
        self._text(grid, 47, 88, "O OLHO E UMA JANELA  /  MOCKUP ESTATICO",
                   "amber", 1, 70)
        return self._render_cells(grid)


def generate_mockups(output_dir: Path, palette_name: str = "nocturne") -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = AsciiEyeMockupRenderer(palette_name)
    paths: list[Path] = []
    for index, state in enumerate(STATES):
        image = renderer.render(state, index)
        path = output_dir / f"{state.key}.png"
        image.save(path, format="PNG", optimize=True)
        paths.append(path)
    return paths
