from datetime import datetime, timedelta, timezone

import os

import checks
import data_reader
import message_builder
import rules

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def normal_row(torque=40.0, air_temp=298.0):
    return {
        "torque_nm": torque,
        "air_temp_k": air_temp,
        "process_temp_k": 308.0,
        "rotational_speed_rpm": 1500,
        "tool_wear_min": 10,
    }


def moving_row(i, **changes):
    """A row whose torque, speed and process temperature all change with i."""
    row = normal_row(torque=40.0 + i)
    row["rotational_speed_rpm"] = 1500 + i
    row["process_temp_k"] = 308.0 + i / 10
    row.update(changes)
    return row


def varied_rows(count=10):
    return [moving_row(i) for i in range(count)]


def test_recent_data_is_not_silence():
    last_seen = {"M1": NOW - timedelta(seconds=5)}
    assert checks.check_silence(last_seen, NOW, limit_seconds=60) == []


def test_old_data_is_silence():
    last_seen = {"M1": NOW - timedelta(seconds=90), "M2": NOW - timedelta(seconds=1)}
    alerts = checks.check_silence(last_seen, NOW, limit_seconds=60)
    assert len(alerts) == 1
    assert alerts[0]["machine_id"] == "M1"
    assert alerts[0]["incident_type"] == "silence"


def test_changing_torque_is_not_stuck():
    assert checks.check_stuck({"M1": varied_rows()}, count=10) == []


def test_same_torque_ten_times_is_stuck():
    rows = [normal_row(torque=41.0) for _ in range(10)]
    alerts = checks.check_stuck({"M2": rows}, count=10)
    assert len(alerts) == 1
    assert alerts[0]["incident_type"] == "sensor_stuck"


def test_not_enough_readings_is_not_stuck():
    rows = [normal_row(torque=41.0) for _ in range(4)]
    assert checks.check_stuck({"M2": rows}, count=10) == []


def test_normal_values_are_in_range():
    assert checks.check_range({"M1": varied_rows()}) == []


def test_zero_kelvin_is_out_of_range():
    rows = [normal_row(air_temp=0.0)] + varied_rows(4)
    alerts = checks.check_range({"M4": rows})
    assert len(alerts) == 1
    assert alerts[0]["incident_type"] == "out_of_range"
    assert "air_temp_k" in alerts[0]["message"]


def test_a_clean_stream_gives_no_alerts():
    last_seen = {"M1": NOW}
    assert checks.find_alerts(last_seen, {"M1": varied_rows()}, NOW) == []


def test_stuck_speed_is_found_and_named():
    rows = [moving_row(i, rotational_speed_rpm=1500) for i in range(10)]
    alerts = checks.check_stuck({"M1": rows}, count=10)
    assert len(alerts) == 1
    assert "rotational_speed_rpm stuck at 1500" in alerts[0]["message"]
    assert "torque_nm" not in alerts[0]["message"]


def test_stuck_process_temperature_is_found_and_named():
    rows = [moving_row(i, process_temp_k=308.6) for i in range(10)]
    alerts = checks.check_stuck({"M1": rows}, count=10)
    assert "process_temp_k stuck at 308.6" in alerts[0]["message"]


def test_two_stuck_sensors_give_one_alert_naming_both():
    rows = [moving_row(i, torque_nm=41.0, rotational_speed_rpm=1500) for i in range(10)]
    alerts = checks.check_stuck({"M1": rows}, count=10)
    assert len(alerts) == 1
    assert "torque_nm" in alerts[0]["message"] and "rotational_speed_rpm" in alerts[0]["message"]


def test_air_temperature_is_not_checked_for_stuck():
    rows = [moving_row(i, air_temp_k=298.0) for i in range(10)]
    assert "air_temp_k" not in rules.STUCK_SENSORS
    assert checks.check_stuck({"M1": rows}, count=10) == []


def test_real_ai4i_rows_give_no_stuck_alarm():
    """Slide a window of STUCK_COUNT readings over every machine of the real data."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "ai4i2020.csv")
    rows = data_reader.read_rows(path)
    per_machine = {}
    for index, row in enumerate(rows):
        per_machine.setdefault(message_builder.machine_for(index), []).append(row)

    for machine_id, machine_rows in per_machine.items():
        for start in range(len(machine_rows) - rules.STUCK_COUNT + 1):
            window = machine_rows[start:start + rules.STUCK_COUNT]
            newest_first = list(reversed(window))
            assert checks.check_stuck({machine_id: newest_first}) == [], (machine_id, start)
