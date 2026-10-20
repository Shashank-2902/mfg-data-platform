# Which machine each fault is applied to.
FAULT_MACHINE = {
    "silence": "M3",
    "sensor_stuck": "M2",
    "out_of_range": "M4",
}

FAULTS = ["none"] + list(FAULT_MACHINE)


def apply_fault(message, fault, fault_started, memory):
    """Return the message to publish, changed by the fault. Return None to skip it.

    memory is a dict that remembers the frozen value of a stuck sensor.
    """
    if fault == "none" or not fault_started:
        return message
    if message["machine_id"] != FAULT_MACHINE[fault]:
        return message

    if fault == "silence":
        return None

    if fault == "sensor_stuck":
        # The torque sensor keeps sending the first value it had when it got stuck.
        if "torque_nm" not in memory:
            memory["torque_nm"] = message["torque_nm"]
        message["torque_nm"] = memory["torque_nm"]
        return message

    if fault == "out_of_range":
        # A broken temperature sensor reports 0 Kelvin.
        message["air_temp_k"] = 0.0
        return message

    return message
