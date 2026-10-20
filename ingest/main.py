import os
import time

import paho.mqtt.client as mqtt
import psycopg

import handler
import readings_db

TOPIC = "factory/readings"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mfg:mfg@localhost:5432/mfg")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

counts = {"saved": 0, "duplicate": 0, "rejected": 0}
connection = {"conn": None}


def get_connection():
    """Return the database connection. Wait and retry until the database is there."""
    while connection["conn"] is None or connection["conn"].closed:
        try:
            connection["conn"] = readings_db.connect(DATABASE_URL)
        except psycopg.Error as error:
            print(f"Database not ready ({error}). Trying again in 2 seconds.")
            time.sleep(2)
    return connection["conn"]


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to the broker.")
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    # If the database is down we keep retrying here. The broker holds the other
    # messages in its queue, so no reading is lost.
    while True:
        try:
            result = handler.handle_payload(get_connection(), msg.payload)
            break
        except psycopg.Error as error:
            print(f"Database error ({error}). Trying again in 2 seconds.")
            time.sleep(2)

    counts[result] += 1
    total = sum(counts.values())
    if total % 500 == 0:
        print(f"Messages so far: {counts}")


def main():
    # A fixed client id and clean_session=False make the broker queue messages while we are away.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingest", clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
