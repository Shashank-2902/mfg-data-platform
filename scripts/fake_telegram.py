"""A tiny stand-in for the Telegram Bot API, for demos without a real bot.

It answers sendMessage like Telegram does and prints one line per request:
the request number, the parse_mode if there is one, the answer status and the text.

FAKE_TELEGRAM_FAIL_FIRST=N makes the first N requests fail with HTTP 500, so you can
test what happens when Telegram is down. Later requests succeed.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class RequestCounter:
    """Counts requests and says which of them must fail."""

    def __init__(self, fail_first=0):
        self.fail_first = fail_first
        self.count = 0
        self.lock = threading.Lock()

    def next_request(self):
        """Return (request number, True if this request must fail)."""
        with self.lock:
            self.count += 1
            return self.count, self.count <= self.fail_first


class FakeTelegram(BaseHTTPRequestHandler):
    counter = RequestCounter()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        number, must_fail = self.counter.next_request()
        status = 500 if must_fail else 200
        parse_mode = data.get("parse_mode")
        mode = f" parse_mode={parse_mode}" if parse_mode else ""
        print(f"TELEGRAM REQUEST {number}{mode} status={status} text={data.get('text', '')}", flush=True)

        if must_fail:
            reply = {"ok": False, "error_code": 500, "description": "Internal Server Error (fake, on purpose)"}
        else:
            reply = {
                "ok": True,
                "result": {
                    "message_id": number,
                    "date": 0,
                    "chat": {"id": data.get("chat_id", 0), "type": "private"},
                    "text": data.get("text", ""),
                },
            }
        payload = json.dumps(reply).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def make_server(port, fail_first=0):
    """A server whose first `fail_first` requests fail. Each server has its own counter."""
    handler = type("Handler", (FakeTelegram,), {"counter": RequestCounter(fail_first)})
    return HTTPServer(("0.0.0.0", port), handler)


if __name__ == "__main__":
    fail_first = int(os.getenv("FAKE_TELEGRAM_FAIL_FIRST", "0") or 0)
    print(f"Fake Telegram listening on port 8081. The first {fail_first} requests will fail.", flush=True)
    make_server(8081, fail_first).serve_forever()
