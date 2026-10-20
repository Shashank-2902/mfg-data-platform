import os
import sys

import psycopg
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")

# Let the tests import the modules of each service.
for folder in ["replayer", "ingest", "monitor", "scripts"]:
    sys.path.append(os.path.join(ROOT, folder))

import env_file  # noqa: E402

TEST_DB_NAME = "mfg_test"


def database_url_for_tests():
    """Same server as ADMIN_URL, but the separate database mfg_test."""
    return env_file.database_url().rsplit("/", 1)[0] + "/" + TEST_DB_NAME


@pytest.fixture(scope="session")
def database_url():
    """Create a fresh test database so the tests never touch your real data."""
    try:
        admin = psycopg.connect(env_file.database_url(), autocommit=True)
    except (psycopg.OperationalError, RuntimeError):
        pytest.skip("no database available (start it with: docker compose up -d timescaledb)")

    admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
    admin.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    admin.close()

    url = database_url_for_tests()
    with psycopg.connect(url, autocommit=True) as conn:
        with open(os.path.join(ROOT, "db", "init.sql"), encoding="utf-8") as f:
            conn.execute(f.read())
    return url


@pytest.fixture
def conn(database_url):
    """A connection to the test database with all tables empty."""
    connection = psycopg.connect(database_url, autocommit=True)
    connection.execute("TRUNCATE raw_readings, rejected_readings, outbox, incidents RESTART IDENTITY")
    yield connection
    connection.close()


def make_message(machine_id="M1", event_time="2026-01-01T00:00:00+00:00", **changes):
    """A valid message. Pass keyword arguments to change single fields."""
    message = {
        "machine_id": machine_id,
        "event_time": event_time,
        "udi": 1,
        "product_type": "M",
        "air_temp_k": 298.1,
        "process_temp_k": 308.6,
        "rotational_speed_rpm": 1551,
        "torque_nm": 42.8,
        "tool_wear_min": 0,
        "machine_failure": 0,
        "twf": 0,
        "hdf": 0,
        "pwf": 0,
        "osf": 0,
        "rnf": 0,
    }
    message.update(changes)
    return message
