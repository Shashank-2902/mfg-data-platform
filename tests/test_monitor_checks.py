from datetime import datetime, timedelta, timezone

import checks

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def normal_row(torque=40.0, air_temp=298.0):
    return {
        "torque_nm": torque,
        "air_temp_k": air_temp,
        "process_temp_k": 308.0,
        "rotational_speed_rpm": 1500,
        "tool_wear_min": 10,
    }


def varied_rows(count=10):
    return [normal_row(torque=40.0 + i) for i in range(count)]


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
