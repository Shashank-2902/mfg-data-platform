"""Print the live results table from the saved runs, without Docker.

    python benchmark/summarise_runs.py
"""
import json
import os

import live_fault_test

FAULTS = ["none", "silence", "sensor_stuck", "out_of_range"]


def read_runs(path=live_fault_test.SAVE_FILE):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summaries_from(runs):
    return [live_fault_test.summarize(fault, [r for r in runs if r["fault"] == fault]) for fault in FAULTS]


def main():
    live_fault_test.print_table(summaries_from(read_runs()))


if __name__ == "__main__":
    main()
