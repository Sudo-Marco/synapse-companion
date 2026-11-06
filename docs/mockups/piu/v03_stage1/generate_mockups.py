"""Create offline pixel-art review sheets for the Piu 0.3 visual proposal.

All character LODs are rasterized directly on their native grids. Only the
review-sheet enlargements use nearest-neighbour scaling. This script does not
write to application assets or import the running UI.
"""
from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[3]
PHOTO = PROJECT / "docs" / "mockups" / "piu" / "fundo_fotografico_cc0.jpg"
FONT_PATH = PROJECT / "src" / "synapse_pet" / "assets" / "fonts" / "silkscreen" / "Silkscreen-Bold.ttf"
SIZES = (48, 32, 20)
VIEWS = ("perfil", "frente", "costas")
PERIODS = ("madrugada", "manhã", "tarde", "entardecer", "noite")
PALETTE = {
    "outline_outer": "#4A3216", "outline_inner": "#8A5A2C",
    "outline_light": "#FFF3A0", "yellow_light": "#FFF08A",
    "yellow": "#FFD93B", "yellow_mid": "#F8C22B",
    "yellow_shadow": "#EAA823", "wing_light": "#F7B64D",
    "wing": "#D9820F", "wing_shadow": "#B96112",
    "beak_light": "#FFD36A", "beak": "#FF9B2F",
    "beak_shadow": "#D86B1D", "eye": "#30251C",
    "white": "#FFFFFF", "glint_blue": "#BFEFFF",
    "cheek": "#FF9DB5", "feet": "#E97825",
}


def color(key: str) -> tuple[int, int, int]:
    value = PALETTE.get(key, key).lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def scale(v: float, size: int) -> int:
    return int(round(v * size / 48))


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        return ImageFont.load_default()


def bbox(values: tuple[float, float, float, float], size: int,
         yscale: float = 1.0, yoffset: float = 0.0,
         xoffset: float = 0.0) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = values
    return (scale(x0 + xoffset, size), scale(24 + (y0 - 24) * yscale + yoffset, size),
            scale(x1 + xoffset, size), scale(24 + (y1 - 24) * yscale + yoffset, size))


def points(values: list[tuple[float, float]], size: int,
           yscale: float = 1.0, yoffset: float = 0.0,
           xoffset: float = 0.0) -> list[tuple[int, int]]:
    return [(scale(x + xoffset, size),
             scale(24 + (y - 24) * yscale + yoffset, size))
            for x, y in values]


