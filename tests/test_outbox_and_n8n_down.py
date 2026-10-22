"""Tests for the alert delivery rule: if n8n is down, ingestion carries on and
alerts wait in the outbox and are retried."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg

import handler
import n8n_client
import outbox
import runner
from conftest import make_message, database_url_for_tests

DEAD_URL = "http://127.0.0.1:9/webhook/incident"  # nothing listens on port 9

ALERT = {
    "machine_id": "M3",
    "incident_type": "silence",
    "severity": "high",
    "message": "no data for 75 seconds",
}


def count(conn, table, where="true"):
    return conn.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]


def start_fake_n8n():
    """A small web server that behaves like the n8n flow: log the incident, mark the outbox row."""

    class FakeN8n(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with psycopg.connect(database_url_for_tests(), autocommit=True) as db:
                db.execute(
                    "INSERT INTO incidents (machine_id, incident_type, severity, message, outbox_id) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (machine_id, incident_type) "
                    "WHERE status = 'open' DO NOTHING",
                    (body["machine_id"], body["incident_type"], body["severity"], body["message"], body["outbox_id"]),
                )
                db.execute("UPDATE outbox SET delivered_at = now() WHERE id = %s", (body["outbox_id"],))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"delivered": true}')

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), FakeN8n)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/webhook/incident"


def send_to(url):
    return lambda payload: n8n_client.send(url, payload)


def make_due(conn):
    conn.execute("UPDATE outbox SET next_attempt_at = now()")


def test_backoff_grows_and_stops_at_five_minutes():
    assert outbox.backoff_seconds(1) == 10
    assert outbox.backoff_seconds(2) == 20
    assert outbox.backoff_seconds(3) == 40
    assert outbox.backoff_seconds(20) == 300


def test_same_problem_is_queued_only_once(conn):
    assert outbox.add_if_new(conn, ALERT) is True
    assert outbox.add_if_new(conn, ALERT) is False
    assert count(conn, "outbox") == 1


def test_open_incident_blocks_a_new_alert(conn):
    conn.execute(
        "INSERT INTO incidents (machine_id, incident_type, severity, message) VALUES ('M3', 'silence', 'high', 'x')"
    )
    assert outbox.add_if_new(conn, ALERT) is False


def test_failed_delivery_is_retried_later_with_backoff(conn):
    outbox.add_if_new(conn, ALERT)

    delivered = outbox.deliver_pending(conn, send_to(DEAD_URL))
    assert delivered == 0
    assert count(conn, "outbox", "attempts = 1 AND delivered_at IS NULL") == 1

    # The retry time is in the future, so asking again right away tries nothing.
    outbox.deliver_pending(conn, send_to(DEAD_URL))
    assert count(conn, "outbox", "attempts = 1") == 1

    # When the retry time has come and the call fails again, the attempt counter goes up.
    make_due(conn)
    outbox.deliver_pending(conn, send_to(DEAD_URL))
    assert count(conn, "outbox", "attempts = 2") == 1


def test_alert_is_delivered_when_n8n_is_back(conn):
    outbox.add_if_new(conn, ALERT)
    outbox.deliver_pending(conn, send_to(DEAD_URL))

    server, url = start_fake_n8n()
    try:
        make_due(conn)
        assert outbox.deliver_pending(conn, send_to(url)) == 1
    finally:
        server.shutdown()

    assert count(conn, "outbox", "delivered_at IS NOT NULL") == 1
    assert count(conn, "incidents", "status = 'open'") == 1


def test_n8n_answering_without_marking_the_row_counts_as_failure(conn):
    outbox.add_if_new(conn, ALERT)
    outbox.deliver_pending(conn, lambda payload: None)  # "n8n" says ok but changes nothing
    assert count(conn, "outbox", "attempts = 1 AND delivered_at IS NULL") == 1


def test_ingestion_keeps_working_while_n8n_is_down(conn):
    """The key rule: a dead n8n must not stop readings from being stored."""
    # A machine that stopped sending 5 minutes ago, so the monitor wants to raise an alert.
    conn.execute("INSERT INTO raw_readings (machine_id, event_time, received_at, udi, product_type, air_temp_k, "
                 "process_temp_k, rotational_speed_rpm, torque_nm, tool_wear_min, machine_failure, twf, hdf, pwf, "
                 "osf, rnf) VALUES ('M3', '2026-01-01', now() - interval '5 minutes', 1, 'M', 298, 308, 1500, 40, "
                 "0, 0, 0, 0, 0, 0, 0)")

    runner.run_once(conn, send_to(DEAD_URL))
    assert count(conn, "outbox", "delivered_at IS NULL AND attempts >= 1") == 1

    # More readings arrive while n8n is still down. All of them are stored.
    for second in range(20):
        message = make_message("M1", event_time=f"2026-01-01T00:00:{second:02d}+00:00", torque_nm=40.0 + second,
                               rotational_speed_rpm=1500 + second, process_temp_k=308.0 + second / 10)
        assert handler.handle_payload(conn, json.dumps(message).encode()) == "saved"
    assert count(conn, "raw_readings", "machine_id = 'M1'") == 20

    # n8n comes back and the waiting alert is delivered without losing anything.
    server, url = start_fake_n8n()
    try:
        make_due(conn)
        runner.run_once(conn, send_to(url))
    finally:
        server.shutdown()

    assert count(conn, "outbox", "delivered_at IS NOT NULL") == 1
    assert count(conn, "incidents", "incident_type = 'silence' AND status = 'open'") == 1
    assert count(conn, "raw_readings", "machine_id = 'M1'") == 20


def test_incident_is_closed_when_the_problem_is_gone(conn):
    conn.execute(
        "INSERT INTO incidents (machine_id, incident_type, severity, message) VALUES ('M3', 'silence', 'high', 'x')"
    )
    runner.run_once(conn, send_to(DEAD_URL))  # there is no data at all, so no problem is active
    assert count(conn, "incidents", "status = 'resolved'") == 1


def insert_reading_received(conn, machine_id, interval):
    """Store one reading that the database received `interval` ago, e.g. '2 hours'."""
    conn.execute(
        "INSERT INTO raw_readings (machine_id, event_time, received_at, udi, product_type, air_temp_k, "
        "process_temp_k, rotational_speed_rpm, torque_nm, tool_wear_min, machine_failure, twf, hdf, pwf, "
        "osf, rnf) VALUES (%s, now() - %s::interval, now() - %s::interval, 1, 'M', 298, 308, 1500, 40, "
        "0, 0, 0, 0, 0, 0, 0)",
        (machine_id, interval, interval),
    )


def test_a_machine_silent_for_two_hours_keeps_its_open_incident(conn):
    insert_reading_received(conn, "M3", "2 hours")
    conn.execute(
        "INSERT INTO incidents (machine_id, incident_type, severity, message) VALUES ('M3', 'silence', 'high', 'x')"
    )
    runner.run_once(conn, send_to(DEAD_URL))
    runner.run_once(conn, send_to(DEAD_URL))
    assert count(conn, "incidents", "status = 'open'") == 1
    assert count(conn, "incidents", "status = 'resolved'") == 0


def test_the_silence_incident_resolves_when_new_data_arrives(conn):
    insert_reading_received(conn, "M3", "2 hours")
    conn.execute(
        "INSERT INTO incidents (machine_id, incident_type, severity, message) VALUES ('M3', 'silence', 'high', 'x')"
    )
    runner.run_once(conn, send_to(DEAD_URL))
    assert count(conn, "incidents", "status = 'open'") == 1

    insert_reading_received(conn, "M3", "1 second")
    runner.run_once(conn, send_to(DEAD_URL))
    assert count(conn, "incidents", "status = 'resolved'") == 1
    assert count(conn, "incidents", "status = 'open'") == 0


def start_n8n_that_answers(status):
    """A webhook that always answers with the given status and changes nothing."""

    class Answer(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(status)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/webhook/incident"


def test_an_error_answer_from_n8n_keeps_the_row_undelivered_and_it_is_retried(conn):
    """n8n answers 500 when its Telegram call fails: the monitor must keep the row and try again."""
    outbox.add_if_new(conn, ALERT)
    server, url = start_n8n_that_answers(500)
    try:
        assert outbox.deliver_pending(conn, send_to(url)) == 0
        assert count(conn, "outbox", "attempts = 1 AND delivered_at IS NULL") == 1

        make_due(conn)
        assert outbox.deliver_pending(conn, send_to(url)) == 0
        assert count(conn, "outbox", "attempts = 2 AND delivered_at IS NULL") == 1
    finally:
        server.shutdown()
