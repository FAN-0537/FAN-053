"""把 MCP Server 暴露的工具注册到 xAgent 的工具注册表。"""

from __future__ import annotations

import re
from typing import Any

from core.filesystem.support import error
from core.mcp.client import MCPManager, summarize_result
from core.tools.base import ToolRegistry, ToolSpec

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]")
MAX_TOOL_NAME_LENGTH = 64


def _sanitize(value: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", value.strip())
    return cleaned or "unnamed"


def _exposed_name(server: str, tool: str) -> str:
    prefix = f"mcp__{_sanitize(server)}__"
    budget = MAX_TOOL_NAME_LENGTH - len(prefix)
    if budget <= 0:
        return prefix[:MAX_TOOL_NAME_LENGTH]
    return prefix + _sanitize(tool)[:budget]


def _unique_name(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        return candidate
    index = 2
    while True:
        suffix = f"_{index}"
        base = candidate[: MAX_TOOL_NAME_LENGTH - len(suffix)]
        name = f"{base}{suffix}"
        if name not in used:
            return name
        index += 1


def register_mcp_tools(registry: ToolRegistry, manager: MCPManager) -> dict[str, tuple[str, str]]:
    """注册所有已连接 Server 的工具，返回 “暴露名称 -> (Server, 原始工具名)” 映射。"""

    used = set(registry.names())
    mapping: dict[str, tuple[str, str]] = {}

    for server_name, connection in manager.connections.items():
        if not connection.is_ready:
            continue
        for tool in connection.tools:
            exposed = _unique_name(_exposed_name(server_name, tool.name), used)
            used.add(exposed)
            mapping[exposed] = (server_name, tool.name)

            description = tool.description or f"MCP Server {server_name} 提供的工具 {tool.name}"
            full_description = f"[MCP: {server_name}] {description}"
            schema = tool.inputSchema or {"type": "object", "properties": {}}
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            else:
                schema = dict(schema)
                schema.pop("$schema", None)
                schema.setdefault("type", "object")

            def make_handler(server: str, tool_name: str):
                async def handler(**arguments: Any) -> dict[str, Any]:
                    try:
                        result = await manager.acall_tool(server, tool_name, arguments)
                    except Exception as exc:  # noqa: BLE001 - 统一转换为工具错误
                        return error(
                            f"MCP 工具调用失败（{server}/{tool_name}）: {exc}"
                        )
                    return summarize_result(result)

                return handler

            registry.register(
                ToolSpec(
                    name=exposed,
                    description=full_description,
                    parameters=schema,
                    handler=make_handler(server_name, tool.name),
                )
            )

    manager.tool_map = dict(mapping)
    return mapping