def draw_sprite(size: int, view: str, pose: str = "idle", frame: int = 0
                ) -> tuple[Image.Image, Image.Image]:
    """Return an RGBA sprite and its filled silhouette mask, drawn at native size."""
    sway = (-2, 0, 2)[frame % 3] if pose.startswith("dance_sway") else 0
    if pose == "run":
        sway = (-1, 1, -1, 1)[frame % 4]
    hop_y = (1, -1, -3, 0)[frame % 4] if pose.startswith("dance_hop") else 0
    headbob = (0, -1, 1)[frame % 3] if pose.startswith("dance_head") else 0
    dy = 2 if pose in {"tired", "resting"} else 0
    if pose == "run":
        dy = (0, -1, 0, 1)[frame % 4]
    if pose == "caught":
        dy = -2
    if pose == "fall":
        dy = 5
    dy += hop_y
    xoff = sway
    yscale = 0.78 if pose == "fall" else 1.0
    if pose.startswith("dance_hop"):
        dy += -2 if frame in (1, 2) else 0
    if pose.startswith("dance_head"):
        dy += headbob

    mask = Image.new("L", (size, size), 0)
    m = ImageDraw.Draw(mask)
    def mell(box: tuple[float, float, float, float]) -> None:
        m.ellipse(bbox(box, size, yscale, dy, xoff), fill=255)
    def mpoly(poly: list[tuple[float, float]]) -> None:
        m.polygon(points(poly, size, yscale, dy, xoff), fill=255)

    # Body, head, crest, wings, tail, beak, and feet all contribute to the
    # single outside halo; details remain separate, lighter strokes.
    if view == "perfil":
        mell((11, 14, 37, 40)); mell((11, 5, 35, 29))
        mpoly([(14, 34), (23, 34), (18, 46), (12, 45), (8, 40)])
        mpoly([(18, 35), (26, 36), (24, 47), (18, 46), (14, 41)])
        mpoly([(24, 35), (30, 34), (38, 42), (34, 46), (26, 43)])
        mpoly([(15, 10), (13, 4), (20, 6), (24, 1), (27, 7), (31, 3), (34, 10)])
        mpoly([(17, 25), (8, 22), (5, 25), (7, 32), (16, 35)])
        mpoly([(19, 27), (9, 31), (6, 35), (11, 38), (20, 34)])
        mpoly([(31, 17), (46, 21), (42, 27), (31, 28)])
        mpoly([(15, 39), (24, 39), (25, 44), (17, 45)])
    elif view == "frente":
        mell((8, 15, 40, 41)); mell((7, 5, 41, 31))
        mpoly([(14, 34), (23, 35), (20, 47), (12, 46), (10, 40)])
        mpoly([(24, 35), (34, 34), (38, 40), (36, 46), (27, 47)])
        mpoly([(15, 9), (13, 4), (20, 6), (24, 1), (28, 6), (33, 3), (36, 10)])
        mpoly([(10, 22), (4, 20), (3, 25), (8, 32), (15, 34)])
        mpoly([(38, 22), (44, 20), (45, 25), (40, 32), (33, 34)])
        mpoly([(19, 24), (29, 24), (34, 28), (24, 33), (14, 28)])
        if pose == "caught":
            mpoly([(10, 22), (2, 16), (5, 11), (10, 15), (13, 21)])
            mpoly([(38, 22), (46, 16), (43, 11), (38, 15), (35, 21)])
        if pose == "listening":
            mpoly([(8, 23), (5, 16), (10, 14), (16, 22)])
    else:  # costas: obvious folded wings and three fanned tail feathers.
        mell((10, 13, 38, 42)); mell((11, 5, 37, 30))
        mpoly([(14, 9), (12, 3), (20, 5), (24, 0), (28, 6), (34, 3), (36, 10)])
        mpoly([(12, 18), (5, 19), (6, 28), (13, 34), (21, 30), (22, 23)])
        mpoly([(36, 18), (43, 19), (42, 28), (35, 34), (27, 30), (26, 23)])
        mpoly([(18, 34), (23, 30), (26, 35), (16, 47), (10, 44)])
        mpoly([(22, 34), (25, 30), (29, 34), (25, 47), (19, 47)])
        mpoly([(25, 35), (29, 31), (33, 34), (39, 44), (33, 47)])
        mpoly([(15, 39), (23, 39), (23, 45), (16, 46)])
        mpoly([(25, 39), (33, 39), (32, 46), (25, 45)])

    # Build the optional 1-pixel cream outline first, then colorized body parts.
    halo = mask.filter(ImageFilter.MaxFilter(3))
    halo_only = Image.fromarray(np.maximum(
        np.asarray(halo, dtype=np.int16) - np.asarray(mask, dtype=np.int16), 0
    ).astype(np.uint8), mode="L")
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste((*color("outline_light"), 255), (0, 0, size, size), halo_only)
    d = ImageDraw.Draw(out)
    stroke = max(1, round(size / 26))
    inner = color("outline_inner")
    outer = color("outline_outer")

    def ellipse(box: tuple[float, float, float, float], fill: str,
                outline: str = "outline_outer", width: int | None = None) -> None:
        d.ellipse(bbox(box, size, yscale, dy, xoff), fill=color(fill),
                  outline=color(outline), width=width or stroke)
    def polygon(poly: list[tuple[float, float]], fill: str,
                outline: str = "outline_outer", width: int | None = None) -> None:
        xy = points(poly, size, yscale, dy, xoff)
        d.polygon(xy, fill=color(fill))
        d.line(xy + [xy[0]], fill=color(outline), width=width or stroke,
               joint="curve")
    def line(coords: list[tuple[float, float]], fill: str = "outline_inner",
             width: int | None = None) -> None:
        d.line(points(coords, size, yscale, dy, xoff), fill=color(fill),
               width=width or max(1, round(size / 40)), joint="curve")
    def rect(box: tuple[float, float, float, float], fill: str) -> None:
        d.rectangle(bbox(box, size, yscale, dy, xoff), fill=color(fill))

    if view == "perfil":
        ellipse((11, 14, 37, 40), "yellow_mid")
        ellipse((11, 5, 35, 29), "yellow")
        # Warm underside shadow and a broad head highlight follow the palette ramp.
        ellipse((15, 29, 34, 38), "yellow_shadow", outline="yellow_shadow", width=1)
        ellipse((14, 7, 26, 14), "yellow_light", outline="yellow_light", width=1)
        polygon([(14, 34), (23, 34), (18, 46), (12, 45), (8, 40)], "wing")
        polygon([(18, 35), (26, 36), (24, 47), (18, 46), (14, 41)], "wing_light")
        polygon([(24, 35), (30, 34), (38, 42), (34, 46), (26, 43)], "wing")
        polygon([(15, 10), (13, 4), (20, 6), (24, 1), (27, 7), (31, 3), (34, 10)], "yellow_light")
        polygon([(17, 25), (8, 22), (5, 25), (7, 32), (16, 35)], "wing")
        polygon([(19, 27), (9, 31), (6, 35), (11, 38), (20, 34)], "wing_shadow")
        # Clear feather tips, three tail feathers, and a thin mouth seam.
        for pts in [[(8, 26), (12, 28), (15, 32)], [(9, 33), (13, 33), (17, 35)],
                    [(16, 37), (17, 42), (16, 44)], [(23, 38), (22, 43), (21, 45)],
                    [(31, 37), (34, 41), (33, 44)]]:
            line(pts, "yellow_light", 1)
        polygon([(31, 17), (46, 21), (42, 27), (31, 28)], "beak")
        line([(34, 25), (43, 25)], "beak_shadow", 1)
        ellipse((25, 14, 31, 21), "eye", outline="eye", width=1)
        ellipse((26, 14, 28, 17), "white", outline="white", width=1)
        ellipse((28, 17, 29, 18), "glint_blue", outline="glint_blue", width=1)
        ellipse((19, 28, 24, 31), "cheek", outline="cheek", width=1)
        # Side wing outer/body separation stays a fine, warm line.
        line([(11, 22), (16, 24), (19, 30)], "outline_inner", 1)
        line([(18, 33), (20, 35), (22, 33)], "yellow_light", 1)
    elif view == "frente":
        ellipse((8, 15, 40, 41), "yellow_mid")
        ellipse((7, 5, 41, 31), "yellow")
        ellipse((13, 7, 35, 15), "yellow_light", outline="yellow_light", width=1)
        ellipse((13, 29, 35, 39), "yellow_shadow", outline="yellow_shadow", width=1)
        polygon([(15, 9), (13, 4), (20, 6), (24, 1), (28, 6), (33, 3), (36, 10)], "yellow_light")
        polygon([(10, 22), (4, 20), (3, 25), (8, 32), (15, 34)], "wing")
        polygon([(38, 22), (44, 20), (45, 25), (40, 32), (33, 34)], "wing")
        for x in (8, 37):
            line([(x, 25), (x + (3 if x < 20 else -3), 28),
                  (x + (5 if x < 20 else -5), 31)], "wing_light", 1)
        # Face stays friendly at all LODs: broad glints, no sharp angry brow.
        eye_shift = -1 if pose == "thinking" else 0
        if pose in {"resting"}:
            line([(14, 20), (18, 21), (21, 20)], "eye", max(1, stroke))
            line([(27, 20), (30, 21), (34, 20)], "eye", max(1, stroke))
        elif pose == "tired":
            ellipse((13, 17, 21, 25), "eye", outline="eye", width=1)
            ellipse((27, 17, 35, 25), "eye", outline="eye", width=1)
            line([(13, 18), (21, 20)], "yellow_shadow", 2)
            line([(27, 20), (35, 18)], "yellow_shadow", 2)
        else:
            for x in (14, 27):
                ellipse((x, 16 + eye_shift, x + 8, 25 + eye_shift), "eye", outline="eye", width=1)
                ellipse((x + 2, 17 + eye_shift, x + 5, 21 + eye_shift), "white", outline="white", width=1)
                ellipse((x + 5, 21 + eye_shift, x + 6, 22 + eye_shift), "glint_blue", outline="glint_blue", width=1)
        ellipse((5, 27, 13, 31), "cheek", outline="cheek", width=1)
        ellipse((35, 27, 43, 31), "cheek", outline="cheek", width=1)
        polygon([(19, 24), (29, 24), (34, 28), (24, 33), (14, 28)], "beak")
        line([(17, 29), (24, 30), (31, 29)], "beak_shadow", 1)
        if pose == "listening":
            polygon([(8, 23), (5, 16), (10, 14), (16, 22)], "wing_light", "outline_inner", 1)
            line([(8, 18), (12, 21)], "yellow_light", 1)
        if pose == "caught":
            polygon([(10, 22), (2, 16), (5, 11), (10, 15), (13, 21)], "wing_light", "outline_inner", 1)
            polygon([(38, 22), (46, 16), (43, 11), (38, 15), (35, 21)], "wing_light", "outline_inner", 1)
        # Small feather marks add breast texture without turning it into noise.
        for x in (21, 24, 27):
            line([(x, 35), (x+1, 37)], "yellow_light", 1)
    else:
        # Back: pale nape, large but softly shaded folded wings, 3 feather fan.
        ellipse((10, 13, 38, 42), "yellow_mid")
        ellipse((11, 5, 37, 30), "yellow")
        ellipse((15, 7, 30, 15), "yellow_light", outline="yellow_light", width=1)
        polygon([(14, 9), (12, 3), (20, 5), (24, 0), (28, 6), (34, 3), (36, 10)], "yellow_light")
        polygon([(12, 18), (5, 19), (6, 28), (13, 34), (21, 30), (22, 23)], "wing")
        polygon([(36, 18), (43, 19), (42, 28), (35, 34), (27, 30), (26, 23)], "wing")
        for xoff_wing in (0, 1):
            for i in range(3):
                x = 8 + i * 3 if xoff_wing == 0 else 40 - i * 3
                sign = 1 if xoff_wing == 0 else -1
                line([(x, 22 + i * 2), (x + 3 * sign, 26 + i * 2),
                      (x + 5 * sign, 29 + i)], "yellow_light", 1)
        # A bright, clear tail fan replaces the previous dark central blotches.
        polygon([(18, 34), (23, 30), (26, 35), (16, 47), (10, 44)], "wing")
        polygon([(22, 34), (25, 30), (29, 34), (25, 47), (19, 47)], "wing_light")
        polygon([(25, 35), (29, 31), (33, 34), (39, 44), (33, 47)], "wing")
        line([(17, 39), (16, 44), (14, 44)], "yellow_light", 1)
        line([(23, 37), (22, 44), (21, 46)], "yellow_light", 1)
        line([(29, 37), (34, 43), (36, 43)], "yellow_light", 1)

    # The feet show three toes when space allows, and point down in the caught pose.
    foot_y = 44 if pose == "caught" else 44
    foot_color = "feet"
    if pose == "resting":
        line([(14, 41), (20, 42), (25, 42), (30, 41)], foot_color, 2)
    elif pose == "run":
        phase = frame % 4
        left_step = (-3, -1, 2, 3)[phase]
        right_step = (3, 1, -2, -3)[phase]
        for center, step in ((18, left_step), (30, right_step)):
            line([(center, 37), (center + step, 43),
                  (center + step + (3 if step <= 0 else 1), 44)], foot_color, 2)
            for toe in (-2, 0, 2):
                line([(center + step, 43), (center + step + toe, 45)], foot_color, 1)
    elif view != "costas":
        for center in ((18, foot_y), (30, foot_y)):
            line([(center[0], center[1] - 5), (center[0], center[1])], foot_color, 2)
            for toe in (-3, 0, 3):
                line([(center[0], center[1] - 1),
                      (center[0] + toe, center[1] + 1)], foot_color, 1)
    else:
        for center in (18, 30):
            line([(center, foot_y - 5), (center, foot_y)], foot_color, 2)
            for toe in (-3, 0, 3):
                line([(center, foot_y - 1), (center + toe, foot_y + 1)], foot_color, 1)

    # Mood/action overlays are only small accents; the silhouette remains soft.
    if pose == "thinking":
        for i, r in enumerate((1, 1, 2)):
            xx = 39 + i * 3
            yy = 11 - i * 3
            ellipse((xx - r, yy - r, xx + r, yy + r), "yellow_light",
                    outline="outline_inner", width=1)
        line([(26, 14), (29, 12)], "outline_inner", 1)
    if pose == "tired":
        line([(31, 32), (35, 34), (39, 33)], "beak_shadow", 1)
        if view == "perfil":
            line([(34, 23), (39, 25), (43, 23)], "beak_shadow", 2)
            line([(25, 15), (30, 17)], "yellow_shadow", 2)
        elif view == "frente":
            polygon([(19, 29), (29, 29), (27, 33), (21, 33)], "beak_shadow", "beak_shadow", 1)
        for i in range(3):
            line([(38 + i * 2, 29 + i), (40 + i * 2, 27 + i)], "glint_blue", 1)
    if pose.startswith("dance"):
        beat_x = 4 + (frame % 2) * 2
        line([(beat_x, 13), (beat_x + 2, 10)], "cheek", 1)
        if pose.startswith("dance_hop"):
            for i in range(2):
                line([(6 + i * 4, 39), (4 + i * 4, 43)], "yellow_light", 1)
    if pose == "caught":
        line([(17, 38), (15, 46)], "feet", 2)
        line([(30, 38), (32, 46)], "feet", 2)
    if pose == "fall":
        for x, y in ((6, 10), (40, 9), (42, 33)):
            line([(x - 1, y), (x + 1, y)], "beak_light", 1)
            line([(x, y - 1), (x, y + 1)], "beak_light", 1)
    return out, mask


