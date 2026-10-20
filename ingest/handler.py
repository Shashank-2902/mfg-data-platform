import json

import readings_db
import validator


def handle_payload(conn, payload):
    """Process one MQTT payload. Returns "saved", "duplicate" or "rejected"."""
    text = payload.decode("utf-8", errors="replace")

    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        readings_db.save_rejected(conn, text, "not valid json")
        return "rejected"

    ok, reason = validator.check_message(message)
    if not ok:
        readings_db.save_rejected(conn, text, reason)
        return "rejected"

    if readings_db.save_reading(conn, message):
        return "saved"
    return "duplicate"
