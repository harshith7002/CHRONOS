"""
CHRONOS Multimodal Grounding & Entity Resolver
Bridges visual scene observations, sensor metadata, and user corrections to intent slots and execution DAG.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VisualObject(BaseModel):
    object_id: str
    label: str
    bounding_box: Optional[List[float]] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class VisualScene(BaseModel):
    scene_id: str
    timestamp: float
    detected_objects: List[VisualObject] = Field(default_factory=list)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


class MultimodalGrounder:
    """
    Grounds visual objects, sensor telemetry, and deictic user references into intent slots.
    """

    @staticmethod
    def ground_flight_selection(user_query: str, flight_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Resolve flight candidate from user utterance."""
        if not flight_list:
            return None

        q = user_query.lower()
        if "cheapest" in q or "lowest price" in q or "best price" in q:
            return min(flight_list, key=lambda f: f.get("price", float("inf")))

        if "earliest" in q or "morning" in q or "first" in q:
            return flight_list[0]

        if "second" in q and len(flight_list) > 1:
            return flight_list[1]

        if "last" in q:
            return flight_list[-1]

        return flight_list[0]

    @staticmethod
    def resolve_multimodal_correction(
        scene: VisualScene,
        user_utterance: str,
        current_slots: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Processes visual scene context with user voice correction.
        Example: Scene shows indicator LED. User says: "No, that's actually the power LED indicator."
        Revises intent slots, triggering selective DAG invalidation.
        """
        updated_slots = dict(current_slots)
        text = user_utterance.lower()

        for obj in scene.detected_objects:
            lbl = obj.label.lower()
            if "power" in text and ("led" in lbl or "light" in lbl or "indicator" in lbl):
                updated_slots["indicator_type"] = "power_led"
                updated_slots["severity"] = "normal_operational"
                updated_slots["diagnostic_action"] = "monitor_standby"
                break
            elif "coolant" in text or "overheating" in text:
                updated_slots["indicator_type"] = "temp_warning"
                updated_slots["severity"] = "critical"
                updated_slots["diagnostic_action"] = "trigger_coolant_purge"

        return updated_slots
