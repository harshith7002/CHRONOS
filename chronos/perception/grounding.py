"""
CHRONOS Multimodal Grounding & Entity Resolver
Resolves references (e.g. 'the cheapest one', 'the morning flight', 'this option') to concrete entities.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


class MultimodalGrounder:
    """
    Grounds linguistic and deictic references against active tool results and contextual entities.
    """

    @staticmethod
    def ground_flight_selection(user_query: str, flight_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Resolve flight from user utterance."""
        if not flight_list:
            return None

        q = user_query.lower()
        if "cheapest" in q or "lowest price" in q or "best price" in q:
            return min(flight_list, key=lambda f: f.get("price", float("inf")))

        if "earliest" in q or "morning" in q or "first" in q:
            # Sort by time or default to first
            return flight_list[0]

        if "second" in q and len(flight_list) > 1:
            return flight_list[1]

        if "last" in q:
            return flight_list[-1]

        # By default return the best candidate
        return flight_list[0]
