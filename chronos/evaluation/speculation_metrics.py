"""
CHRONOS Speculation Efficiency & Branch Lifecycle Metrics
Quantifies computational reuse vs waste across intent version transitions and branch lifecycles.
"""

from __future__ import annotations
from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field
from chronos.protocol.schemas import CallStatus
from chronos.tools.dag import ExecutionDAG, DAGNode
from chronos.state.branch_manager import TemporalStateManager


class SpeculationEfficiencyReport(BaseModel):
    total_speculative_nodes: int
    reused_nodes_count: int
    wasted_nodes_count: int
    speculation_reuse_rate: float = Field(..., description="Proportion of speculative computation preserved (0.0 to 1.0)")
    speculation_waste_rate: float = Field(..., description="Proportion of speculative computation discarded")
    branches_created: int
    branches_superseded: int
    branches_active: int
    branches_discarded: int


class SpeculationAnalyzer:
    """
    Computes rigorous speculation efficiency metrics from execution DAG and branch state.
    """

    @staticmethod
    def analyze(dag: ExecutionDAG, state_mgr: TemporalStateManager) -> SpeculationEfficiencyReport:
        nodes = dag.get_all_nodes()
        total_speculative = len(nodes)
        reused = 0
        wasted = 0

        for node in nodes:
            if node.status in (CallStatus.CANCELLED, CallStatus.STALE_REJECTED, CallStatus.FAILED):
                wasted += 1
            elif node.status == CallStatus.COMPLETED and node.reusable:
                reused += 1

        reuse_rate = round(reused / max(1, total_speculative), 4)
        waste_rate = round(wasted / max(1, total_speculative), 4)

        branches = state_mgr.get_all_branches()
        created = len(branches)
        superseded = sum(1 for b in branches if b["status"] == "SUPERSEDED")
        active = sum(1 for b in branches if b["status"] == "ACTIVE")
        discarded = sum(1 for b in branches if b["status"] == "DISCARDED")

        return SpeculationEfficiencyReport(
            total_speculative_nodes=total_speculative,
            reused_nodes_count=reused,
            wasted_nodes_count=wasted,
            speculation_reuse_rate=reuse_rate,
            speculation_waste_rate=waste_rate,
            branches_created=created,
            branches_superseded=superseded,
            branches_active=active,
            branches_discarded=discarded,
        )
