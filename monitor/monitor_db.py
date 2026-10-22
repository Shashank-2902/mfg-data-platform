import psycopg

READ_COLUMNS = ["torque_nm", "air_temp_k", "process_temp_k", "rotational_speed_rpm", "tool_wear_min"]

# The newest N rows of every machine, but only rows received recently.
RECENT_ROWS_SQL = """
    SELECT machine_id, received_at, torque_nm, air_temp_k, process_temp_k,
           rotational_speed_rpm, tool_wear_min
    FROM (
        SELECT *, row_number() OVER (PARTITION BY machine_id ORDER BY event_time DESC) AS rn
        FROM raw_readings
        WHERE received_at > now() - make_interval(mins => %s)
    ) t
    WHERE rn <= %s
    ORDER BY machine_id, rn
"""


# The last reading of every machine, over all history. A machine that has been
# silent for hours must still be known, otherwise its silence incident would close.
LAST_SEEN_SQL = "SELECT machine_id, max(received_at) FROM raw_readings GROUP BY machine_id"


def connect(url):
    return psycopg.connect(url, autocommit=True)


def get_state(conn, rows_per_machine, lookback_minutes):
    """Return (now, last_seen, recent_rows) as read from the database."""
    now = conn.execute("SELECT now()").fetchone()[0]
    last_seen = dict(conn.execute(LAST_SEEN_SQL).fetchall())

    # Only recent rows are used for the stuck and range checks.
    result = conn.execute(RECENT_ROWS_SQL, (lookback_minutes, rows_per_machine)).fetchall()
    recent_rows = {}
    for machine_id, _received_at, *values in result:
        recent_rows.setdefault(machine_id, []).append(dict(zip(READ_COLUMNS, values)))
    return now, last_seen, recent_rows


def resolve_cleared(conn, active_alerts):
    """Close open incidents whose problem is gone."""
    active = {(a["machine_id"], a["incident_type"]) for a in active_alerts}
    open_incidents = conn.execute(
        "SELECT id, machine_id, incident_type FROM incidents WHERE status = 'open'"
    ).fetchall()
    for incident_id, machine_id, incident_type in open_incidents:
        if (machine_id, incident_type) not in active:
            conn.execute(
                "UPDATE incidents SET status = 'resolved', resolved_at = now() WHERE id = %s",
                (incident_id,),
            )
