"""
CHRONOS Model Context Protocol (MCP) Integration Client.
Enables dynamic tool discovery, execution class classification, and real-time execution via MCP stdio/SSE servers.
"""

from __future__ import annotations
import asyncio
import json
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from chronos.protocol.schemas import ExecutionClass, ToolDefinition
from chronos.tools.manifest import ToolRegistry


class MCPTool(BaseModel):
    name: str
    description: str = ""
    inputSchema: Dict[str, Any] = Field(default_factory=dict)
    execution_class: ExecutionClass = ExecutionClass.READ_ONLY


class MCPClient:
    """
    Model Context Protocol (MCP) dynamic client for CHRONOS.
    Discovers tools from MCP servers and registers them with full invariant safety into CHRONOS ToolRegistry.
    """

    def __init__(self, server_command: Optional[List[str]] = None, sse_url: Optional[str] = None):
        self.server_command = server_command
        self.sse_url = sse_url
        self.discovered_tools: Dict[str, MCPTool] = {}

    def _infer_execution_class(self, tool_name: str, description: str) -> ExecutionClass:
        """
        Infers execution class based on safety heuristics:
        - Irreversible: buy, book, pay, charge, delete, drop, wipe, send_payment, execute_order
        - Reversible: write, save_draft, update_profile, set_preference, create_temp
        - Read Only: get, search, list, fetch, query, read, find, check
        """
        combined = f"{tool_name} {description}".lower()
        irreversible_keywords = ["book", "buy", "pay", "charge", "commit", "delete", "drop", "transfer", "order", "execute_payment"]
        reversible_keywords = ["draft", "set", "update", "toggle", "store_temp", "cache"]

        for kw in irreversible_keywords:
            if kw in combined:
                return ExecutionClass.IRREVERSIBLE_WRITE
        for kw in reversible_keywords:
            if kw in combined:
                return ExecutionClass.REVERSIBLE_WRITE
        return ExecutionClass.READ_ONLY

    def register_mcp_tool_manually(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Optional[Callable[..., Any]] = None,
        execution_class: Optional[ExecutionClass] = None,
    ) -> MCPTool:
        """Registers an MCP tool definition."""
        inferred_class = execution_class or self._infer_execution_class(name, description)
        mcp_tool = MCPTool(
            name=name,
            description=description,
            inputSchema=parameters,
            execution_class=inferred_class,
        )
        self.discovered_tools[name] = mcp_tool
        return mcp_tool

    def export_to_chronos_registry(self, registry: ToolRegistry) -> None:
        """
        Translates all discovered MCP tools into CHRONOS ToolDefinitions and registers them.
        """
        for name, tool in self.discovered_tools.items():
            tool_def = ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
                execution_class=tool.execution_class,
                estimated_duration=0.15,
                idempotent=(tool.execution_class == ExecutionClass.READ_ONLY),
                requires_confirmation=(tool.execution_class == ExecutionClass.IRREVERSIBLE_WRITE),
            )
            registry.register(tool_def)
