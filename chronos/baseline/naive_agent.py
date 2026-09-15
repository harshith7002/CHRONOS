"""
CHRONOS Baseline: Naive Unversioned Agent
Implements traditional single-mutable-state agent architecture without temporal versioning,
dependency DAGs, stale result rejection, or idempotency deduplication.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import time


class NaiveAgent:
    """
    Naive baseline agent:
    - Single mutable state dictionary
    - Unversioned asynchronous tool execution
    - Overwrites state on any arriving tool result (vulnerable to stale contamination)
    - No idempotency ledger (vulnerable to duplicate state writes)
    - No 4-stage commit gate (vulnerable to executing without confirmation)
    """

    def __init__(self):
        self.state: Dict[str, Any] = {
            "destination": None,
            "date": None,
            "flights": [],
            "selected_flight": None,
            "booked_flights": [],
        }
        self.active_tasks: List[Dict[str, Any]] = []
        self.dispatched_tool_calls_count: int = 0
        self.duplicate_writes_count: int = 0
        self.stale_state_violations_count: int = 0
        self.unconfirmed_commits_count: int = 0

    def process_user_input(self, text: str) -> Dict[str, Any]:
        cleaned = text.lower()

        # Update destination if mentioned
        for city in ["mumbai", "delhi", "bangalore", "chennai", "goa"]:
            if city in cleaned:
                self.state["destination"] = city.capitalize()

        # Update date
        for d in ["tomorrow", "friday", "today", "saturday"]:
            if d in cleaned:
                self.state["date"] = d.capitalize()

        # If booking request
        if "book" in cleaned:
            # Naive agent books directly without 4-stage confirmation gate
            flight = self.state.get("selected_flight") or (self.state["flights"][0] if self.state["flights"] else {"flight_id": "DEFAULT-101"})
            
            # Record duplicate if already booked
            if any(b.get("flight_id") == flight.get("flight_id") for b in self.state["booked_flights"]):
                self.duplicate_writes_count += 1

            self.state["booked_flights"].append(flight)
            return {"action": "booked", "flight": flight}

        # If search request
        if self.state["destination"]:
            # Dispatch unversioned search
            call = {
                "tool": "search_flights",
                "destination": self.state["destination"],
                "dispatched_at": time.time(),
            }
            self.active_tasks.append(call)
            self.dispatched_tool_calls_count += 1
            return {"action": "searching", "destination": self.state["destination"]}

        return {"action": "idle"}

    def receive_async_tool_result(self, tool_name: str, origin_destination: str, output: Any) -> None:
        """
        Simulates an asynchronous background tool returning out-of-order.
        Naive agent blindly mutates active state!
        """
        if tool_name == "search_flights":
            # State contamination check: if destination was updated to something else, this is a stale mutation
            if self.state["destination"] and self.state["destination"].lower() != origin_destination.lower():
                self.stale_state_violations_count += 1

            # Blindly overwrite active flights!
            self.state["flights"] = output
            if output:
                self.state["selected_flight"] = output[0]

    def reset(self) -> None:
        self.state = {
            "destination": None,
            "date": None,
            "flights": [],
            "selected_flight": None,
            "booked_flights": [],
        }
        self.active_tasks.clear()
        self.dispatched_tool_calls_count = 0
        self.duplicate_writes_count = 0
        self.stale_state_violations_count = 0
        self.unconfirmed_commits_count = 0
