"""
Tests for Formal System Invariants and 20-Category Adversarial Matrix.
"""

import pytest
from chronos.evaluation.adversarial_matrix import AdversarialBenchmarkRunner
from chronos.evaluation.scaling_benchmarks import ScalingBenchmark
from chronos.evaluation.speculation_metrics import SpeculationAnalyzer
from chronos.core.invariants import SystemInvariants
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent


def test_formal_invariants_hold_under_normal_and_interrupted_runs():
    clock = VirtualClock(mode="stepped")
    agent = ChronosAgent(clock=clock)

    agent.process_user_input("Find flights to Delhi")
    agent.step_time(0.1)
    agent.process_user_input("Actually Mumbai")
    agent.force_inject_stale_result("c_old", "v1", "search_flights", [{"flight_id": "DEL-1"}])
    agent.step_time(0.5)
    agent.process_user_input("Book the cheapest one")
    agent.process_user_input("Yes confirm booking")

    # Verify formal invariants
    result = SystemInvariants.verify_all(agent.event_log, agent.state_mgr, agent.idempotency, agent.dag)
    assert result.passed is True
    assert len(result.violations) == 0
    assert len(result.invariants_verified) >= 6


def test_adversarial_matrix_execution():
    # Run matrix with 10 seeds per scenario (200 executions)
    summary = AdversarialBenchmarkRunner.run_matrix(seeds_per_scenario=10)
    assert summary.total_runs == 200
    assert summary.chronos_task_completion_rate == 1.0
    assert summary.chronos_total_stale_violations == 0
    assert summary.chronos_total_duplicate_commits == 0
    assert summary.chronos_total_invariant_violations == 0

    # Naive baseline must exhibit measurable safety & stale violations
    assert summary.naive_total_safety_violations > 0


def test_scaling_benchmarks_zero_violations():
    report = ScalingBenchmark.run_scaling_suite(tiers=[1, 5, 10, 25], iterations_per_tier=10)
    assert report.zero_violation_verified is True
    assert len(report.tiers) == 4
    for tier in report.tiers:
        assert tier.cancellation_latency_p50_ms >= 0.0
        assert tier.event_throughput_per_sec > 0.0


def test_speculation_reuse_metrics():
    clock = VirtualClock(mode="stepped")
    agent = ChronosAgent(clock=clock)
    agent.process_user_input("Find flights to Delhi")
    agent.step_time(0.5)
    report = SpeculationAnalyzer.analyze(agent.dag, agent.state_mgr)
    assert report.total_speculative_nodes >= 1
    assert report.speculation_reuse_rate >= 0.0
