import math
from datetime import datetime

NUMBER_FIELDS = ["air_temp_k", "process_temp_k", "torque_nm"]
INTEGER_FIELDS = ["udi", "rotational_speed_rpm", "tool_wear_min"]
FLAG_FIELDS = ["machine_failure", "twf", "hdf", "pwf", "osf", "rnf"]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_message(message):
    """Return (True, "") if the message is well formed, else (False, reason).

    This only checks the shape of the message. Whether a value makes sense
    (for example 0 Kelvin) is judged later by the monitor, so such rows are kept.
    """
    if not isinstance(message, dict):
        return False, "message is not a json object"

    if not isinstance(message.get("machine_id"), str) or message["machine_id"] == "":
        return False, "machine_id missing"

    try:
        datetime.fromisoformat(message["event_time"])
    except (KeyError, TypeError, ValueError):
        return False, "event_time missing or not a date"

    if message.get("product_type") not in ("L", "M", "H"):
        return False, "product_type must be L, M or H"

    for name in NUMBER_FIELDS:
        if not is_number(message.get(name)):
            return False, f"{name} missing or not a number"

    for name in INTEGER_FIELDS:
        if not is_integer(message.get(name)):
            return False, f"{name} missing or not an integer"

    for name in FLAG_FIELDS:
        value = message.get(name)
        if isinstance(value, bool) or value not in (0, 1):
            return False, f"{name} must be 0 or 1"

    return True, ""
