import psycopg

INSERT_READING = """
    INSERT INTO raw_readings (
        machine_id, event_time, udi, product_type, air_temp_k, process_temp_k,
        rotational_speed_rpm, torque_nm, tool_wear_min, machine_failure,
        twf, hdf, pwf, osf, rnf
    ) VALUES (
        %(machine_id)s, %(event_time)s, %(udi)s, %(product_type)s, %(air_temp_k)s, %(process_temp_k)s,
        %(rotational_speed_rpm)s, %(torque_nm)s, %(tool_wear_min)s, %(machine_failure)s,
        %(twf)s, %(hdf)s, %(pwf)s, %(osf)s, %(rnf)s
    )
    ON CONFLICT (machine_id, event_time) DO NOTHING
"""


def connect(url):
    return psycopg.connect(url, autocommit=True)


def save_reading(conn, message):
    """Insert one reading. Returns True if it was new, False if we already had it."""
    cursor = conn.execute(INSERT_READING, message)
    return cursor.rowcount == 1


def save_rejected(conn, payload_text, reason):
    conn.execute(
        "INSERT INTO rejected_readings (reason, payload) VALUES (%s, %s)",
        (reason, payload_text),
    )
