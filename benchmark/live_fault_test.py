"""Run each fault against the real Docker stack and measure what happens.

Needs the stack running: docker compose --profile demo up -d --build
    python benchmark/live_fault_test.py

For every fault it reports how long the monitor needed to open an incident,
whether the alert reached n8n, and how many readings were lost (should be 0).
"""
import os
import subprocess
import sys
import time

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.append(os.path.join(ROOT, "replayer"))

import fault_injector  # noqa: E402
import message_builder  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mfg:mfg_local_pw@localhost:5433/mfg")
ROWS = 1000
RATE = 10
FAULT_START_ROW = 200

EXPECTED = {
    "silence": ("M3", "silence"),
    "sensor_stuck": ("M2", "sensor_stuck"),
    "out_of_range": ("M4", "out_of_range"),
}


def clear_tables(conn):
    conn.execute("TRUNCATE raw_readings, outbox, incidents, rejected_readings RESTART IDENTITY")


def run_replayer(fault):
    command = ["docker", "compose", "run", "--rm", "replayer", "--rows", str(ROWS), "--rate", str(RATE),
               "--fault", fault, "--fault-start-row", str(FAULT_START_ROW)]
    subprocess.run(command, cwd=ROOT, capture_output=True, check=True)


def expected_rows(fault):
    """How many rows should reach the database. A silent machine sends nothing after the fault."""
    skipped = 0
    if fault == "silence":
        for index in range(FAULT_START_ROW, ROWS):
            if message_builder.machine_for(index) == fault_injector.FAULT_MACHINE["silence"]:
                skipped += 1
    return ROWS - skipped


def fault_start_time(conn):
    """Wall-clock time when the row where the fault begins was received."""
    event_time = message_builder.event_time_for(FAULT_START_ROW)
    return conn.execute("SELECT received_at FROM raw_readings WHERE event_time = %s", (event_time,)).fetchone()[0]


def wait_for_delivery(conn, seconds=30):
    """Wait until all alerts in the outbox are delivered."""
    for _ in range(seconds):
        waiting = conn.execute("SELECT count(*) FROM outbox WHERE delivered_at IS NULL").fetchone()[0]
        if waiting == 0:
            return
        time.sleep(1)


def measure(conn, fault):
    clear_tables(conn)
    run_replayer(fault)
    time.sleep(3)  # let the last messages arrive

    stored = conn.execute("SELECT count(*) FROM raw_readings").fetchone()[0]
    result = {"fault": fault, "rows_lost": expected_rows(fault) - stored}
    started = fault_start_time(conn)

    if fault == "none":
        result["false_alarms"] = conn.execute("SELECT count(*) FROM incidents").fetchone()[0]
        return result

    machine, incident_type = EXPECTED[fault]
    wait_for_delivery(conn)
    row = conn.execute(
        "SELECT opened_at FROM incidents WHERE machine_id = %s AND incident_type = %s ORDER BY opened_at LIMIT 1",
        (machine, incident_type),
    ).fetchone()
    result["delay"] = None if row is None else round((row[0] - started).total_seconds(), 1)
    result["false_alarms"] = conn.execute(
        "SELECT count(*) FROM incidents WHERE NOT (machine_id = %s AND incident_type = %s)",
        (machine, incident_type),
    ).fetchone()[0]
    return result


def main():
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    results = []
    for fault in ["none", "silence", "sensor_stuck", "out_of_range"]:
        print(f"Running fault: {fault} ...", flush=True)
        results.append(measure(conn, fault))

    print()
    print("| Fault | Detection delay | False alarms | Rows lost |")
    print("| --- | --- | --- | --- |")
    for r in results:
        delay = "-" if r["fault"] == "none" else ("not detected" if r["delay"] is None else f"{r['delay']} s")
        print(f"| {r['fault']} | {delay} | {r['false_alarms']} | {r['rows_lost']} |")


if __name__ == "__main__":
    main()
