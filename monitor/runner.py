import checks
import monitor_db
import outbox
import rules


def run_once(conn, send):
    """One round: read the data, find problems, queue alerts, try to deliver them.

    Alerts go to the outbox first. If n8n is down, delivery fails and is tried
    again later. Nothing here touches ingestion.
    """
    now, last_seen, recent_rows = monitor_db.get_state(
        conn, rows_per_machine=rules.STUCK_COUNT, lookback_minutes=rules.LOOKBACK_MINUTES
    )

    alerts = checks.find_alerts(last_seen, recent_rows, now)

    for alert in alerts:
        outbox.add_if_new(conn, alert)

    monitor_db.resolve_cleared(conn, alerts)
    return outbox.deliver_pending(conn, send)
