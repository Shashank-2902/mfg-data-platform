"""Compare the monitor with a simple baseline, using simulated time (no Docker needed).

The baseline is the obvious first idea: only alert when a machine stops sending data.
The monitor also checks for stuck values and values out of range.

    python benchmark/detection_delay.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in ["replayer", "monitor"]:
    sys.path.append(os.path.join(HERE, "..", folder))

import checks  # noqa: E402
import data_reader  # noqa: E402
import fault_injector  # noqa: E402
import message_builder  # noqa: E402
import rules  # noqa: E402

CSV_PATH = os.path.join(HERE, "..", "data", "ai4i2020.csv")
RATE = 10                # messages per second
ROWS = 2000              # 200 seconds of simulated time
FAULT_START_ROW = 300    # the fault starts 30 seconds in

# Which alert we expect for each fault.
EXPECTED = {
    "silence": ("M3", "silence"),
    "sensor_stuck": ("M2", "sensor_stuck"),
    "out_of_range": ("M4", "out_of_range"),
}


def monitor_rule(last_seen, recent_rows, now):
    return checks.find_alerts(last_seen, recent_rows, now)


def baseline_rule(last_seen, recent_rows, now):
    return checks.check_silence(last_seen, now)


def simulate(fault, rule, rows):
    """Replay the data with simulated time. Returns {(machine, type): first alert time in seconds}."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    last_seen = {}
    recent_rows = {}
    memory = {}
    first_alert = {}

    for index in range(ROWS):
        seconds = index / RATE
        now = start + timedelta(seconds=seconds)

        message = message_builder.build_message(rows[index % len(rows)], index)
        message = fault_injector.apply_fault(message, fault, index >= FAULT_START_ROW, memory)
        if message is not None:
            machine = message["machine_id"]
            last_seen[machine] = now
            recent_rows.setdefault(machine, []).insert(0, message)
            del recent_rows[machine][rules.STUCK_COUNT:]

        # The monitor looks at the data every few seconds.
        if index % (rules.CHECK_EVERY_SECONDS * RATE) == 0:
            for alert in rule(last_seen, recent_rows, now):
                key = (alert["machine_id"], alert["incident_type"])
                first_alert.setdefault(key, seconds)
    return first_alert


def measure():
    """Return one result per fault: detection delay for the monitor and the baseline, and false alarms."""
    rows = data_reader.read_rows(CSV_PATH)
    fault_start_seconds = FAULT_START_ROW / RATE
    results = []

    for fault, expected_key in EXPECTED.items():
        result = {"fault": fault}
        for name, rule in [("monitor", monitor_rule), ("baseline", baseline_rule)]:
            alerts = simulate(fault, rule, rows)
            detected_at = alerts.get(expected_key)
            result[name + "_delay"] = None if detected_at is None else round(detected_at - fault_start_seconds, 1)
            result[name + "_false_alarms"] = len([key for key in alerts if key != expected_key])
        results.append(result)

    clean = {"fault": "none (clean run)"}
    for name, rule in [("monitor", monitor_rule), ("baseline", baseline_rule)]:
        clean[name + "_delay"] = None
        clean[name + "_false_alarms"] = len(simulate("none", rule, rows))
    results.append(clean)
    return results


def format_delay(value):
    return "not detected" if value is None else f"{value} s"


def as_markdown(results):
    lines = [
        "| Fault | Monitor: detection delay | Baseline (silence only): detection delay | False alarms (monitor / baseline) |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        delay_monitor = "-" if r["fault"].startswith("none") else format_delay(r["monitor_delay"])
        delay_baseline = "-" if r["fault"].startswith("none") else format_delay(r["baseline_delay"])
        false_alarms = f"{r['monitor_false_alarms']} / {r['baseline_false_alarms']}"
        lines.append(f"| {r['fault']} | {delay_monitor} | {delay_baseline} | {false_alarms} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(as_markdown(measure()))
