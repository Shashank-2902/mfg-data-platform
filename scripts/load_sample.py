"""Load rows straight into the database without MQTT.

Handy for trying dbt and Grafana quickly, and for the CI pipeline.
    python scripts/load_sample.py --rows 10000
"""
import argparse
import os
import sys

# Reuse the code of the replayer and the ingest service.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(HERE, "..", "replayer"))
sys.path.append(os.path.join(HERE, "..", "ingest"))

import data_reader  # noqa: E402
import env_file  # noqa: E402
import message_builder  # noqa: E402
import readings_db  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--csv", default=os.path.join(HERE, "..", "data", "ai4i2020.csv"))
    args = parser.parse_args()

    rows = data_reader.read_rows(args.csv)
    conn = readings_db.connect(env_file.database_url())

    new_rows = 0
    for index in range(args.rows):
        message = message_builder.build_message(rows[index % len(rows)], index)
        if readings_db.save_reading(conn, message):
            new_rows += 1
    print(f"Loaded {new_rows} new rows ({args.rows - new_rows} were already there).")


if __name__ == "__main__":
    main()
