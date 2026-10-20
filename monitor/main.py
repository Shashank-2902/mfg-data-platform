import os
import time

import psycopg

import monitor_db
import n8n_client
import rules
import runner

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mfg:mfg@localhost:5432/mfg")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/incident")


def send_to_n8n(payload):
    n8n_client.send(N8N_WEBHOOK_URL, payload)


def main():
    print(f"Monitor started. Checking every {rules.CHECK_EVERY_SECONDS} seconds.")
    conn = None
    while True:
        try:
            if conn is None or conn.closed:
                conn = monitor_db.connect(DATABASE_URL)
            runner.run_once(conn, send_to_n8n)
        except psycopg.Error as error:
            print(f"Database error: {error}")
            conn = None
        time.sleep(rules.CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
