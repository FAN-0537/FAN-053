"""MCP（Model Context Protocol）客户端集成。"""

from core.mcp.client import MCPManager
from core.mcp.config import MCPServerConfig, load_mcp_config
from core.mcp.loader import MCPLoadResult, describe_manager, load_mcp_async
from core.mcp.tools import register_mcp_tools

__all__ = [
    "MCPLoadResult",
    "MCPManager",
    "MCPServerConfig",
    "describe_manager",
    "load_mcp_async",
    "load_mcp_config",
    "register_mcp_tools",
]
