import os

# No data for longer than this many seconds counts as silence.
SILENCE_SECONDS = int(os.getenv("SILENCE_SECONDS", "60"))

# This many identical values in a row count as a stuck sensor.
STUCK_COUNT = int(os.getenv("STUCK_COUNT", "10"))

# Sensors the stuck check looks at. air_temp_k is left out on purpose: it has only
# 93 distinct values in the AI4I data and one machine repeats the same value 10
# times in a row, which would be a false alarm.
STUCK_SENSORS = ["torque_nm", "rotational_speed_rpm", "process_temp_k"]

# How often the monitor looks at the data.
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "5"))

# The stuck and range checks only look at readings received within this many
# minutes. The silence check does not use it: it looks at the whole history.
LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "60"))

# Allowed range for each value. Wide on purpose: they only catch broken sensors.
RANGES = {
    "air_temp_k": (270, 330),
    "process_temp_k": (280, 340),
    "rotational_speed_rpm": (500, 4000),
    "torque_nm": (0, 100),
    "tool_wear_min": (0, 300),
}
