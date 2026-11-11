"""MCP 异步加载入口。

连接 MCP Server 可能耗时较长，这里把阻塞的 ``MCPManager.start`` 放到线程中，
让 TUI 可以先显示界面，加载完成后再刷新侧边栏。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import MCPRuntimeConfig, PROJECT_ROOT
from core.mcp.client import MCPManager
from core.mcp.config import MCPConfigError, load_mcp_config
from core.mcp.tools import register_mcp_tools
from core.tools.base import ToolRegistry


@dataclass(slots=True)
class MCPLoadResult:
    manager: MCPManager | None = None
    mapping: dict[str, tuple[str, str]] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)


async def load_mcp_async(
    registry: ToolRegistry,
    workspace: str | Path,
    config: MCPRuntimeConfig | None = None,
) -> MCPLoadResult:
    options = config or MCPRuntimeConfig()
    result = MCPLoadResult()

    candidates: list[Path] = []
    for candidate in (Path(workspace), Path.cwd(), PROJECT_ROOT):
        resolved = Path(candidate).expanduser().resolve()
        if resolved not in candidates:
            candidates.append(resolved)

    loaded = None
    for directory in candidates:
        try:
            candidate_config = load_mcp_config(directory)
        except MCPConfigError as exc:
            result.notices.append(f"MCP 配置错误（{directory}）: {exc}")
            return result
        if candidate_config.path is not None:
            loaded = candidate_config
            break

    if loaded is None:
        searched = "、".join(str(path) for path in candidates)
        result.notices.append(
            f"未发现 .mcp.json（已查找: {searched}），MCP 未启用"
        )
        return result

    result.notices.extend(loaded.warnings)
    if not loaded.servers:
        result.notices.append(f"未配置 MCP Server（{loaded.path}）")
        return result

    manager = MCPManager(
        connect_timeout=options.connect_timeout,
        call_timeout=options.call_timeout,
        close_timeout=options.close_timeout,
    )
    try:
        errors = await asyncio.to_thread(manager.start, loaded.servers)
    except Exception as exc:  # noqa: BLE001 - MCP 故障不应影响主流程
        manager.close()
        result.notices.append(f"MCP 初始化失败: {exc}")
        return result

    for server, message in errors.items():
        result.notices.append(f"MCP Server “{server}” 连接失败: {message}")

    try:
        mapping = register_mcp_tools(registry, manager)
    except Exception as exc:  # noqa: BLE001 - 同上
        result.notices.append(f"MCP 工具注册失败: {exc}")
        manager.close()
        return result

    connected: list[str] = [
        name
        for name, connection in manager.connections.items()
        if connection.is_ready
    ]
    if connected:
        result.notices.append(
            f"已连接 MCP Server: {', '.join(sorted(connected))}，"
            f"注册工具 {len(mapping)} 个"
        )
    else:
        result.notices.append("没有成功连接的 MCP Server")

    result.manager = manager
    result.mapping = mapping
    return result


def describe_manager(manager: MCPManager | None) -> list[dict[str, Any]]:
    """把 MCP 连接状态整理成供 TUI 渲染的结构。"""

    if manager is None:
        return []
    servers: list[dict[str, Any]] = []
    for name, connection in manager.connections.items():
        if connection.is_ready:
            status = "connected"
            detail = ""
        elif connection.error is not None:
            status = "error"
            detail = MCPManager._describe_error(connection.error)
        else:
            status = "connecting"
            detail = ""
        servers.append(
            {
                "name": name,
                "status": status,
                "detail": detail,
                "tools": [tool.name for tool in connection.tools],
            }
        )
    return servers
