import os

# No data for longer than this many seconds counts as silence.
SILENCE_SECONDS = int(os.getenv("SILENCE_SECONDS", "60"))

# This many identical torque values in a row count as a stuck sensor.
STUCK_COUNT = int(os.getenv("STUCK_COUNT", "10"))

# How often the monitor looks at the data.
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "5"))

# Only readings received within this many minutes are looked at.
LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "60"))

# Allowed range for each value. Wide on purpose: they only catch broken sensors.
RANGES = {
    "air_temp_k": (270, 330),
    "process_temp_k": (280, 340),
    "rotational_speed_rpm": (500, 4000),
    "torque_nm": (0, 100),
    "tool_wear_min": (0, 300),
}
