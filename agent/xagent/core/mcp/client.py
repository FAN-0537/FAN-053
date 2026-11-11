"""MCP 客户端连接管理。

MCP Python SDK 的 ``ClientSession`` 是异步上下文对象，且连接需要长期保持。
为了让同步的工具注册表也能安全使用，这里用独立后台线程运行专用事件循环，
每个 Server 在该循环中维持一个长连接任务；调用方通过线程安全的 Future 交互。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from core.mcp.config import MCPServerConfig

DEFAULT_CONNECT_TIMEOUT = 30.0
DEFAULT_CALL_TIMEOUT = 120.0
DEFAULT_CLOSE_TIMEOUT = 10.0


@dataclass(slots=True)
class MCPServerConnection:
    config: MCPServerConfig
    session: ClientSession | None = None
    tools: list[types.Tool] = field(default_factory=list)
    call_lock: asyncio.Lock | None = None
    stop_event: asyncio.Event | None = None
    ready: threading.Event = field(default_factory=threading.Event)
    error: BaseException | None = None
    task: concurrent.futures.Future[Any] | None = None

    @property
    def is_ready(self) -> bool:
        return self.ready.is_set() and self.error is None and self.session is not None


class _LoopThread(threading.Thread):
    """运行 asyncio 事件循环的守护线程。"""

    def __init__(self) -> None:
        super().__init__(name="xagent-mcp-loop", daemon=True)
        self.loop = asyncio.new_event_loop()
        self._started = threading.Event()

    def run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._started.set()
        try:
            self.loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                self.loop.close()

    def wait_started(self, timeout: float = 5.0) -> bool:
        return self._started.wait(timeout)

    def submit(self, coro: Any) -> concurrent.futures.Future[Any]:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self.loop.stop)


class MCPManager:
    """管理多个 MCP Server 的连接、工具发现与工具调用。"""

    def __init__(
        self,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        call_timeout: float = DEFAULT_CALL_TIMEOUT,
        close_timeout: float = DEFAULT_CLOSE_TIMEOUT,
    ) -> None:
        self._thread = _LoopThread()
        self._connections: dict[str, MCPServerConnection] = {}
        self._started = False
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._close_timeout = close_timeout
        self.errors: dict[str, str] = {}
        self.tool_map: dict[str, tuple[str, str]] = {}

    @property
    def connections(self) -> dict[str, MCPServerConnection]:
        return dict(self._connections)

    def start(
        self,
        configs: tuple[MCPServerConfig, ...] | list[MCPServerConfig],
        *,
        connect_timeout: float | None = None,
    ) -> dict[str, str]:
        """连接所有 Server 并发现工具，返回 “Server 名 -> 错误信息” 映射。"""

        if not configs:
            return {}

        if connect_timeout is None:
            connect_timeout = self._connect_timeout

        if not self._started:
            self._thread.start()
            if not self._thread.wait_started():
                self._started = False
                self.errors = {"*": "MCP 后台事件循环启动失败"}
                return dict(self.errors)
            self._started = True

        for config in configs:
            connection = MCPServerConnection(config=config)
            self._connections[config.name] = connection
            connection.task = self._thread.submit(self._server_main(connection))

            if not connection.ready.wait(connect_timeout):
                connection.error = TimeoutError(
                    f"连接超时（{connect_timeout:.0f} 秒）"
                )
            if connection.error is not None:
                self.errors[config.name] = self._describe_error(connection.error)

        return dict(self.errors)

    async def _server_main(self, connection: MCPServerConnection) -> None:
        connection.stop_event = asyncio.Event()
        try:
            if connection.config.transport == "stdio":
                params = StdioServerParameters(
                    command=connection.config.command or "",
                    args=list(connection.config.args),
                    env=connection.config.env or None,
                    cwd=connection.config.cwd,
                )
                # 把 stdio server 的日志写入空设备，避免污染 Textual 界面。
                with open(os.devnull, "w", encoding="utf-8") as errlog:
                    async with stdio_client(params, errlog=errlog) as (
                        read_stream,
                        write_stream,
                    ):
                        await self._session_main(
                            connection, read_stream, write_stream
                        )
            else:
                async with streamablehttp_client(
                    connection.config.url or "",
                    headers=connection.config.headers or None,
                ) as (read_stream, write_stream, _get_session_id):
                    await self._session_main(connection, read_stream, write_stream)
        except BaseException as exc:  # noqa: BLE001 - 需要把失败原因交给调用方
            connection.error = exc
        finally:
            connection.ready.set()

    async def _session_main(
        self,
        connection: MCPServerConnection,
        read_stream: Any,
        write_stream: Any,
    ) -> None:
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            connection.session = session
            connection.tools = list(listed.tools)
            connection.call_lock = asyncio.Lock()
            connection.ready.set()
            assert connection.stop_event is not None
            await connection.stop_event.wait()

    async def _acall_tool(
        self,
        connection: MCPServerConnection,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float,
    ) -> types.CallToolResult:
        if connection.error is not None:
            raise RuntimeError(self._describe_error(connection.error))
        if not connection.ready.is_set():
            raise RuntimeError("MCP Server 尚未连接完成")
        if connection.session is None or connection.call_lock is None:
            raise RuntimeError("MCP Server 连接不可用")

        async def call() -> types.CallToolResult:
            async with connection.call_lock:
                return await connection.session.call_tool(tool_name, arguments)

        future = self._thread.submit(call())
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(future),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"工具调用超时（{timeout:.0f} 秒）") from exc

    async def acall_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> types.CallToolResult:
        connection = self._connections.get(server_name)
        if connection is None:
            raise KeyError(f"未找到 MCP Server: {server_name}")
        return await self._acall_tool(
            connection,
            tool_name,
            arguments or {},
            self._call_timeout if timeout is None else timeout,
        )

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> types.CallToolResult:
        """同步版本的调用，供非 asyncio 场景使用。"""

        if timeout is None:
            timeout = self._call_timeout
        connection = self._connections.get(server_name)
        if connection is None:
            raise KeyError(f"未找到 MCP Server: {server_name}")
        if connection.error is not None:
            raise RuntimeError(self._describe_error(connection.error))
        if not connection.ready.is_set() or connection.session is None:
            raise RuntimeError("MCP Server 连接不可用")
        if connection.call_lock is None:
            raise RuntimeError("MCP Server 连接不可用")

        async def call() -> types.CallToolResult:
            async with connection.call_lock:
                return await connection.session.call_tool(tool_name, arguments or {})

        future = self._thread.submit(call())
        return future.result(timeout=timeout)

    def close(self, *, timeout: float | None = None) -> None:
        if not self._started:
            return
        if timeout is None:
            timeout = self._close_timeout

        for connection in self._connections.values():
            if connection.stop_event is not None:
                self._thread.loop.call_soon_threadsafe(connection.stop_event.set)

        for connection in self._connections.values():
            if connection.task is None:
                continue
            try:
                connection.task.result(timeout=timeout)
            except Exception:  # noqa: BLE001 - 关闭阶段忽略清理异常
                connection.task.cancel()

        self._thread.stop()
        self._thread.join(timeout=timeout)
        self._started = False

    @staticmethod
    def _describe_error(exc: BaseException) -> str:
        root = MCPManager._root_exception(exc)
        message = str(root).strip()
        name = type(root).__name__
        return f"{name}: {message}" if message else name

    @staticmethod
    def _root_exception(exc: BaseException) -> BaseException:
        """展开 ExceptionGroup，返回最内层、信息量最大的异常。"""

        while True:
            nested = getattr(exc, "exceptions", None)
            if not nested:
                return exc
            exc = nested[0]


def summarize_result(result: types.CallToolResult) -> dict[str, Any]:
    """把 MCP 调用结果转换为可直接交给 LLM 的结构化字典。"""

    content: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for item in result.content or []:
        if isinstance(item, types.TextContent):
            text_parts.append(item.text)
            content.append({"type": "text", "text": item.text})
            continue
        try:
            content.append(item.model_dump(mode="json", exclude_none=True))
        except AttributeError:
            content.append({"type": getattr(item, "type", "unknown"), "value": str(item)})

    payload: dict[str, Any] = {"ok": not result.isError}
    if text_parts:
        payload["text"] = "\n".join(text_parts)
    if content:
        payload["content"] = content
    if result.structuredContent is not None:
        payload["structuredContent"] = result.structuredContent
    if result.isError:
        payload["error"] = payload.get("text") or "MCP 工具返回错误"
    return payload
