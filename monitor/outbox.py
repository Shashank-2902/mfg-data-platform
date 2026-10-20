ADD_IF_NEW_SQL = """
    INSERT INTO outbox (machine_id, incident_type, severity, message)
    SELECT %(machine_id)s, %(incident_type)s, %(severity)s, %(message)s
    WHERE NOT EXISTS (
        SELECT 1 FROM outbox
        WHERE machine_id = %(machine_id)s AND incident_type = %(incident_type)s AND delivered_at IS NULL
    )
    AND NOT EXISTS (
        SELECT 1 FROM incidents
        WHERE machine_id = %(machine_id)s AND incident_type = %(incident_type)s AND status = 'open'
    )
"""

DUE_SQL = """
    SELECT id, machine_id, incident_type, severity, message, created_at
    FROM outbox
    WHERE delivered_at IS NULL AND next_attempt_at <= now()
    ORDER BY id
    LIMIT 20
"""


def backoff_seconds(attempts):
    """Wait 10, 20, 40 ... seconds after each failed attempt, but never more than 5 minutes."""
    return min(5 * 2 ** attempts, 300)


def add_if_new(conn, alert):
    """Put an alert in the outbox unless the same problem is already waiting or open."""
    cursor = conn.execute(ADD_IF_NEW_SQL, alert)
    return cursor.rowcount == 1


def is_delivered(conn, outbox_id):
    row = conn.execute("SELECT delivered_at IS NOT NULL FROM outbox WHERE id = %s", (outbox_id,)).fetchone()
    return row[0]


def mark_failed(conn, outbox_id, attempts):
    conn.execute(
        "UPDATE outbox SET attempts = attempts + 1, "
        "next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s",
        (backoff_seconds(attempts + 1), outbox_id),
    )


def deliver_pending(conn, send):
    """Try to send every alert that is due. Returns how many were delivered.

    send(payload) must raise an error when the alert could not be sent.
    n8n marks the outbox row as delivered itself, so we check that too.
    """
    delivered = 0
    for row in conn.execute(DUE_SQL).fetchall():
        outbox_id, machine_id, incident_type, severity, message, created_at = row
        attempts = conn.execute("SELECT attempts FROM outbox WHERE id = %s", (outbox_id,)).fetchone()[0]
        payload = {
            "outbox_id": outbox_id,
            "machine_id": machine_id,
            "incident_type": incident_type,
            "severity": severity,
            "message": message,
            "created_at": created_at.isoformat(),
        }
        try:
            send(payload)
            if not is_delivered(conn, outbox_id):
                raise RuntimeError("n8n answered but did not mark the row as delivered")
            delivered += 1
        except Exception as error:
            print(f"Could not deliver outbox {outbox_id} (attempt {attempts + 1}): {error}")
            mark_failed(conn, outbox_id, attempts)
    return delivered
