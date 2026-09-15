"""
Tests for Chained DAG invalidation, Adversarial Stale Injection, Multimodal Grounding, and Latency Benchmarking.
"""

import pytest
from chronos.evaluation.harness import ReplayHarness
from chronos.evaluation.benchmarks import LatencyBenchmark


def test_chained_dag_cascade_invalidation():
    harness = ReplayHarness()
    result = harness.run_chained_dag_invalidation_scenario()
    assert result["status"] == "ok"
    assert "call_filter_v1" in result["invalidated_nodes"]
    assert "call_select_v1" in result["invalidated_nodes"]
    assert result["current_snapshot"] == "v2"


def test_adversarial_stale_booking_prevention():
    harness = ReplayHarness()
    result = harness.run_adversarial_stale_booking_injection_scenario()
    assert result["status"] == "blocked"
    assert result["commit_prevented"] is True
    assert result["token_state"] == "REJECTED"


def test_multimodal_vision_correction():
    harness = ReplayHarness()
    result = harness.run_multimodal_vision_correction_scenario()
    assert result["status"] == "corrected"
    assert result["corrected_slots"]["indicator_type"] == "power_led"
    assert result["cancelled_tools_count"] >= 1


def test_latency_benchmarks_metrics():
    report = LatencyBenchmark.run_full_benchmark(iterations=100)
    assert report.fast_path_ack_latency.samples_count == 100
    assert report.fast_path_ack_latency.p50_ms >= 0.0
    assert report.interruption_cancellation_latency.p50_ms >= 0.0
    assert report.snapshot_evolution_latency.p50_ms >= 0.0
    assert report.idempotency_check_latency.p50_ms >= 0.0


def test_naive_vs_chronos_comparison():
    harness = ReplayHarness()
    res = harness.run_naive_vs_chronos_comparison()
    # Naive agent failed
    assert res["naive_baseline"]["state_contaminated"] is True
    assert res["naive_baseline"]["duplicate_commits_count"] > 0
    assert res["naive_baseline"]["safety_score"] == 0.0

    # CHRONOS succeeded
    assert res["chronos_control_plane"]["state_contaminated"] is False
    assert res["chronos_control_plane"]["duplicate_commits_count"] == 0
    assert res["chronos_control_plane"]["actual_commits_count"] == 1
    assert res["chronos_control_plane"]["safety_score"] == 1.0
