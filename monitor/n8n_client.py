import requests


def send(url, payload):
    """Post the alert to the n8n webhook. Raises an error if n8n is down or answers with an error."""
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
