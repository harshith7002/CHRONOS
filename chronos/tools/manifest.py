"""
CHRONOS Dynamic Tool Manifest & Registry
Fully schema-driven tool registration without hardcoded domain dependencies.
"""

from __future__ import annotations
import inspect
from typing import Any, Callable, Dict, List, Optional
from chronos.protocol.schemas import ToolDefinition, ExecutionClass


class ToolRegistry:
    """
    Registry for dynamic tools and their executable handlers.
    """

    def __init__(self):
        self._definitions: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., Any]] = {}

    def register_tool(
        self,
        definition: ToolDefinition,
        handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        """Register a tool definition and optional handler callable."""
        self._definitions[definition.name] = definition
        if handler:
            self._handlers[definition.name] = handler

    def register_from_dict(self, tool_dict: Dict[str, Any], handler: Optional[Callable[..., Any]] = None) -> ToolDefinition:
        """Parse dictionary manifest and register tool."""
        defn = ToolDefinition(**tool_dict)
        self.register_tool(defn, handler)
        return defn

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._definitions.get(name)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Convenience alias for get_tool."""
        return self._definitions.get(name)

    def register(self, definition: ToolDefinition, handler: Optional[Callable[..., Any]] = None) -> None:
        """Convenience alias for register_tool."""
        self.register_tool(definition, handler)

    def get_handler(self, name: str) -> Optional[Callable[..., Any]]:
        return self._handlers.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._definitions.values())

    def has_tool(self, name: str) -> bool:
        return name in self._definitions

    def clear(self) -> None:
        self._definitions.clear()
        self._handlers.clear()


def create_default_travel_manifest() -> ToolRegistry:
    """
    Creates the dynamic reference manifest for the travel scenario demo.
    Notice: the engine does not depend on this, this is only used for tests and demo.
    """
    registry = ToolRegistry()

    # 1. search_flights (READ_ONLY, speculative safe)
    registry.register_tool(
        ToolDefinition(
            name="search_flights",
            description="Search available flights by destination, date, and time of day",
            input_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "date": {"type": "string"},
                    "time_of_day": {"type": "string"},
                    "max_price": {"type": "number"},
                },
                "required": ["destination"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "flights": {"type": "array"},
                },
            },
            execution_class=ExecutionClass.READ_ONLY,
            reversible=True,
            idempotent=True,
            requires_confirmation=False,
            slot_dependencies=["destination", "date", "time_of_day", "max_price"],
            estimated_duration=0.2,
        ),
        handler=lambda destination, date=None, time_of_day=None, max_price=None: [
            {"flight_id": f"{destination.upper()[:3]}-101", "dest": destination, "price": 8500, "time": "08:00 AM"},
            {"flight_id": f"{destination.upper()[:3]}-202", "dest": destination, "price": 12000, "time": "02:00 PM"},
            {"flight_id": f"{destination.upper()[:3]}-303", "dest": destination, "price": 7200, "time": "09:30 AM"},
        ],
    )

    # 2. filter_flights (READ_ONLY, depends on search_flights)
    registry.register_tool(
        ToolDefinition(
            name="filter_flights",
            description="Filter flights based on max price and time window",
            input_schema={
                "type": "object",
                "properties": {
                    "flights": {"type": "array"},
                    "max_price": {"type": "number"},
                },
            },
            execution_class=ExecutionClass.READ_ONLY,
            reversible=True,
            idempotent=True,
            requires_confirmation=False,
            slot_dependencies=["max_price"],
            estimated_duration=0.05,
        ),
        handler=lambda flights, max_price=10000: [
            f for f in flights if f.get("price", 0) <= max_price
        ],
    )

    # 3. select_flight (READ_ONLY, depends on filter_flights)
    registry.register_tool(
        ToolDefinition(
            name="select_flight",
            description="Select best matching flight (e.g. cheapest or earliest)",
            input_schema={
                "type": "object",
                "properties": {
                    "flights": {"type": "array"},
                    "criterion": {"type": "string"},
                },
            },
            execution_class=ExecutionClass.READ_ONLY,
            reversible=True,
            idempotent=True,
            requires_confirmation=False,
            slot_dependencies=["criterion"],
            estimated_duration=0.05,
        ),
        handler=lambda flights, criterion="cheapest": min(flights, key=lambda f: f.get("price", 999999)) if flights else None,
    )

    # 4. book_flight (IRREVERSIBLE_WRITE, requires strict confirmation)
    registry.register_tool(
        ToolDefinition(
            name="book_flight",
            description="Irreversibly book the selected flight and charge payment",
            input_schema={
                "type": "object",
                "properties": {
                    "flight_id": {"type": "string"},
                    "passenger_name": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["flight_id"],
            },
            execution_class=ExecutionClass.IRREVERSIBLE_WRITE,
            reversible=False,
            idempotent=True,
            requires_confirmation=True,
            slot_dependencies=["flight_id", "passenger_name"],
            estimated_duration=0.3,
        ),
        handler=lambda flight_id, passenger_name="Passenger", amount=0: {
            "booking_reference": f"PNR-{flight_id}-{uuid_suffix()}",
            "status": "CONFIRMED",
            "flight_id": flight_id,
            "passenger": passenger_name,
            "amount_charged": amount,
        },
    )

    # 5. cancel_booking (REVERSIBLE_WRITE compensation)
    registry.register_tool(
        ToolDefinition(
            name="cancel_booking",
            description="Reversible cancellation of a booking reference",
            input_schema={
                "type": "object",
                "properties": {
                    "booking_reference": {"type": "string"},
                },
                "required": ["booking_reference"],
            },
            execution_class=ExecutionClass.REVERSIBLE_WRITE,
            reversible=True,
            idempotent=True,
            requires_confirmation=True,
            slot_dependencies=["booking_reference"],
            estimated_duration=0.2,
        ),
        handler=lambda booking_reference: {
            "booking_reference": booking_reference,
            "status": "REFUNDED",
        },
    )

    return registry


def uuid_suffix() -> str:
    import uuid
    return uuid.uuid4().hex[:6].upper()
