import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "benchmark"))

import detection_delay  # noqa: E402


def results_by_fault():
    return {r["fault"]: r for r in detection_delay.measure()}


def test_monitor_catches_every_fault():
    results = results_by_fault()
    for fault in ["silence", "sensor_stuck", "out_of_range"]:
        assert results[fault]["monitor_delay"] is not None


def test_baseline_only_catches_silence():
    results = results_by_fault()
    assert results["silence"]["baseline_delay"] is not None
    assert results["sensor_stuck"]["baseline_delay"] is None
    assert results["out_of_range"]["baseline_delay"] is None


def test_clean_run_has_no_false_alarms():
    clean = results_by_fault()["none (clean run)"]
    assert clean["monitor_false_alarms"] == 0
    assert clean["baseline_false_alarms"] == 0


def test_silence_is_found_after_the_60_second_limit():
    delay = results_by_fault()["silence"]["monitor_delay"]
    assert 60 <= delay <= 70
