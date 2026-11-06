from datetime import datetime, timedelta, timezone

from synapse_pet.ui.day_cycle import (moon_phase, moon_position, period_name,
                                      activity_factor, scene_palette,
                                      sun_position, sun_times)


def test_default_clock_has_five_expected_local_periods():
    assert period_name(datetime(2026, 6, 1, 4)) == "madrugada"
    assert period_name(datetime(2026, 6, 1, 8)) == "manha"
    assert period_name(datetime(2026, 6, 1, 14)) == "tarde"
    assert period_name(datetime(2026, 6, 1, 17)) == "entardecer"
    assert period_name(datetime(2026, 6, 1, 22)) == "noite"


def test_palette_interpolates_smoothly_across_dawn_and_manual_scene_override():
    before = scene_palette(datetime(2026, 6, 1, 5, 59))
    after = scene_palette(datetime(2026, 6, 1, 6, 1))
    before_rgb = tuple(int(before.sky[index:index + 2], 16)
                       for index in (1, 3, 5))
    after_rgb = tuple(int(after.sky[index:index + 2], 16)
                      for index in (1, 3, 5))
    assert max(abs(a - b) for a, b in zip(before_rgb, after_rgb)) < 8
    assert scene_palette(datetime(2026, 6, 1, 12), "night").sky == "#192b54"


def test_manual_solar_coordinates_are_offline_and_timezone_aware():
    value = datetime(2026, 6, 21, 12, tzinfo=timezone(timedelta(hours=-4)))
    times = sun_times(value, {"latitude": 40.7, "longitude": -74.0})
    assert times.polar_state is None
    assert 5.0 <= times.sunrise_hour <= 6.5
    assert 19.5 <= times.sunset_hour <= 21.5
    assert sun_position(value, {"latitude": 40.7, "longitude": -74.0}) is not None


def test_polar_days_fall_back_to_configured_hours_without_nonfinite_values():
    value = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    times = sun_times(value, {"latitude": 80.0, "longitude": 0.0,
                              "sunrise_hour": 6, "sunset_hour": 18})
    assert times.polar_state == "polar_day"
    assert (times.sunrise_hour, times.sunset_hour) == (6.0, 18.0)


def test_moon_phase_and_night_arc_are_date_driven_without_network():
    new_moon = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    full_moon = datetime(2000, 1, 21, 17, 40, tzinfo=timezone.utc)
    assert moon_phase(new_moon) < 0.01
    assert abs(moon_phase(full_moon) - 0.5) < 0.04
    assert moon_position(datetime(2026, 6, 1, 21)) is not None
    assert moon_position(datetime(2026, 6, 1, 12)) is None


def test_circadian_activity_bias_is_lower_at_night_and_higher_in_morning():
    early = activity_factor(datetime(2026, 6, 1, 4))
    morning = activity_factor(datetime(2026, 6, 1, 9))
    assert early < 1.0 < morning

