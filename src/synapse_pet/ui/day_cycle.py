"""Offline local-time helpers for the Piu scene and circadian presentation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math


@dataclass(frozen=True, slots=True)
class SunTimes:
    sunrise_hour: float
    sunset_hour: float
    polar_state: str | None = None


@dataclass(frozen=True, slots=True)
class ScenePalette:
    sky: str
    horizon: str
    far: str
    near: str
    night_weight: float
    period: str


_PALETTES = {
    "madrugada": ("#273553", "#584a6e", "#4c5572", "#33425f", 0.84),
    "manha": ("#9bd8e8", "#d9f3d0", "#69aa62", "#42784c", 0.08),
    "tarde": ("#78c2d8", "#d6e7a7", "#6da866", "#46764c", 0.00),
    "entardecer": ("#e79b86", "#f4c27d", "#735b83", "#4d486e", 0.26),
    "noite": ("#192b54", "#354a78", "#34466d", "#253557", 1.00),
}


def local_hour(value: datetime) -> float:
    return value.hour + value.minute / 60.0 + value.second / 3600.0


def _solar_hour(day: date, latitude: float, longitude: float,
                utc_offset_hours: float, sunrise: bool) -> tuple[float | None, str | None]:
    day_number = day.timetuple().tm_yday
    longitude_hour = longitude / 15.0
    approximate = day_number + ((6.0 if sunrise else 18.0) - longitude_hour) / 24.0
    mean_anomaly = 0.9856 * approximate - 3.289
    true_longitude = (mean_anomaly + 1.916 * math.sin(math.radians(mean_anomaly))
                      + 0.020 * math.sin(2.0 * math.radians(mean_anomaly))
                      + 282.634) % 360.0
    right_ascension = math.degrees(math.atan(0.91764 * math.tan(
        math.radians(true_longitude)))) % 360.0
    right_ascension += (math.floor(true_longitude / 90.0) * 90.0
                        - math.floor(right_ascension / 90.0) * 90.0)
    right_ascension /= 15.0
    sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
    cos_declination = math.cos(math.asin(sin_declination))
    denominator = cos_declination * math.cos(math.radians(latitude))
    if abs(denominator) < 1e-12:
        return None, "polar_day" if sin_declination * math.sin(
            math.radians(latitude)) > 0 else "polar_night"
    cos_hour_angle = ((math.cos(math.radians(90.833))
                       - sin_declination * math.sin(math.radians(latitude)))
                      / denominator)
    if cos_hour_angle > 1.0:
        return None, "polar_night"
    if cos_hour_angle < -1.0:
        return None, "polar_day"
    angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_hour_angle))))
    hour_angle = (360.0 - angle if sunrise else angle) / 15.0
    local_mean_time = hour_angle + right_ascension - 0.06571 * approximate - 6.622
    utc_hour = (local_mean_time - longitude_hour) % 24.0
    return (utc_hour + utc_offset_hours) % 24.0, None


def sun_times(value: datetime, config: dict | None = None) -> SunTimes:
    config = config or {}
    default_rise = float(config.get("sunrise_hour", 6.0)) % 24.0
    default_set = float(config.get("sunset_hour", 18.0)) % 24.0
    latitude = config.get("latitude")
    longitude = config.get("longitude")
    if latitude is None or longitude is None:
        return SunTimes(default_rise, default_set)
    latitude, longitude = float(latitude), float(longitude)
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return SunTimes(default_rise, default_set)
    offset = value.utcoffset()
    offset_hours = offset.total_seconds() / 3600.0 if offset else 0.0
    rise, rise_polar = _solar_hour(value.date(), latitude, longitude,
                                   offset_hours, True)
    setting, set_polar = _solar_hour(value.date(), latitude, longitude,
                                     offset_hours, False)
    if rise is None or setting is None or rise_polar or set_polar:
        state = rise_polar or set_polar
        return SunTimes(default_rise, default_set, state)
    if (setting - rise) % 24.0 < 1.0:
        return SunTimes(default_rise, default_set, "invalid_solar_day")
    return SunTimes(rise, setting)


def period_name(value: datetime, config: dict | None = None) -> str:
    times = sun_times(value, config)
    hour = local_hour(value)
    dawn_end = max(3.0, min(10.0, times.sunrise_hour - 0.75))
    dusk_start = max(14.0, min(20.0, times.sunset_hour - 1.5))
    night_start = max(dusk_start + 1.0,
                      min(23.7, times.sunset_hour + 1.2))
    if hour >= night_start:
        return "noite"
    if hour < dawn_end:
        return "madrugada"
    if hour < 12.0:
        return "manha"
    if hour < dusk_start:
        return "tarde"
    return "entardecer"


def activity_factor(value: datetime, config: dict | None = None) -> float:
    return {"madrugada": 0.58, "manha": 1.16, "tarde": 1.0,
            "entardecer": 0.82, "noite": 0.68}[period_name(value, config)]


def moon_phase(value: datetime) -> float:
    """Approximate illuminated-cycle position, 0=new and .5=full; no ephemeris."""
    reference = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    instant = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    synodic_month_days = 29.530588853
    return ((instant - reference).total_seconds() / 86400.0
            / synodic_month_days) % 1.0


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index:index + 2], 16)
                 for index in (1, 3, 5))  # type: ignore[return-value]


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(channel))):02x}"
                        for channel in rgb)


def _blend(a: str, b: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    # Smoothstep keeps the palette's speed gentle at each anchor.
    amount = amount * amount * (3.0 - 2.0 * amount)
    left, right = _hex_rgb(a), _hex_rgb(b)
    return _rgb_hex(tuple(round(x + (y - x) * amount)
                          for x, y in zip(left, right)))


def scene_palette(value: datetime, setting: str = "auto",
                  config: dict | None = None) -> ScenePalette:
    config = config or {}
    period = period_name(value, config)
    setting = str(setting).strip().lower()
    forced = {"day": "tarde", "dia": "tarde", "dusk": "entardecer",
              "sunset": "entardecer", "entardecer": "entardecer",
              "night": "noite", "noite": "noite",
              "madrugada": "madrugada", "morning": "manha",
              "manha": "manha", "afternoon": "tarde", "tarde": "tarde"}
    if setting in forced:
        key = forced[setting]
        sky, horizon, far, near, night = _PALETTES[key]
        return ScenePalette(sky, horizon, far, near, night, period)

    times = sun_times(value, config)
    rise, sunset = times.sunrise_hour, times.sunset_hour
    morning = min(22.5, rise + 1.0)
    afternoon = min(sunset - 2.1, (rise + sunset) / 2.0 + 1.4)
    dusk = min(23.0, sunset - 0.65)
    night = min(23.8, sunset + 1.15)
    dawn = max(0.0, rise - 1.25)
    # Anchor colors make a complete circular day; values are sorted and clamped
    # for unusual but valid manually supplied sunrise/sunset settings.
    anchors = [(0.0, "madrugada"), (dawn, "madrugada"),
               (morning, "manha"), (afternoon, "tarde"),
               (dusk, "entardecer"), (night, "noite"), (24.0, "madrugada")]
    ordered = []
    for hour, name in sorted(anchors, key=lambda item: item[0]):
        hour = max(0.0, min(24.0, hour))
        if ordered and hour <= ordered[-1][0]:
            hour = min(24.0, ordered[-1][0] + 0.01)
        ordered.append((hour, name))
    hour = local_hour(value)
    left = ordered[-2]
    right = ordered[-1]
    for first, second in zip(ordered, ordered[1:]):
        if first[0] <= hour < second[0]:
            left, right = first, second
            break
    ratio = 0.0 if right[0] == left[0] else (hour - left[0]) / (right[0] - left[0])
    first_palette, second_palette = _PALETTES[left[1]], _PALETTES[right[1]]
    colors = [_blend(first_palette[index], second_palette[index], ratio)
              for index in range(4)]
    night_weight = first_palette[4] + (second_palette[4] - first_palette[4]) * (
        ratio * ratio * (3.0 - 2.0 * ratio))
    return ScenePalette(*colors, max(0.0, min(1.0, night_weight)), period)


def sun_position(value: datetime, config: dict | None = None) -> tuple[float, float] | None:
    times = sun_times(value, config)
    span = (times.sunset_hour - times.sunrise_hour) % 24.0
    elapsed = (local_hour(value) - times.sunrise_hour) % 24.0
    if span <= 0.0 or elapsed > span:
        return None
    fraction = elapsed / span
    altitude = math.sin(math.pi * fraction)
    return fraction, altitude


def moon_position(value: datetime, config: dict | None = None) -> tuple[float, float] | None:
    times = sun_times(value, config)
    night_span = (times.sunrise_hour - times.sunset_hour) % 24.0
    elapsed = (local_hour(value) - times.sunset_hour) % 24.0
    if night_span <= 0.0 or elapsed > night_span:
        return None
    fraction = elapsed / night_span
    return fraction, math.sin(math.pi * fraction)


__all__ = ["ScenePalette", "SunTimes", "activity_factor", "local_hour",
           "moon_phase", "moon_position", "period_name", "scene_palette",
           "sun_position", "sun_times"]
