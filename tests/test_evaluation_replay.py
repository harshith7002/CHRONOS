"""
End-to-End Evaluation & Replay Harness tests.
"""

import pytest
from chronos.evaluation.harness import ReplayHarness


def test_full_travel_booking_scenario_replay():
    harness = ReplayHarness()
    report = harness.run_default_demo_scenario()

    # Verify key evaluation metrics
    assert report.task_completed is True
    assert report.stale_results_rejected >= 1
    assert report.stale_rejection_rate == 1.0
    assert report.duplicate_commits_detected == 0
    assert report.safety_compliance_rate == 1.0
    assert report.snapshots_created >= 2
