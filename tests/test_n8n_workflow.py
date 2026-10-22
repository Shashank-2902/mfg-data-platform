"""Checks on the n8n workflow file. They only read the JSON (and use the test database
for the decision query), so no container is needed."""
import json
import os
import re
import shutil
import subprocess

import pytest

PATH = os.path.join(os.path.dirname(__file__), "..", "n8n", "workflows", "alert_flow.json")
TELEGRAM_NODES = ["Telegram high", "Telegram other"]
MARK = "Mark outbox delivered"


@pytest.fixture(scope="module")
def workflow():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def node(workflow, name):
    return next(n for n in workflow["nodes"] if n["name"] == name)


def targets(workflow, name):
    """All nodes that `name` sends its output to, as (output index, target name)."""
    result = []
    for index, outputs in enumerate(workflow["connections"].get(name, {}).get("main", [])):
        result += [(index, link["node"]) for link in outputs]
    return result


def sources_of(workflow, name):
    return sorted(source for source in workflow["connections"] if name in [t for _, t in targets(workflow, source)])


# ---------- the file itself ----------

def test_the_workflow_keeps_its_id_and_the_response_mode(workflow):
    assert workflow["id"] == "mfgalertflow01"
    # With this mode n8n answers the webhook with HTTP 500 when a node fails before the answer node.
    assert node(workflow, "Webhook")["parameters"]["responseMode"] == "responseNode"


def test_every_connection_points_to_an_existing_node(workflow):
    names = {n["name"] for n in workflow["nodes"]}
    for source, outputs in workflow["connections"].items():
        assert source in names
        for output in outputs["main"]:
            for link in output:
                assert link["node"] in names, (source, link["node"])


def test_node_names_and_ids_are_unique(workflow):
    names = [n["name"] for n in workflow["nodes"]]
    ids = [n["id"] for n in workflow["nodes"]]
    assert len(set(names)) == len(names) and len(set(ids)) == len(ids)


def test_the_workflow_file_holds_no_secrets(workflow):
    text = json.dumps(workflow)
    assert not re.search(r"\d{8,10}:[A-Za-z0-9_-]{30,}", text)           # a Telegram bot token
    assert "accessToken" not in text and "password" not in text.lower()
    for n in workflow["nodes"]:
        for credential in n.get("credentials", {}).values():
            assert set(credential) == {"id", "name"}                      # only a reference, never a value


# ---------- delivered only after Telegram worked ----------

def test_the_outbox_is_marked_only_after_a_telegram_node_or_for_a_real_duplicate(workflow):
    assert sources_of(workflow, MARK) == sorted(TELEGRAM_NODES + ["Send the message?"])
    # From the decision node only the "no" output (index 1) may go straight to marking.
    assert [i for i, t in targets(workflow, "Send the message?") if t == MARK] == [1]
    assert [t for i, t in targets(workflow, "Send the message?") if i == 0] == ["Switch on severity"]


def test_the_monitor_gets_its_answer_only_after_marking(workflow):
    assert targets(workflow, MARK) == [(0, "Answer the monitor")]
    assert sources_of(workflow, "Answer the monitor") == [MARK]


def test_a_failing_telegram_node_stops_the_workflow(workflow):
    """No error handling on the Telegram nodes: a failure ends the run before the answer node,
    which makes n8n answer the webhook with an error status."""
    for name in TELEGRAM_NODES:
        n = node(workflow, name)
        assert not n.get("continueOnFail")
        assert n.get("onError", "stopWorkflow") == "stopWorkflow"
        assert not n.get("retryOnFail")


def test_the_decision_uses_the_send_flag(workflow):
    condition = node(workflow, "Send the message?")["parameters"]["conditions"]["conditions"][0]
    assert condition["leftValue"] == "={{ $json.send }}"
    assert condition["operator"]["type"] == "boolean"


# ---------- the text ----------

def test_the_text_is_sent_as_html_so_underscores_survive(workflow):
    for name in TELEGRAM_NODES:
        parameters = node(workflow, name)["parameters"]
        assert parameters["additionalFields"]["parse_mode"] == "HTML"
        text = parameters["text"]
        assert "&amp;" in text and "&lt;" in text and "&gt;" in text    # the HTML special characters are escaped
        assert "/_/" not in text and "\\_" not in text                  # the underscore is left alone


def test_the_text_is_one_expression_so_no_space_depends_on_text_next_to_braces(workflow):
    """n8n 1.70.3 lost the space in 'ALERT {{ ... }}' at run time. The whole text is now one expression."""
    for name, label in [("Telegram high", "ALERT"), ("Telegram other", "Warning")]:
        text = node(workflow, name)["parameters"]["text"]
        assert text.startswith("={{ '" + label + " ' + String(")
        assert text.endswith(" }}")
        assert text.count("{{") == 1 and text.count("}}") == 1
        assert ") + ': ' + String(" in text


