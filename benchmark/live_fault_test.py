"""Run each fault against the real Docker stack and measure what happens.

Needs the stack running: docker compose --profile demo up -d --build
    python benchmark/live_fault_test.py

Every fault and the clean run are repeated RUNS times. For each one it reports
the run length, how long the monitor needed to open an incident (mean, minimum,
maximum), false alarms and how many readings were lost (should be 0).
"""
import json
import os
import statistics
import subprocess
import sys
import time

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.append(os.path.join(ROOT, "replayer"))
sys.path.append(os.path.join(ROOT, "scripts"))

import env_file  # noqa: E402
import fault_injector  # noqa: E402
import message_builder  # noqa: E402

RUNS = 5
SAVE_FILE = os.path.join(HERE, "results", "live_runs.jsonl")
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
    first, last = conn.execute("SELECT min(received_at), max(received_at) FROM raw_readings").fetchone()
    result = {"fault": fault, "rows_lost": expected_rows(fault) - stored,
              "run_seconds": (last - first).total_seconds()}
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


def summarize(fault, runs):
    delays = [r["delay"] for r in runs if r.get("delay") is not None]
    summary = {
        "fault": fault,
        "runs": len(runs),
        "run_seconds": statistics.mean(r["run_seconds"] for r in runs),
        "false_alarms": sum(r["false_alarms"] for r in runs),
        "rows_lost": sum(r["rows_lost"] for r in runs),
        "detected": len(delays),
    }
    if delays:
        summary.update(mean=statistics.mean(delays), low=min(delays), high=max(delays))
    return summary


def print_table(summaries):
    print()
    print("| Fault | Runs | Run length | Detected | Delay mean | Delay min | Delay max | False alarms | Rows lost |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in summaries:
        length = f"{ROWS} rows, {s['run_seconds']:.0f} s"
        if s["fault"] == "none":
            delays = "- | - | -"
            detected = "-"
        else:
            detected = f"{s['detected']}/{s['runs']}"
            delays = f"{s['mean']:.1f} s | {s['low']:.1f} s | {s['high']:.1f} s" if s["detected"] else "- | - | -"
        print(f"| {s['fault']} | {s['runs']} | {length} | {detected} | {delays} | {s['false_alarms']} | {s['rows_lost']} |")


def is_valid(run):
    """A run that took far longer than the replay (for example the laptop slept) is thrown away."""
    return run["run_seconds"] < ROWS / RATE * 1.5


def load_saved_runs():
    """Runs finished in an earlier start of this script, so a stop does not lose them."""
    saved = {}
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, encoding="utf-8") as f:
            for line in f:
                run = json.loads(line)
                if is_valid(run):
                    saved.setdefault(run["fault"], []).append(run)
    return saved


def save_run(run):
    os.makedirs(os.path.dirname(SAVE_FILE), exist_ok=True)
    with open(SAVE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")


def main():
    """Run python benchmark/live_fault_test.py again after a stop to carry on.
    Use --fresh to delete the saved runs and start from zero."""
    if "--fresh" in sys.argv and os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    saved = load_saved_runs()

    conn = psycopg.connect(env_file.database_url(), autocommit=True)
    summaries = []
    for fault in ["none", "silence", "sensor_stuck", "out_of_range"]:
        runs = saved.get(fault, [])[:RUNS]
        while len(runs) < RUNS:
            print(f"Fault {fault}, run {len(runs) + 1} of {RUNS} ...", flush=True)
            run = measure(conn, fault)
            if is_valid(run):
                save_run(run)
                runs.append(run)
            else:
                print(f"  run took {run['run_seconds']:.0f} s, thrown away and repeated", flush=True)
        summaries.append(summarize(fault, runs))

    print_table(summaries)


if __name__ == "__main__":
    main()
