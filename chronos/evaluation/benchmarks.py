"""
CHRONOS Latency & Micro-Benchmarking Engine
Measures real empirical latency distributions (p50, p95, p99) for Fast Path, Cancellation, and Snapshot Evolution.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List
import numpy as np
from pydantic import BaseModel, Field

from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.protocol.events import InterruptionLevel


class LatencyDistribution(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    samples_count: int


class BenchmarkReport(BaseModel):
    fast_path_ack_latency: LatencyDistribution
    interruption_cancellation_latency: LatencyDistribution
    snapshot_evolution_latency: LatencyDistribution
    idempotency_check_latency: LatencyDistribution
    chained_dag_execution_latency: LatencyDistribution


class LatencyBenchmark:
    """
    Executes microsecond-precision benchmarks across core control plane critical paths.
    """

    @staticmethod
    def _compute_stats(times_seconds: List[float]) -> LatencyDistribution:
        ms = [t * 1000.0 for t in times_seconds]
        if not ms:
            return LatencyDistribution(
                p50_ms=0, p95_ms=0, p99_ms=0, mean_ms=0, min_ms=0, max_ms=0, samples_count=0
            )
        return LatencyDistribution(
            p50_ms=round(float(np.percentile(ms, 50)), 3),
            p95_ms=round(float(np.percentile(ms, 95)), 3),
            p99_ms=round(float(np.percentile(ms, 99)), 3),
            mean_ms=round(float(np.mean(ms)), 3),
            min_ms=round(float(np.min(ms)), 3),
            max_ms=round(float(np.max(ms)), 3),
            samples_count=len(ms),
        )

    @classmethod
    def run_full_benchmark(cls, iterations: int = 1000) -> BenchmarkReport:
        clock = VirtualClock(mode="stepped")
        agent = ChronosAgent(clock=clock)

        # 1. Benchmark Fast Path Acknowledgment
        fast_path_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            agent.floor_controller.generate_fast_ack(
                level=InterruptionLevel.LEVEL_1,
                snapshot_id="v1",
                slot_updates={"destination": "Mumbai"},
            )
            fast_path_times.append(time.perf_counter() - t0)

        # 2. Benchmark Interruption & Cancellation Propagation
        cancellation_times = []
        for i in range(iterations):
            agent.scheduler.dispatch(
                tool_name="search_flights",
                arguments={"destination": "Delhi"},
                snapshot_id=f"v_bench_{i}",
            )
            t0 = time.perf_counter()
            agent.interruption_controller.handle_interruption("Actually Mumbai")
            cancellation_times.append(time.perf_counter() - t0)

        # 3. Benchmark Snapshot Evolution
        snapshot_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            agent.state_mgr.create_new_snapshot(
                timestamp=clock.now(),
                slot_updates={"destination": "Bangalore", "date": "Friday"},
            )
            snapshot_times.append(time.perf_counter() - t0)

        # 4. Benchmark Idempotency Ledger Check
        idempotency_times = []
        for i in range(iterations):
            key = f"idem_key_bench_{i}"
            agent.idempotency.register_or_get(
                idempotency_key=key,
                call_id=f"call_{i}",
                snapshot_id="v1",
                tool_name="book_flight",
                arguments={"flight_id": "BOM-101"},
                created_at=clock.now(),
            )
            t0 = time.perf_counter()
            agent.idempotency.has_committed(key)
            idempotency_times.append(time.perf_counter() - t0)

        # 5. Benchmark Chained DAG Invalidation
        dag_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            agent.dag.compute_selective_invalidation(
                modified_slots={"destination": "Goa"},
                current_snapshot_id="v_latest",
            )
            dag_times.append(time.perf_counter() - t0)

        return BenchmarkReport(
            fast_path_ack_latency=cls._compute_stats(fast_path_times),
            interruption_cancellation_latency=cls._compute_stats(cancellation_times),
            snapshot_evolution_latency=cls._compute_stats(snapshot_times),
            idempotency_check_latency=cls._compute_stats(idempotency_times),
            chained_dag_execution_latency=cls._compute_stats(dag_times),
        )
