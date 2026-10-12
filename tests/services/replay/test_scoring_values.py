"""Unit tests for ground-truth scoring and config value helpers."""
import math

from app.services.replay.capture import summarize
from app.services.replay.scoring import overall_status, rank_key, score_run
from app.services.replay.values import same_value, value_for_config


def _summary(mean, std=0.5, count=10):
    return {"nodes": {"n": {"values": {"len": {"count": count, "mean": mean, "std": std, "min": 0, "max": 9, "last": 1}}}}}


def _target(expected=6.0, tolerance=0.1, key="len", tid="t1"):
    return {"id": tid, "node_id": "n", "metric_key": key, "expected": expected, "tolerance": tolerance, "label": ""}


class TestScoreRun:
    def test_pass_within_tolerance(self):
        s = score_run(_summary(6.05), [_target()])
        t = s["targets"][0]
        assert s["overall"] == "pass" and t["status"] == "pass"
        assert math.isclose(t["error"], 0.05) and math.isclose(t["pct_error"], 0.05 / 6 * 100)
        assert t["std"] == 0.5

    def test_fail_beyond_tolerance(self):
        assert score_run(_summary(6.5), [_target()])["overall"] == "fail"

    def test_negative_error_is_reported_signed(self):
        t = score_run(_summary(5.0), [_target(tolerance=2)])["targets"][0]
        assert t["error"] == -1.0 and t["abs_error"] == 1.0

    def test_without_tolerance_it_is_informational(self):
        s = score_run(_summary(9), [_target(tolerance=None)])
        assert s["overall"] == "info" and s["targets"][0]["status"] == "info"

    def test_missing_metric(self):
        s = score_run(_summary(6), [_target(key="nope")])
        assert s["overall"] == "missing" and s["targets"][0]["value"] is None

    def test_no_targets_means_nothing_to_score(self):
        assert score_run(_summary(6), [])["overall"] is None

    def test_zero_expected_has_no_percentage(self):
        assert score_run(_summary(1), [_target(expected=0, tolerance=5)])["targets"][0]["pct_error"] is None

    def test_fail_beats_missing_beats_pass(self):
        assert overall_status([{"status": "pass"}, {"status": "fail"}, {"status": "missing"}]) == "fail"
        assert overall_status([{"status": "pass"}, {"status": "missing"}]) == "missing"
        assert overall_status([{"status": "pass"}, {"status": "info"}]) == "pass"


def test_rank_key_orders_by_total_error_with_missing_last():
    close = score_run(_summary(6.01), [_target()])
    far = score_run(_summary(7.0), [_target()])
    missing = score_run(_summary(6), [_target(key="nope")])
    assert sorted([far, missing, close], key=rank_key) == [close, far, missing]


def test_summarize_reports_population_std():
    capture = {
        "nodes": {"n": {"name": "N", "type": "t", "frames": [
            {"frame": i, "timestamp": None, "points": 1, "values": {"v": float(v)}}
            for i, v in enumerate([2, 4, 4, 4, 5, 5, 7, 9])
        ]}},
        "saved_results": [], "errors": [],
    }
    stats = summarize(capture)["nodes"]["n"]["values"]["v"]
    assert stats["mean"] == 5.0 and math.isclose(stats["std"], 2.0)


class TestValues:
    def test_numeric_strings_equal_numbers(self):
        assert same_value("0.7", 0.7) and same_value(50, "50") and same_value("1e-3", 0.001)

    def test_different_values(self):
        assert not same_value("0.7", 1.5) and not same_value("a", "b")

    def test_booleans_are_not_numbers(self):
        assert not same_value(True, 1) and same_value(True, True)

    def test_lists_compare_elementwise(self):
        assert same_value([1, "2"], ["1", 2]) and not same_value([1, 2], [1, 2, 3])

    def test_config_keeps_string_style_for_numeric_strings(self):
        assert value_for_config("0.7", 1.5) == "1.5"
        assert value_for_config(0.7, 1.5) == 1.5
        assert value_for_config("abc", 1.5) == 1.5
        assert value_for_config("5", True) is True
