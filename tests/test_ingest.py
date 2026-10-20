import json

import handler
import validator
from conftest import make_message


def test_good_message_is_accepted():
    ok, reason = validator.check_message(make_message())
    assert ok and reason == ""


def test_missing_field_is_rejected():
    message = make_message()
    del message["torque_nm"]
    ok, reason = validator.check_message(message)
    assert not ok
    assert "torque_nm" in reason


def test_wrong_types_are_rejected():
    assert not validator.check_message(make_message(torque_nm="high"))[0]
    assert not validator.check_message(make_message(udi=1.5))[0]
    assert not validator.check_message(make_message(twf=True))[0]
    assert not validator.check_message(make_message(twf=2))[0]
    assert not validator.check_message(make_message(product_type="X"))[0]
    assert not validator.check_message(make_message(event_time="yesterday"))[0]
    assert not validator.check_message(make_message(machine_id=""))[0]


def test_not_a_number_is_rejected():
    assert not validator.check_message(make_message(torque_nm=float("nan")))[0]


def test_strange_but_well_formed_value_is_kept_for_the_monitor():
    # 0 Kelvin is wrong, but the shape is fine. The monitor will flag it, ingest keeps it.
    assert validator.check_message(make_message(air_temp_k=0.0))[0]


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_new_reading_is_saved(conn):
    payload = json.dumps(make_message()).encode()
    assert handler.handle_payload(conn, payload) == "saved"
    assert count(conn, "raw_readings") == 1


def test_same_reading_twice_is_stored_once(conn):
    payload = json.dumps(make_message()).encode()
    assert handler.handle_payload(conn, payload) == "saved"
    assert handler.handle_payload(conn, payload) == "duplicate"
    assert count(conn, "raw_readings") == 1


def test_same_time_on_another_machine_is_a_new_reading(conn):
    handler.handle_payload(conn, json.dumps(make_message("M1")).encode())
    handler.handle_payload(conn, json.dumps(make_message("M2")).encode())
    assert count(conn, "raw_readings") == 2


def test_broken_json_goes_to_rejected_table(conn):
    assert handler.handle_payload(conn, b"{not json") == "rejected"
    assert count(conn, "raw_readings") == 0
    assert count(conn, "rejected_readings") == 1


def test_invalid_message_goes_to_rejected_table_with_reason(conn):
    payload = json.dumps(make_message(product_type="X")).encode()
    assert handler.handle_payload(conn, payload) == "rejected"
    reason = conn.execute("SELECT reason FROM rejected_readings").fetchone()[0]
    assert "product_type" in reason
