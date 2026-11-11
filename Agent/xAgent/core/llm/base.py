"""LLM 抽象接口。

core 只依赖这里的协议，不直接依赖 OpenAI SDK，
方便未来替换模型供应商或在测试中注入假实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage | None = None


class ChatModel(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantMessage:
        """执行一次对话补全。"""

    def context_window(self) -> tuple[int, bool]:
        """返回 (上下文窗口大小, 是否为默认值)。"""
