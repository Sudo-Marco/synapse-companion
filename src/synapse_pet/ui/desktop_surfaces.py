from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtGui import QImage


@dataclass(frozen=True, slots=True)
class VisualPlatform:
    """A short-lived, locally detected high-contrast ledge on the desktop."""

    left: int
    top: int
    right: int


def _rgb_array(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height = converted.width(), converted.height()
    pointer = converted.constBits()
    try:
        data = memoryview(pointer).tobytes()
    except TypeError:
        data = pointer.tobytes()
    rows = np.frombuffer(data, dtype=np.uint8).reshape(
        height, converted.bytesPerLine())
    return rows[:, :width * 3].reshape(height, width, 3)


def detect_visual_platform(image: QImage, reference_x: int,
                           reference_y: int) -> VisualPlatform | None:
    """Find a large, contrasty shape under a dropped pet without OCR.

    The image is analyzed only in memory. This looks for a broad connected
    horizontal band near the requested foot position; it does not identify or
    retain text, logos, applications, or screenshots.
    """
    if image.isNull() or image.width() < 48 or image.height() < 32:
        return None
    rgb = _rgb_array(image)
    height, width, _ = rgb.shape
    x = max(0, min(width - 1, int(reference_x)))
    y = max(0, min(height - 1, int(reference_y)))

    border = np.concatenate((rgb[0, :, :], rgb[-1, :, :],
                             rgb[:, 0, :], rgb[:, -1, :]), axis=0)
    background = np.median(border, axis=0)
    difference = np.max(np.abs(rgb.astype(np.int16) - background), axis=2)
    luminance = (rgb[:, :, 0].astype(np.int16) * 3
                 + rgb[:, :, 1].astype(np.int16) * 6
                 + rgb[:, :, 2].astype(np.int16)) // 10
    bg_luminance = int((background[0] * 3 + background[1] * 6
                        + background[2]) // 10)
    mask = (difference >= 48) | (np.abs(luminance - bg_luminance) >= 35)

    band_left, band_right = max(0, x - 96), min(width, x + 97)
    band_width = band_right - band_left
    first_row = max(0, y - min(112, height - 12))
    last_row = min(height, y + 10)
    row_counts = mask[first_row:last_row, band_left:band_right].sum(axis=1)
    threshold = max(6, round(band_width * 0.035))
    active_rows = row_counts >= threshold

    # Merge tiny gaps caused by antialiasing and holes in letters/logos.
    for row in range(1, max(1, len(active_rows) - 2)):
        if active_rows[row - 1] and active_rows[row + 1]:
            active_rows[row] = True
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(active_rows):
        if active and start is None:
            start = index
        elif not active and start is not None:
            runs.append((first_row + start, first_row + index - 1))
            start = None
    if start is not None:
        runs.append((first_row + start, first_row + len(active_rows) - 1))

    candidates = [(top, bottom) for top, bottom in runs
                  if bottom - top + 1 >= 6
                  and top <= y + 4 and bottom >= y - 108]
    if not candidates:
        return None
    top, bottom = max(candidates, key=lambda run: run[1])

    component = mask[top:bottom + 1, band_left:band_right]
    column_counts = component.sum(axis=0)
    col_threshold = max(1, round((bottom - top + 1) * 0.025))
    active_columns = column_counts >= col_threshold
    # Treat the spaces inside a short word/logo as one usable ledge.
    active_indices = np.flatnonzero(active_columns)
    if active_indices.size == 0:
        return None
    groups: list[tuple[int, int]] = []
    group_start = previous = int(active_indices[0])
    for value in active_indices[1:]:
        current = int(value)
        if current - previous > 17:
            groups.append((group_start, previous))
            group_start = current
        previous = current
    groups.append((group_start, previous))
    local_reference = x - band_left
    nearest = min(groups, key=lambda group: (0 if group[0] <= local_reference <= group[1]
                                             else min(abs(local_reference - group[0]),
                                                      abs(local_reference - group[1]))))
    left = band_left + nearest[0]
    right = band_left + nearest[1] + 1
    if right - left < 24:
        return None
    return VisualPlatform(left=left, top=top, right=right)


__all__ = ["VisualPlatform", "detect_visual_platform"]
