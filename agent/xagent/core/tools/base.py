"""工具定义与注册表。

工具是 core 对外暴露的能力边界：
- ToolSpec 负责 schema、参数校验与结果序列化；
- ToolRegistry 负责按名称查找并执行工具。

handler 既可以是同步函数，也可以是返回 awaitable 的异步函数，
因此本地工具与 MCP 工具可以统一参与 Function Calling 流程。
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from core.filesystem.support import error

ToolHandler = Callable[..., Any]


def _error_json(message: str) -> str:
    return json.dumps(error(message), ensure_ascii=False)


def _serialize(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _validate(self, arguments: Mapping[str, Any]) -> str | None:
        required = self.parameters.get("required", ())
        missing = [name for name in required if name not in arguments]
        if missing:
            return f"缺少必填参数: {', '.join(missing)}"
        return None

    def invoke(self, arguments: Mapping[str, Any]) -> str:
        missing = self._validate(arguments)
        if missing:
            return _error_json(missing)

        try:
            result = self.handler(**arguments)
        except TypeError as exc:
            return _error_json(f"工具参数错误: {exc}")
        except Exception as exc:
            return _error_json(f"工具执行失败: {exc}")

        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            return _error_json(f"工具 {self.name} 是异步工具，请使用异步执行入口")
        return _serialize(result)

    async def ainvoke(self, arguments: Mapping[str, Any]) -> str:
        missing = self._validate(arguments)
        if missing:
            return _error_json(missing)

        try:
            result = self.handler(**arguments)
            if inspect.isawaitable(result):
                result = await result
        except TypeError as exc:
            return _error_json(f"工具参数错误: {exc}")
        except Exception as exc:
            return _error_json(f"工具执行失败: {exc}")

        return _serialize(result)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具已注册: {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.schema() for spec in self._tools.values()]

    def execute(self, name: str, arguments: Mapping[str, Any]) -> str:
        spec = self._tools.get(name)
        if spec is None:
            return _error_json(f"未知工具: {name}")
        return spec.invoke(arguments)

    async def aexecute(self, name: str, arguments: Mapping[str, Any]) -> str:
        spec = self._tools.get(name)
        if spec is None:
            return _error_json(f"未知工具: {name}")
        return await spec.ainvoke(arguments)
