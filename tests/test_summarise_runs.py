import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "benchmark"))

import summarise_runs  # noqa: E402


def test_the_committed_runs_have_five_runs_per_fault():
    runs = summarise_runs.read_runs()
    for fault in summarise_runs.FAULTS:
        assert len([r for r in runs if r["fault"] == fault]) == 5, fault


def test_the_committed_runs_only_hold_measurements():
    allowed = {"fault", "rows_lost", "run_seconds", "delay", "false_alarms"}
    for run in summarise_runs.read_runs():
        assert set(run) <= allowed


def test_the_table_is_built_from_the_saved_runs(capsys):
    summarise_runs.main()
    table = capsys.readouterr().out
    assert "| silence | 5 |" in table and "| out_of_range | 5 |" in table
