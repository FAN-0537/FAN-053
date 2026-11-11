"""OpenAI 兼容接口实现。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from core.config import LLMConfig
from core.context import DEFAULT_CONTEXT_WINDOW
from core.llm.base import AssistantMessage, ToolCall, TokenUsage


class OpenAICompatibleClient:
    def __init__(
        self,
        config: LLMConfig,
        default_context_window: int = DEFAULT_CONTEXT_WINDOW,
    ) -> None:
        self._config = config
        self._default_context_window = default_context_window
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )

    def context_window(self) -> tuple[int, bool]:
        if self._config.context_window:
            return self._config.context_window, False
        return self._default_context_window, True

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AssistantMessage:
        request: dict[str, Any] = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "messages": messages,
        }
        if tools:
            request["tools"] = tools

        response = await self._client.chat.completions.create(**request)
        message = response.choices[0].message
        tool_calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments or "{}",
            )
            for call in (message.tool_calls or ())
        )
        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            prompt_tokens = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(
                getattr(raw_usage, "completion_tokens", 0) or 0
            )
            total_tokens = int(getattr(raw_usage, "total_tokens", 0) or 0)
            if not total_tokens:
                total_tokens = prompt_tokens + completion_tokens
            if total_tokens:
                usage = TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
        return AssistantMessage(
            content=message.content,
            tool_calls=tool_calls,
            usage=usage,
        )

    async def aclose(self) -> None:
        await self._client.close()
