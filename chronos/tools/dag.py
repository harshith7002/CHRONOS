"""
CHRONOS Dependency DAG & Selective Invalidation
Maintains tool execution dependencies and computes selective invalidation on intent shifts.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from chronos.protocol.schemas import CallStatus, ToolCall, ToolResult


class DAGNode(BaseModel):
    call_id: str
    tool_name: str
    snapshot_id: str
    branch_id: str = "main"
    arguments: Dict[str, Any] = Field(default_factory=dict)
    slot_bindings: Dict[str, Any] = Field(default_factory=dict, description="Slot key->value used for this call")
    upstream_call_ids: Set[str] = Field(default_factory=set)
    downstream_call_ids: Set[str] = Field(default_factory=set)
    status: CallStatus = CallStatus.PENDING
    result: Optional[ToolResult] = None
    reusable: bool = True


class ExecutionDAG:
    """
    Dependency Directed Acyclic Graph tracking tool calls, inputs, outputs, and downstream dependencies.
    """

    def __init__(self):
        self._nodes: Dict[str, DAGNode] = {}

    def add_node(
        self,
        call_id: str,
        tool_name: str,
        snapshot_id: str,
        branch_id: str,
        arguments: Dict[str, Any],
        slot_bindings: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
    ) -> DAGNode:
        upstreams = set(depends_on or [])
        node = DAGNode(
            call_id=call_id,
            tool_name=tool_name,
            snapshot_id=snapshot_id,
            branch_id=branch_id,
            arguments=arguments,
            slot_bindings=slot_bindings,
            upstream_call_ids=upstreams,
            downstream_call_ids=set(),
            status=CallStatus.PENDING,
        )
        self._nodes[call_id] = node

        # Link parent downstream sets
        for parent_id in upstreams:
            if parent_id in self._nodes:
                self._nodes[parent_id].downstream_call_ids.add(call_id)

        return node

    def get_node(self, call_id: str) -> Optional[DAGNode]:
        return self._nodes.get(call_id)

    def get_all_nodes(self) -> List[DAGNode]:
        return list(self._nodes.values())

    def update_status(self, call_id: str, status: CallStatus, result: Optional[ToolResult] = None) -> None:
        if call_id in self._nodes:
            self._nodes[call_id].status = status
            if result is not None:
                self._nodes[call_id].result = result

    def get_downstream_subgraph(self, call_id: str) -> Set[str]:
        """Collect all downstream dependent call_ids recursively."""
        visited: Set[str] = set()
        queue = [call_id]
        while queue:
            curr = queue.pop(0)
            if curr in self._nodes:
                for child_id in self._nodes[curr].downstream_call_ids:
                    if child_id not in visited:
                        visited.add(child_id)
                        queue.append(child_id)
        return visited

    def compute_selective_invalidation(
        self,
        modified_slots: Dict[str, Any],
        current_snapshot_id: str,
    ) -> Tuple[Set[str], Set[str]]:
        """
        Computes which nodes must be CANCELLED / INVALIDATED vs which can be PRESERVED as reusable.
        Returns: (to_invalidate_call_ids, to_preserve_call_ids)
        """
        to_invalidate: Set[str] = set()
        to_preserve: Set[str] = set()

        for call_id, node in self._nodes.items():
            # Check if this node directly used any modified slot with a changed value
            direct_slot_mismatch = False
            for slot_key, slot_val in node.slot_bindings.items():
                if slot_key in modified_slots and modified_slots[slot_key] != slot_val:
                    direct_slot_mismatch = True
                    break

            if direct_slot_mismatch:
                to_invalidate.add(call_id)
                # Invalidate all downstream dependents of this node
                downstream = self.get_downstream_subgraph(call_id)
                to_invalidate.update(downstream)

        # Everything else that is not invalidated can potentially be preserved
        for call_id in self._nodes:
            if call_id not in to_invalidate:
                to_preserve.add(call_id)

        return to_invalidate, to_preserve

    def get_active_nodes(self) -> List[DAGNode]:
        return [
            n for n in self._nodes.values()
            if n.status in (CallStatus.PENDING, CallStatus.DISPATCHED, CallStatus.RUNNING)
        ]

    def clear(self) -> None:
        self._nodes.clear()
