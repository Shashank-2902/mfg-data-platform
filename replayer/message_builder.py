from datetime import datetime, timedelta, timezone

# The dataset has no real timestamps, so we make them up.
# Row 0 is at START_TIME, row 1 is 10 seconds later, and so on.
START_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
SECONDS_PER_ROW = 10

# The dataset has no machine ids either, so the rows are shared between 5 machines.
MACHINES = ["M1", "M2", "M3", "M4", "M5"]


def machine_for(index):
    return MACHINES[index % len(MACHINES)]


def event_time_for(index):
    return START_TIME + timedelta(seconds=index * SECONDS_PER_ROW)


def build_message(row, index):
    """Turn one dataset row into the message we publish."""
    message = dict(row)
    message["machine_id"] = machine_for(index)
    message["event_time"] = event_time_for(index).isoformat()
    return message
