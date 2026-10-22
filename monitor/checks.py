import rules


def make_alert(machine_id, incident_type, severity, message):
    return {
        "machine_id": machine_id,
        "incident_type": incident_type,
        "severity": severity,
        "message": message,
    }


def check_silence(last_seen, now, limit_seconds=rules.SILENCE_SECONDS):
    """last_seen maps machine_id to the time of its last reading."""
    alerts = []
    for machine_id, seen_at in last_seen.items():
        silent_for = (now - seen_at).total_seconds()
        if silent_for > limit_seconds:
            message = f"no data for {int(silent_for)} seconds"
            alerts.append(make_alert(machine_id, "silence", "high", message))
    return alerts


def check_stuck(recent_rows, count=rules.STUCK_COUNT, sensors=rules.STUCK_SENSORS):
    """recent_rows maps machine_id to its latest rows, newest first."""
    alerts = []
    for machine_id, rows in recent_rows.items():
        problems = []
        for sensor in sensors:
            values = [row[sensor] for row in rows[:count]]
            if len(values) == count and len(set(values)) == 1:
                problems.append(f"{sensor} stuck at {values[0]} for {count} readings")
        if problems:
            alerts.append(make_alert(machine_id, "sensor_stuck", "medium", "; ".join(problems)))
    return alerts


def check_range(recent_rows, ranges=rules.RANGES, look_at=5):
    """Look at the last few rows of each machine for values outside the allowed range."""
    alerts = []
    for machine_id, rows in recent_rows.items():
        problems = []
        for row in rows[:look_at]:
            for name, (low, high) in ranges.items():
                value = row[name]
                text = f"{name} = {value} is outside {low} to {high}"
                if (value < low or value > high) and text not in problems:
                    problems.append(text)
        if problems:
            alerts.append(make_alert(machine_id, "out_of_range", "high", "; ".join(problems)))
    return alerts


def find_alerts(last_seen, recent_rows, now):
    """Run all checks and return the list of alerts."""
    return check_silence(last_seen, now) + check_stuck(recent_rows) + check_range(recent_rows)