def scene(period: str) -> Image.Image:
    """Draw a multi-plane 640x240 landscape with deterministic decorative life."""
    w, h = 640, 240
    schemes = {
        "madrugada": (("#26345D", "#48547A", "#73647E"), "#FFE0A0", True),
        "manhã": (("#71CBE8", "#A8E2E9", "#D8EDC6"), "#FFF0A3", False),
        "tarde": (("#55B8E4", "#A3DBE4", "#E5E4B7"), "#FFE375", False),
        "entardecer": (("#D96F78", "#F4A176", "#FFD28B"), "#FFF0C0", False),
        "noite": (("#101E42", "#283C68", "#4A5C78"), "#DDE8FF", True),
    }
    sky, horizon, low = schemes[period][0]
    night = schemes[period][2]
    im = Image.new("RGB", (w, h), sky)
    d = ImageDraw.Draw(im)
    # Five broad smooth steps keep a pixel-art sky gradient; subtle noise stays
    # only in the sky and never touches the character or foreground silhouettes.
    for i in range(5):
        y0, y1 = i * 22, (i + 1) * 22
        mix = i / 5
        c0 = np.array(color(sky)); c1 = np.array(color(horizon))
        col = tuple(np.round(c0 * (1 - mix) + c1 * mix).astype(int))
        d.rectangle((0, y0, w, y1), fill=col)
    rng = random.Random(2200 + PERIODS.index(period))
    for _ in range(180):
        x, y = rng.randrange(w), rng.randrange(110)
        if rng.random() < 0.42:
            base = np.array(im.getpixel((x, y)), dtype=int)
            delta = rng.choice((-5, -3, 3, 5))
            d.point((x, y), fill=tuple(np.clip(base + delta, 0, 255)))
    sun_x = (110, 180, 455, 520, 540)[PERIODS.index(period)]
    sun_y = (48, 42, 40, 66, 46)[PERIODS.index(period)]
    orb = schemes[period][1]
    for rad, alpha_col in ((32, "#FFEAD033"), (23, "#FFF0B066")):
        d.ellipse((sun_x-rad, sun_y-rad, sun_x+rad, sun_y+rad), fill=alpha_col[:7])
    d.ellipse((sun_x-13, sun_y-13, sun_x+13, sun_y+13), fill=orb)
    if period in {"madrugada", "noite"}:
        for _ in range(42):
            x, y = rng.randrange(w), rng.randrange(100)
            r = 2 if rng.random() < 0.20 else 1
            d.rectangle((x, y, x+r, y+r), fill="#F7F1D2" if r == 2 else "#CAD5F3")
    # Two cloud silhouettes: pillowy daytime clouds and stretched dusk bands.
    cloud = "#E9F6F1" if not night else "#7388B0"
    def cloud_shape(x: int, y: int, stretched: bool = False) -> None:
        k = 1.3 if stretched else 1.0
        d.rectangle((x+10, y+8, x+65*k, y+22), fill=cloud)
        for cx, cy, r in ((x+18, y+8, 12), (x+38, y+1, 16), (x+60, y+8, 11)):
            d.ellipse((cx-r*k, cy-r, cx+r*k, cy+r), fill=cloud)
    cloud_shape(48, 36)
    cloud_shape(420, 83, True)
    # Three distant landscape planes.
    d.polygon([(0, 137), (85, 112), (170, 136), (280, 108), (386, 136),
               (505, 111), (640, 137), (640, 240), (0, 240)], fill="#89B684" if not night else "#425C68")
    d.polygon([(0, 158), (110, 132), (205, 158), (325, 126), (430, 160),
               (535, 137), (640, 165), (640, 240), (0, 240)], fill="#69A66B" if not night else "#334F61")
    d.polygon([(0, 186), (130, 161), (270, 190), (380, 159), (510, 188),
               (640, 165), (640, 240), (0, 240)], fill="#4F8C5D" if not night else "#263F51")
    # A creek and short reflected streaks run behind the foreground flowers.
    d.polygon([(0, 202), (66, 194), (130, 203), (224, 194), (310, 203),
               (400, 194), (520, 205), (640, 196), (640, 219), (0, 220)],
              fill="#8CCCD0" if not night else "#3E7890")
    for i in range(18):
        x = rng.randrange(w-20); y = rng.randrange(198, 218)
        d.line((x, y, x+rng.randrange(5, 18), y), fill="#D2F4E9" if not night else "#83B7C4", width=1)
    # Distant house, tree canopy, trunk and a two-height fence.
    house_x = 510
    d.rectangle((house_x, 126, house_x+42, 154), fill="#EBC58B" if not night else "#9B8B84")
    d.polygon([(house_x-6, 128), (house_x+21, 108), (house_x+49, 128)], fill="#8E5741" if not night else "#534B63")
    d.rectangle((house_x+7, 137, house_x+15, 147), fill="#83A9A0")
    d.rectangle((house_x+27, 137, house_x+36, 154), fill="#845A3C")
    d.rectangle((565, 107, 570, 170), fill="#79553A")
    for cx, cy, r in ((552, 108, 21), (578, 103, 25), (596, 115, 17)):
        d.ellipse((cx-r, cy-r, cx+r, cy+r), fill="#4F8C5D" if not night else "#355C58")
    for x in range(0, w, 48):
        d.rectangle((x, 178, x+3, 211), fill="#9C704B")
        d.rectangle((x-1, 184, x+20, 187), fill="#C4935B")
        d.rectangle((x+9, 197, x+31, 200), fill="#A77B4E")
    # Foreground grass tufts and three distinct flower silhouettes.
    d.rectangle((0, 220, w, h), fill="#437D4B" if not night else "#203D3B")
    for _ in range(85):
        x = rng.randrange(w); y = rng.randrange(218, 240)
        d.line((x, y+4, x+rng.choice((-2, 0, 2)), y), fill="#75A852" if not night else "#426A59", width=1)
    flower_colors = ("#F7D7C8", "#FFF1A5", "#ECA6BC")
    for i, x in enumerate(range(22, w-10, 73)):
        y = rng.randrange(220, 234)
        kind = i % 3
        d.line((x, y+11, x, y+2), fill="#76A854" if not night else "#54775E", width=2)
        if kind == 0:
            for dx, dy0 in ((-3, 0), (3, 0), (0, -3), (0, 3)):
                d.rectangle((x+dx-1, y+dy0-1, x+dx+1, y+dy0+1), fill=flower_colors[kind])
        elif kind == 1:
            d.ellipse((x-4, y-4, x+4, y+4), fill=flower_colors[kind])
        else:
            d.rectangle((x-3, y-4, x+3, y+3), fill=flower_colors[kind])
        d.point((x, y), fill="#EBA43D")
    # The same LOD is drawn directly at 48x48: 20% of the scene height.
    bird, _ = draw_sprite(48, "perfil", "idle")
    im_rgba = im.convert("RGBA")
    shadow = Image.new("RGBA", im_rgba.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse((106, 211, 173, 225), fill=(26, 45, 37, 92))
    im_rgba.alpha_composite(shadow)
    im_rgba.alpha_composite(bird, (116, 164))
    d = ImageDraw.Draw(im_rgba)
    if period in {"madrugada", "noite"}:
        for _ in range(14):
            x, y = rng.randrange(w), rng.randrange(120, 220)
            r = 1 if rng.random() < 0.7 else 2
            d.ellipse((x-r, y-r, x+r, y+r), fill="#E8D78D")
    else:
        for x, y in ((206, 96), (235, 89), (495, 142)):
            # Tiny, readable butterflies rather than anonymous dots.
            wing = "#FFE5A8" if period != "entardecer" else "#FFDFC0"
            d.ellipse((x-5, y-3, x-1, y+1), fill=wing)
            d.ellipse((x+1, y-3, x+5, y+1), fill=wing)
            d.line((x, y-2, x, y+3), fill="#A86F49", width=1)
            d.line((x, y-2, x-2, y-5), fill="#A86F49", width=1)
            d.line((x, y-2, x+2, y-5), fill="#A86F49", width=1)
    return im_rgba.convert("RGB")


def contact_sheet() -> None:
    rows = []
    for view in VIEWS:
        row = []
        for size in SIZES:
            row.append((draw_sprite(size, view)[0], f"{view.upper()} · {size}px"))
        rows.append(row)
    for factor in (1, 4):
        max_art = 48 * factor
        cw, ch = max(156, max_art + 32), max(105, max_art + 42)
        sheet = Image.new("RGB", (cw * 3 + 40, ch * 3 + 74), "#24365E")
        d = ImageDraw.Draw(sheet)
        d.text((18, 12), f"PIU · VISTAS E LOD · {factor}X", font=font(16), fill="#FFF3A0")
        for r, row in enumerate(rows):
            for c, (sprite, label) in enumerate(row):
                x, y = 10 + c*cw, 48 + r*ch
                d.rectangle((x, y, x+cw-3, y+ch-3), fill="#1B2D4F", outline="#F4D98B", width=1)
                scale_factor = factor
                scaled = sprite.resize((sprite.width*scale_factor, sprite.height*scale_factor), Image.Resampling.NEAREST)
                sheet.paste(scaled, (x+(cw-scaled.width)//2, y+4), scaled)
                d.text((x+5, y+ch-23), label, font=font(12), fill="#FFF3A0")
        sheet.save(ROOT / f"vistas_lod_{factor}x.png", optimize=True)


POSES = [
    ("pensando", "frente"), ("cansado", "perfil"),
    ("descansando", "frente"), ("ouvindo", "frente"),
    ("dança balanço A", "frente"), ("dança balanço B", "frente"),
    ("dança balanço C", "frente"), ("dança pulinho A", "frente"),
    ("dança pulinho B", "frente"), ("dança pulinho C", "frente"),
    ("dança pulinho D", "frente"), ("dança cabeça A", "perfil"),
    ("dança cabeça B", "perfil"), ("dança cabeça C", "perfil"),
    ("pego no alto", "frente"), ("queda / pancada", "perfil"),
    ("espiando", "frente"),
]


def pose_sheets() -> None:
    for factor in (1, 4):
        cw, ch = 238, 240 if factor == 4 else 144
        columns = 4
        rows = math.ceil(len(POSES) / columns)
        sheet = Image.new("RGB", (columns*cw+24, rows*ch+64), "#24365E")
        d = ImageDraw.Draw(sheet)
        d.text((14, 12), f"PIU · EXPRESSÕES E AÇÕES · {factor}X", font=font(16), fill="#FFF3A0")
        for idx, (label, view) in enumerate(POSES):
            x, y = 8+(idx%columns)*cw, 46+(idx//columns)*ch
            d.rectangle((x, y, x+cw-4, y+ch-4), fill="#1B2D4F", outline="#F4D98B", width=1)
            pose_key = {
                "pensando": "thinking", "cansado": "tired",
                "descansando": "resting", "ouvindo": "listening",
                "dança balanço A": "dance_sway", "dança balanço B": "dance_sway",
                "dança balanço C": "dance_sway", "dança pulinho A": "dance_hop",
                "dança pulinho B": "dance_hop", "dança pulinho C": "dance_hop",
                "dança pulinho D": "dance_hop", "dança cabeça A": "dance_head",
                "dança cabeça B": "dance_head", "dança cabeça C": "dance_head",
                "pego no alto": "caught", "queda / pancada": "fall",
                "espiando": "peek",
            }[label]
            frame = idx
            sprite, _ = draw_sprite(48, view, pose_key, frame)
            enlarge = factor
            if label == "espiando":
                # A screen edge hides the left half; the Piu leans out beyond it.
                d_sprite = ImageDraw.Draw(sprite)
                d_sprite.rectangle((0, 0, 18, 47), fill=(27, 45, 79, 255))
                d_sprite.line((19, 0, 19, 47), fill=color("outline_light") + (255,), width=1)
            scaled = sprite.resize((48*enlarge, 48*enlarge), Image.Resampling.NEAREST)
            sheet.paste(scaled, (x+(cw-scaled.width)//2, y+5), scaled)
            d.text((x+8, y+ch-29), label.upper(), font=font(12), fill="#FFF3A0")
        sheet.save(ROOT / f"poses_novas_{factor}x.png", optimize=True)


BACKGROUNDS = ("preto", "branco", "cinza_medio", "azul_escuro", "xadrez_ruido", "foto")


def background(name: str, size: tuple[int, int]) -> Image.Image:
    w, h = size
    if name == "preto":
        return Image.new("RGB", size, "#05070B")
    if name == "branco":
        return Image.new("RGB", size, "#FFFFFF")
    if name == "cinza_medio":
        return Image.new("RGB", size, "#808080")
    if name == "azul_escuro":
        return Image.new("RGB", size, "#132746")
    if name == "foto" and PHOTO.exists():
        with Image.open(PHOTO) as source:
            return source.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    im = Image.new("RGB", size, "#707C8B")
    d = ImageDraw.Draw(im)
    rng = random.Random(8192)
    tile = 12
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            base = ((x//tile + y//tile) % 2 == 0)
            v = (116 if base else 73) + rng.randint(-18, 18)
            rgb = (v, min(255, v+5), min(255, v+17)) if base else (v, v+8, v+3)
            d.rectangle((x, y, x+tile-1, y+tile-1), fill=rgb)
    for _ in range(w*h//14):
        x, y = rng.randrange(w), rng.randrange(h)
        c = im.getpixel((x,y)); delta = rng.choice((-20,-12,12,20))
        d.point((x,y), fill=tuple(max(0,min(255,k+delta)) for k in c))
    return im


def luminance(rgb: tuple[int, int, int]) -> float:
    values = []
    for channel in rgb:
        x = channel / 255
        values.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return 0.2126*values[0] + 0.7152*values[1] + 0.0722*values[2]


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb)+0.05)/(min(la, lb)+0.05)


def legibility_sheets() -> None:
    view_size = [(view, size) for view in VIEWS for size in SIZES]
    cell_w = 214
    for factor in (2, 3, 4):
        cell_h = factor*48 + 42
        width = cell_w*len(view_size)+16
        height = len(BACKGROUNDS)*(cell_h+27)+50
        sheet = Image.new("RGB", (width, height), "#101923")
        d = ImageDraw.Draw(sheet)
        d.text((12, 10), f"CONTORNO DUPLO · TESTE DE LEITURA · ESCALA {factor}X", font=font(15), fill="#FFF3A0")
        for bidx, bgname in enumerate(BACKGROUNDS):
            y0 = 38 + bidx*(cell_h+27)
            d.text((8, y0+5), bgname.upper(), font=font(11), fill="#FFFFFF")
            for idx, (view, size) in enumerate(view_size):
                x = idx*cell_w+16
                tile_bg = background(bgname, (cell_w-4, cell_h))
                sprite, _mask = draw_sprite(size, view)
                enlarged = sprite.resize((size*factor, size*factor), Image.Resampling.NEAREST)
                tile = tile_bg.copy().convert("RGBA")
                tile.alpha_composite(enlarged, ((tile.width-enlarged.width)//2, 2))
                sheet.paste(tile.convert("RGB"), (x, y0+24))
                d.text((x+5, y0+cell_h+4), f"{view[:3].upper()} {size}px", font=font(9), fill="#E8EDFA")
        sheet.save(ROOT / f"legibilidade_{factor}x.png", optimize=True)

    # Worst sampled paired-outline contrast across all six backgrounds and the
    # three native LODs, so the ratio is not only a solid-color swatch score.
    rows = []
    dark, light = color("outline_outer"), color("outline_light")
    for bgname in BACKGROUNDS:
        ratios = []
        for view in VIEWS:
            for size in SIZES:
                sprite, mask = draw_sprite(size, view)
                # Use the one-pixel perimeter beneath the sprite halo as local
                # background samples; at every point both adjacent outline
                # colors are visible, and the stronger edge supplies contrast.
                expanded = mask.filter(ImageFilter.MaxFilter(3))
                ring = np.asarray(expanded) > 0
                interior = np.asarray(mask) > 0
                ring &= ~interior
                tile = background(bgname, (size+8, size+8))
                # Sample backgrounds at the exact native perimeter positions.
                values = np.asarray(tile)[4:4+size, 4:4+size]
                for rgb in values[ring]:
                    sample = tuple(int(v) for v in rgb)
                    ratios.append(max(contrast(dark, sample), contrast(light, sample)))
        rows.append({"background": bgname, "min_paired_outline_ratio": round(min(ratios), 2),
                     "mean_paired_outline_ratio": round(float(np.mean(ratios)), 2),
                     "pass_3_to_1": min(ratios) >= 3.0})
    with (ROOT / "contraste_legibilidade.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)


def save_scenes() -> None:
    scenes = [(period, scene(period)) for period in PERIODS]
    for period, im in scenes:
        key = period.replace("ã", "a").replace("é", "e")
        im.save(ROOT / f"ambiente_{key}_1x.png", optimize=True)
        im.resize((im.width*3, im.height*3), Image.Resampling.NEAREST).save(
            ROOT / f"ambiente_{key}_3x.png", optimize=True)
    for factor in (1, 3):
        cell_w, cell_h = 644*factor, 270*factor
        sheet = Image.new("RGB", (cell_w*2+18, cell_h*3+24), "#17233A")
        d = ImageDraw.Draw(sheet)
        for i, (period, im) in enumerate(scenes):
            x, y = 6+(i%2)*cell_w, 6+(i//2)*cell_h
            shown = im if factor == 1 else im.resize((im.width*factor, im.height*factor), Image.Resampling.NEAREST)
            sheet.paste(shown, (x, y+22))
            d.text((x+5, y+3), period.upper(), font=font(14*factor), fill="#FFF3A0")
        sheet.save(ROOT / f"ambientes_5_periodos_{factor}x.png", optimize=True)


def write_manifest() -> None:
    data = {
        "schema_version": 1,
        "purpose": "offline_visual_review_only_not_integrated",
        "native_lod_px": {"perto": 48, "medio": 32, "longe": 20},
        "views": list(VIEWS),
        "depth_views": [f"{view}_{size}px" for view in VIEWS for size in SIZES],
        "special_poses": [{"label": label, "view": view, "native_size_px": 48,
                           "pivot": [24, 44], "hitbox": [2, 2, 46, 46]}
                          for label, view in POSES],
        "dance_cycles": {"balanco": 3, "pulinho": 4, "cabecada": 3,
                         "frame_duration_ms": 120, "loop": True},
        "periods": list(PERIODS),
        "scene_size_px": [640, 240],
        "piu_scene_height_fraction": 0.20,
        "enlargement": "nearest-neighbor only",
        "palette": PALETTE,
    }
    (ROOT / "inventario_v03_stage1.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_native_sprites() -> None:
    """Write editable, transparent source frames; atlas packing is a later step."""
    output = ROOT / "sprites"
    output.mkdir(exist_ok=True)
    for view in VIEWS:
        for size in SIZES:
            sprite, _ = draw_sprite(size, view, "idle")
            sprite.save(output / f"{view}_{size}_idle.png", optimize=True)
            for phase in range(4):
                sprite, _ = draw_sprite(size, view, "run", phase)
                sprite.save(output / f"{view}_{size}_run_{phase:02d}.png", optimize=True)
    mappings = {
        "pensando": ("frente", "thinking", 1),
        "cansado_perfil": ("perfil", "tired", 1),
        "cansado_frente": ("frente", "tired", 1),
        "descansando": ("frente", "resting", 1),
        "ouvindo": ("frente", "listening", 1),
        "pego_no_alto": ("frente", "caught", 1),
        "queda_pancada": ("perfil", "fall", 1),
        "espiando": ("frente", "peek", 1),
    }
    for label, (view, pose, count) in mappings.items():
        for phase in range(count):
            sprite, _ = draw_sprite(48, view, pose, phase)
            sprite.save(output / f"pose_{label}_{phase:02d}.png", optimize=True)
    for label, pose, count in (("danca_balanco", "dance_sway", 3),
                               ("danca_pulinho", "dance_hop", 4),
                               ("danca_cabecada", "dance_head", 3)):
        view = "perfil" if label == "danca_cabecada" else "frente"
        for phase in range(count):
            sprite, _ = draw_sprite(48, view, pose, phase)
            sprite.save(output / f"pose_{label}_{phase:02d}.png", optimize=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    contact_sheet()
    pose_sheets()
    save_scenes()
    legibility_sheets()
    write_manifest()
    export_native_sprites()
    print(f"Mockups V0.3 Etapa 1 salvos em: {ROOT}")
    print((ROOT / "contraste_legibilidade.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
