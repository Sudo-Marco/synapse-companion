import time
from synapse_pet.sensors.active_window import ActiveWindowCategorySensor
from synapse_pet.sensors.input_activity import InputActivitySensor
from synapse_pet.sensors.manager import SensorManager
from synapse_pet.runtime.logging_db import ActionLog

def test_sensors_are_off_by_default(tmp_path):
    manager = SensorManager(tmp_path, {}, {})
    assert all(not manager.sensors[name].enabled for name in manager.NAMES)
    assert not InputActivitySensor().enabled
    assert not ActiveWindowCategorySensor({"code": ["code"]}).enabled

def test_keyboard_sensor_reports_only_rate():
    sensor = InputActivitySensor(enabled=True)
    sensor._last = time.monotonic() - 2
    sensor._on_key("typed-secret")
    event = sensor.sample()
    assert event is not None
    assert isinstance(event.value, float)
    assert event.value > 0
    assert not hasattr(event, "key")

def test_window_rules_only_store_categories():
    sensor = ActiveWindowCategorySensor({"codigo": ["code"]}, enabled=True)
    assert sensor.rules == {"codigo": ("code",)}
    assert not hasattr(sensor, "window_title")

def test_action_log_schema_has_no_text_or_window_title(tmp_path):
    log = ActionLog(tmp_path / "actions.sqlite3")
    log.record("pause", "success", 0.1, "codigo")
    import sqlite3
    with sqlite3.connect(log.path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(actions)")}
    assert "text" not in columns
    assert "window_title" not in columns