NODE_HELPER = """
const text = process.argv[1];
const body = JSON.parse(process.argv[2]);
const $ = () => ({ item: { json: { body } } });
const expression = text.slice(1).trim().slice(2, -2);
process.stdout.write(String(eval(expression)));
"""


def rendered_text(workflow, name, body):
    text = node(workflow, name)["parameters"]["text"]
    result = subprocess.run(["node", "-e", NODE_HELPER, text, json.dumps(body)], capture_output=True, text=True, check=True)
    return result.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_expression_logic_keeps_underscores_and_the_space_and_escapes_html(workflow):
    """This runs the expression as plain JavaScript. It is not n8n's own evaluator."""
    body = {"machine_id": "M4", "message": "air_temp_k = 0.0 is outside 270 to 330"}
    assert rendered_text(workflow, "Telegram high", body) == "ALERT M4: air_temp_k = 0.0 is outside 270 to 330"
    assert rendered_text(workflow, "Telegram other", body) == "Warning M4: air_temp_k = 0.0 is outside 270 to 330"

    body = {"machine_id": "M1", "message": "a<b & c>d"}
    assert rendered_text(workflow, "Telegram high", body) == "ALERT M1: a&lt;b &amp; c&gt;d"


# ---------- the decision query, run on the test database ----------

def decision_sql(workflow):
    query = node(workflow, "Open incident")["parameters"]["query"]
    return re.sub(r"\$(\d)", r"%(p\1)s", query)


def new_outbox_row(conn, machine="M4", incident_type="out_of_range"):
    return conn.execute(
        "INSERT INTO outbox (machine_id, incident_type, severity, message) VALUES (%s, %s, 'high', 'x') RETURNING id",
        (machine, incident_type),
    ).fetchone()[0]


def run_decision(conn, workflow, outbox_id, machine="M4", incident_type="out_of_range"):
    params = {"p1": machine, "p2": incident_type, "p3": "high", "p4": "x", "p5": outbox_id}
    return conn.execute(decision_sql(workflow), params).fetchone()[0]


def mark_delivered(conn, outbox_id):
    conn.execute("UPDATE outbox SET delivered_at = now() WHERE id = %s", (outbox_id,))


def incident_count(conn):
    return conn.execute("SELECT count(*) FROM incidents").fetchone()[0]


def test_a_first_attempt_creates_the_incident_and_says_send(conn, workflow):
    outbox_id = new_outbox_row(conn)
    assert run_decision(conn, workflow, outbox_id) is True
    assert conn.execute("SELECT count(*) FROM incidents WHERE outbox_id = %s", (outbox_id,)).fetchone()[0] == 1


def test_a_retry_after_a_failed_telegram_call_sends_again_without_a_second_incident(conn, workflow):
    outbox_id = new_outbox_row(conn)
    assert run_decision(conn, workflow, outbox_id) is True       # first attempt, Telegram then failed
    assert run_decision(conn, workflow, outbox_id) is True       # the retry: send again
    assert incident_count(conn) == 1


def test_a_retry_after_the_incident_was_resolved_still_sends_and_adds_no_incident(conn, workflow):
    outbox_id = new_outbox_row(conn)
    run_decision(conn, workflow, outbox_id)
    conn.execute("UPDATE incidents SET status = 'resolved'")
    assert run_decision(conn, workflow, outbox_id) is True
    assert incident_count(conn) == 1


def test_a_real_duplicate_from_another_row_is_skipped(conn, workflow):
    first = new_outbox_row(conn)
    run_decision(conn, workflow, first)
    mark_delivered(conn, first)
    second = new_outbox_row(conn)
    assert run_decision(conn, workflow, second) is False
    assert incident_count(conn) == 1


def test_a_duplicate_is_skipped_even_while_the_first_row_is_still_undelivered(conn, workflow):
    first = new_outbox_row(conn)
    run_decision(conn, workflow, first)                          # Telegram for the first row failed so far
    second = new_outbox_row(conn)
    assert run_decision(conn, workflow, second) is False
    assert incident_count(conn) == 1


def test_a_second_call_for_an_already_delivered_row_is_skipped(conn, workflow):
    outbox_id = new_outbox_row(conn)
    run_decision(conn, workflow, outbox_id)
    mark_delivered(conn, outbox_id)
    assert run_decision(conn, workflow, outbox_id) is False


def test_a_different_machine_gets_its_own_incident(conn, workflow):
    run_decision(conn, workflow, new_outbox_row(conn, "M1", "silence"), "M1", "silence")
    assert run_decision(conn, workflow, new_outbox_row(conn, "M2", "silence"), "M2", "silence") is True
    assert incident_count(conn) == 2
