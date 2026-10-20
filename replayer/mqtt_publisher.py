import json

import paho.mqtt.client as mqtt

TOPIC = "factory/readings"


def connect(host, port):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="replayer")
    client.connect(host, port)
    client.loop_start()
    return client


def publish(client, message):
    """Send one message with QoS 1 (the broker confirms it got it)."""
    return client.publish(TOPIC, json.dumps(message), qos=1)


def close(client, last_info):
    # Wait until the last message is confirmed before we disconnect.
    if last_info is not None:
        last_info.wait_for_publish()
    client.loop_stop()
    client.disconnect()
