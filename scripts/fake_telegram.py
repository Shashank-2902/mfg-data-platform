"""A tiny stand-in for the Telegram Bot API, for demos without a real bot.

It answers sendMessage like Telegram does and prints the text it receives.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeTelegram(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        print(f"TELEGRAM MESSAGE: {body}", flush=True)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        reply = {
            "ok": True,
            "result": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": data.get("chat_id", 0), "type": "private"},
                "text": data.get("text", ""),
            },
        }
        payload = json.dumps(reply).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Fake Telegram listening on port 8081", flush=True)
    HTTPServer(("0.0.0.0", 8081), FakeTelegram).serve_forever()
