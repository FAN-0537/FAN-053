"""MCP Server 配置加载。

启动时从项目目录（而不是 xAgent 源码目录）读取 ``.mcp.json``，
兼容 MCP 标准配置中的 stdio 与 Streamable HTTP 两种传输方式。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".mcp.json"

STDIO_TYPES = {"stdio"}
HTTP_TYPES = {"streamable_http", "streamable-http", "http", "streamable"}


class MCPConfigError(RuntimeError):
    """MCP 配置文件缺失或格式非法。"""


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    name: str
    transport: str
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class LoadedMCPConfig:
    path: Path | None
    servers: tuple[MCPServerConfig, ...]
    warnings: tuple[str, ...]


def _expand_env(value: str) -> str:
    """展开 ``${VAR}`` 与 ``$VAR`` 形式的环境变量。"""

    if not isinstance(value, str) or "$" not in value:
        return value

    def replace(match: Any) -> str:
        name = match.group(1) or match.group(2)
        return os.environ.get(name, match.group(0))

    import re

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", replace, value)


def _string_mapping(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MCPConfigError(f"{field_name} 必须是对象")
    return {str(key): _expand_env(str(item)) for key, item in value.items()}


def _parse_server(name: str, raw: Any) -> MCPServerConfig:
    if not isinstance(raw, dict):
        raise MCPConfigError("配置项必须是 JSON 对象")

    explicit_type = str(raw.get("type") or "").strip().lower()
    url = raw.get("url")
    command = raw.get("command")

    if explicit_type in HTTP_TYPES:
        transport = "streamable_http"
    elif explicit_type in STDIO_TYPES:
        transport = "stdio"
    elif explicit_type:
        raise MCPConfigError(f"不支持的 type: {explicit_type}")
    elif url:
        transport = "streamable_http"
    elif command:
        transport = "stdio"
    else:
        raise MCPConfigError("缺少 url（HTTP）或 command（stdio）")

    if transport == "streamable_http":
        if not isinstance(url, str) or not url.strip():
            raise MCPConfigError("streamable_http 需要非空的 url")
        return MCPServerConfig(
            name=name,
            transport=transport,
            url=_expand_env(url.strip()),
            headers=_string_mapping(raw.get("headers"), "headers"),
        )

    if not isinstance(command, str) or not command.strip():
        raise MCPConfigError("stdio 需要非空的 command")

    args_raw = raw.get("args") or []
    if not isinstance(args_raw, (list, tuple)):
        raise MCPConfigError("args 必须是字符串数组")

    cwd = raw.get("cwd")
    return MCPServerConfig(
        name=name,
        transport=transport,
        command=_expand_env(command.strip()),
        args=tuple(_expand_env(str(item)) for item in args_raw),
        env=_string_mapping(raw.get("env"), "env"),
        cwd=_expand_env(str(cwd)) if cwd else None,
    )


def load_mcp_config(base_dir: str | Path | None = None) -> LoadedMCPConfig:
    """读取 ``base_dir/.mcp.json``。

    单个 Server 配置非法时只跳过该项并记录警告，不影响其他 Server。
    """

    directory = (Path(base_dir) if base_dir is not None else Path.cwd()).expanduser().resolve()
    path = directory / CONFIG_FILENAME
    if not path.is_file():
        return LoadedMCPConfig(path=None, servers=(), warnings=())

    try:
        # utf-8-sig 兼容 Windows 记事本 / PowerShell 写入的 BOM
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise MCPConfigError(f"读取 MCP 配置失败: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"MCP 配置不是合法的 JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise MCPConfigError("MCP 配置根节点必须是 JSON 对象")

    servers_raw = data.get("mcpServers", data.get("servers"))
    if servers_raw is None:
        raise MCPConfigError("MCP 配置缺少 mcpServers")
    if not isinstance(servers_raw, dict):
        raise MCPConfigError("mcpServers 必须是对象")

    servers: list[MCPServerConfig] = []
    warnings: list[str] = []
    for name, raw in servers_raw.items():
        try:
            servers.append(_parse_server(str(name), raw))
        except MCPConfigError as exc:
            warnings.append(f"MCP Server “{name}” 配置无效，已跳过: {exc}")

    return LoadedMCPConfig(path=path, servers=tuple(servers), warnings=tuple(warnings))
