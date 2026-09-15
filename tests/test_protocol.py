"""
Unit tests for Protocol Layer and Schema Validation.
"""

import pytest
from chronos.protocol.events import Event, EventType, InterruptionLevel
from chronos.protocol.schemas import ExecutionClass, CallStatus, ToolDefinition, ToolCall, ToolResult


def test_immutable_event_creation():
    evt = Event(
        event_type=EventType.USER_INPUT,
        timestamp=1.23,
        snapshot_id="v1",
        payload={"text": "Hello world"},
    )
    assert evt.event_type == EventType.USER_INPUT
    assert evt.timestamp == 1.23
    assert evt.snapshot_id == "v1"
    assert evt.payload["text"] == "Hello world"

    # Verify immutability
    with pytest.raises(Exception):
        evt.timestamp = 2.0  # Should raise ValidationError / FrozenInstanceError


def test_tool_definition_validation():
    tool = ToolDefinition(
        name="test_tool",
        description="A test tool",
        execution_class=ExecutionClass.IRREVERSIBLE_WRITE,
        reversible=False,
        idempotent=True,
        requires_confirmation=True,
    )
    assert tool.execution_class == ExecutionClass.IRREVERSIBLE_WRITE
    assert tool.requires_confirmation is True
    assert tool.reversible is False


def test_interruption_level_enumeration():
    assert InterruptionLevel.LEVEL_0.value == 0
    assert InterruptionLevel.LEVEL_1.value == 1
    assert InterruptionLevel.LEVEL_2.value == 2
    assert InterruptionLevel.LEVEL_3.value == 3
    assert InterruptionLevel.LEVEL_4.value == 4
