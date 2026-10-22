import json
import threading
import urllib.error
import urllib.request

import fake_telegram


def test_the_first_n_requests_fail_and_later_ones_succeed():
    counter = fake_telegram.RequestCounter(fail_first=2)
    assert [counter.next_request() for _ in range(4)] == [(1, True), (2, True), (3, False), (4, False)]


def test_with_zero_nothing_fails():
    counter = fake_telegram.RequestCounter(fail_first=0)
    assert all(not counter.next_request()[1] for _ in range(3))


def post(port, text, parse_mode="HTML"):
    body = json.dumps({"chat_id": "1", "text": text, "parse_mode": parse_mode}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/botTOKEN/sendMessage", data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_the_server_answers_500_once_then_200_and_prints_one_line_per_request(capsys):
    server = fake_telegram.make_server(0, fail_first=1)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert post(port, "ALERT M4: air_temp_k = 0.0") == 500
        assert post(port, "ALERT M4: air_temp_k = 0.0") == 200
    finally:
        server.shutdown()
        server.server_close()

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("TELEGRAM REQUEST")]
    assert lines == [
        "TELEGRAM REQUEST 1 parse_mode=HTML status=500 text=ALERT M4: air_temp_k = 0.0",
        "TELEGRAM REQUEST 2 parse_mode=HTML status=200 text=ALERT M4: air_temp_k = 0.0",
    ]
