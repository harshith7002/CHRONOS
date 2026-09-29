"""
CHRONOS SDK Decorators and Wrappers.
Easily decorate Python functions into Invariant-Compliant CHRONOS Tools.
"""

from __future__ import annotations
import inspect
from typing import Any, Callable, Dict, Optional, TypeVar

from chronos.protocol.schemas import ExecutionClass, ToolDefinition

F = TypeVar("F", bound=Callable[..., Any])


def chronos_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    execution_class: ExecutionClass = ExecutionClass.READ_ONLY,
    idempotent: bool = True,
    estimated_duration: float = 0.1,
    requires_confirmation: bool = False,
) -> Callable[[F], F]:
    """
    Decorator that attaches CHRONOS tool metadata to any Python function.
    """
    def decorator(fn: F) -> F:
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").strip()

        # Extract parameters using inspect
        sig = inspect.signature(fn)
        param_properties: Dict[str, Any] = {}
        required_list = []
        for p_name, param in sig.parameters.items():
            if p_name in ("self", "cls"):
                continue
            p_type = "string"
            if param.annotation == int:
                p_type = "integer"
            elif param.annotation == float:
                p_type = "number"
            elif param.annotation == bool:
                p_type = "boolean"
            elif param.annotation == dict:
                p_type = "object"
            elif param.annotation == list:
                p_type = "array"

            param_properties[p_name] = {"type": p_type}
            if param.default == inspect.Parameter.empty:
                required_list.append(p_name)

        input_schema = {
            "type": "object",
            "properties": param_properties,
            "required": required_list,
        }

        tool_def = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            input_schema=input_schema,
            execution_class=execution_class,
            estimated_duration=estimated_duration,
            idempotent=idempotent,
            requires_confirmation=requires_confirmation,
        )

        setattr(fn, "__chronos_tool_def__", tool_def)
        return fn

    return decorator
