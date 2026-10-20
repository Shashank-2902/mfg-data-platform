import os
from datetime import datetime

import data_reader
import fault_injector
import message_builder

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai4i2020.csv")


def test_csv_has_10000_rows():
    rows = data_reader.read_rows(CSV_PATH)
    assert len(rows) == 10000
    assert rows[0]["udi"] == 1
    assert rows[0]["torque_nm"] == 42.8


def test_machines_take_turns():
    assert message_builder.machine_for(0) == "M1"
    assert message_builder.machine_for(4) == "M5"
    assert message_builder.machine_for(5) == "M1"


def test_event_time_is_fixed_and_ten_seconds_apart():
    first = datetime.fromisoformat(message_builder.event_time_for(0).isoformat())
    second = datetime.fromisoformat(message_builder.event_time_for(1).isoformat())
    assert (second - first).total_seconds() == 10
    # Same index always gives the same time, so a repeated replay is not a new reading.
    assert message_builder.event_time_for(7) == message_builder.event_time_for(7)


def make_message(machine_id, torque=40.0):
    return {"machine_id": machine_id, "torque_nm": torque, "air_temp_k": 298.0}


def test_no_fault_changes_nothing():
    message = make_message("M3")
    assert fault_injector.apply_fault(message, "none", True, {}) == message


def test_fault_does_nothing_before_it_starts():
    message = make_message("M3")
    assert fault_injector.apply_fault(message, "silence", False, {}) == message


def test_silence_drops_only_the_faulty_machine():
    assert fault_injector.apply_fault(make_message("M3"), "silence", True, {}) is None
    assert fault_injector.apply_fault(make_message("M1"), "silence", True, {}) is not None


def test_sensor_stuck_freezes_the_first_value():
    memory = {}
    first = fault_injector.apply_fault(make_message("M2", torque=41.0), "sensor_stuck", True, memory)
    second = fault_injector.apply_fault(make_message("M2", torque=55.5), "sensor_stuck", True, memory)
    assert first["torque_nm"] == 41.0
    assert second["torque_nm"] == 41.0


def test_out_of_range_sets_temperature_to_zero():
    changed = fault_injector.apply_fault(make_message("M4"), "out_of_range", True, {})
    assert changed["air_temp_k"] == 0.0
    untouched = fault_injector.apply_fault(make_message("M1"), "out_of_range", True, {})
    assert untouched["air_temp_k"] == 298.0
