"""Agent 会话编排。

只依赖抽象 LLM 协议和工具注册表，通过异步事件流向界面层输出状态，
因此同一套核心可以被 TUI、Web 或 Desktop 复用。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import ContextConfig
from core.context import (
    ContextArchive,
    ContextUsage,
    estimate_messages_tokens,
    render_messages,
)
from core.events import AgentEvent, AgentEventType
from core.llm.base import AssistantMessage, ChatModel
from core.prompts import SYSTEM_PROMPT, build_compact_prompt
from core.sessions import (
    PROJECT_CONTEXT_PREFIX,
    SessionStore,
    has_project_context,
)
from core.tools.base import ToolRegistry


class AgentSession:
    def __init__(
        self,
        llm: ChatModel,
        tools: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_rounds: int = 8,
        mcp_manager: Any | None = None,
        workspace: str | Path | None = None,
        context_config: ContextConfig | None = None,
        session_store: SessionStore | None = None,
        project_context: str = "",
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_tool_rounds = max(1, int(max_tool_rounds))
        self._mcp_manager = mcp_manager
        self.workspace = (Path(workspace) if workspace is not None else Path.cwd()).expanduser().resolve()
        self._context_config = context_config or ContextConfig()
        self._session_store = session_store
        self._project_context = str(project_context or "").strip()
        self._archive = ContextArchive(
            self.workspace,
            directory=self._context_config.archive_dir,
            max_matches=self._context_config.recall_max_matches,
            max_chars=self._context_config.recall_max_chars,
            snippet_radius=self._context_config.snippet_radius,
        )
        self._history: list[dict[str, Any]] = []
        self._last_usage_total: int | None = None
        self._compacting = False
        self.reset()

    @property
    def history(self) -> list[dict[str, Any]]:
        return [message.copy() for message in self._history]

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def session_store(self) -> SessionStore | None:
        return self._session_store

    @property
    def project_context(self) -> str:
        return self._project_context

    @property
    def is_compacting(self) -> bool:
        return self._compacting

    @property
    def mcp_manager(self) -> Any | None:
        return self._mcp_manager

    def set_mcp_manager(self, manager: Any | None) -> None:
        self._mcp_manager = manager

    def reset(self) -> None:
        self._history = [{"role": "system", "content": self._system_prompt}]
        self._last_usage_total = None
        self._inject_project_context()

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        history = [message.copy() for message in messages]
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": self._system_prompt})
        self._history = history
        self._last_usage_total = None
        if not has_project_context(history):
            self._inject_project_context()

    def has_conversation(self) -> bool:
        for message in self._history:
            role = message.get("role")
            if role == "system":
                continue
            content = message.get("content")
            if (
                role == "user"
                and isinstance(content, str)
                and content.startswith(PROJECT_CONTEXT_PREFIX)
            ):
                continue
            return True
        return False

    def _inject_project_context(self) -> bool:
        if not self._project_context:
            return False
        if has_project_context(self._history):
            return False
        content = f"{PROJECT_CONTEXT_PREFIX}\n\n{self._project_context}"
        self._history.append({"role": "user", "content": content})
        return True

    def close(self) -> None:
        """释放 MCP 等外部连接。"""

        if self._mcp_manager is not None:
            close = getattr(self._mcp_manager, "close", None)
            if callable(close):
                close()
            self._mcp_manager = None

    def context_usage(self) -> ContextUsage:
        """返回当前会话的上下文占用情况。"""

        window, is_default = self._context_window()
        if self._last_usage_total is not None:
            tokens = self._last_usage_total
        else:
            tokens = self._estimated_tokens()
        tokens = max(0, int(tokens))
        ratio = tokens / window if window > 0 else 0.0
        return ContextUsage(
            tokens=tokens,
            window=window,
            ratio=ratio,
            window_is_default=is_default,
        )

    def needs_compaction(self) -> bool:
        return self.context_usage().ratio >= self._context_config.warning_ratio

    async def send(self, user_input: str) -> AsyncIterator[AgentEvent]:
        text = user_input.strip()
        if not text:
            return

        if self._compacting:
            yield AgentEvent(
                type=AgentEventType.ERROR,
                text="上下文正在压缩，暂时不能处理新的提示词，请稍候。",
            )
            yield AgentEvent(type=AgentEventType.TURN_COMPLETE)
            return

        if self.needs_compaction():
            usage = self.context_usage()
            yield AgentEvent(
                type=AgentEventType.ERROR,
                text=(
                    f"上下文已占用 {usage.ratio * 100:.1f}%"
                    f"（阈值 {self._context_config.warning_ratio * 100:.0f}%），"
                    "请先执行 /compact 压缩上下文后再继续。"
                ),
            )
            yield self._context_event()
            yield AgentEvent(type=AgentEventType.TURN_COMPLETE)
            return

        self._history.append({"role": "user", "content": text})
        yield AgentEvent(type=AgentEventType.USER_MESSAGE, text=text)

        for _ in range(self._max_tool_rounds):
            try:
                reply = await self._llm.complete(
                    self._history,
                    self._tools.schemas(),
                )
            except Exception as exc:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    text=f"调用模型失败: {exc}",
                )
                yield self._context_event()
                yield AgentEvent(type=AgentEventType.TURN_COMPLETE)
                return

            self._record_usage(reply)

            if not reply.tool_calls:
                content = reply.content or ""
                self._history.append({"role": "assistant", "content": content})
                yield AgentEvent(
                    type=AgentEventType.ASSISTANT_MESSAGE,
                    text=content,
                )
                yield self._context_event()
                yield AgentEvent(type=AgentEventType.TURN_COMPLETE)
                return

            self._history.append(self._to_assistant_message(reply))
            if reply.content:
                yield AgentEvent(
                    type=AgentEventType.ASSISTANT_MESSAGE,
                    text=reply.content,
                )

            for call in reply.tool_calls:
                arguments, parse_error = self._parse_arguments(call.arguments)
                yield AgentEvent(
                    type=AgentEventType.TOOL_CALL,
                    tool_call_id=call.id,
                    tool_name=call.name,
                    tool_arguments=arguments
                    if arguments is not None
                    else {"raw": call.arguments},
                )

                if parse_error:
                    result = json.dumps(
                        {"ok": False, "error": parse_error},
                        ensure_ascii=False,
                    )
                else:
                    result = await self._tools.aexecute(call.name, arguments or {})

                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
                yield AgentEvent(
                    type=AgentEventType.TOOL_RESULT,
                    tool_call_id=call.id,
                    tool_name=call.name,
                    tool_result=result,
                )

        yield AgentEvent(
            type=AgentEventType.ERROR,
            text=f"工具调用超过最大轮次（{self._max_tool_rounds}），本轮已中止",
        )
        yield self._context_event()
        yield AgentEvent(type=AgentEventType.TURN_COMPLETE)

    async def compact(self) -> AsyncIterator[AgentEvent]:
        """归档原始上下文并调用 LLM 生成摘要，成功后替换会话历史。"""

        if self._compacting:
            yield AgentEvent(
                type=AgentEventType.ERROR,
                text="上下文正在压缩中，请勿重复执行。",
            )
            return

        if len(self._history) <= 1:
            yield AgentEvent(
                type=AgentEventType.ERROR,
                text="当前没有可压缩的历史上下文。",
            )
            return

        self._compacting = True
        try:
            yield AgentEvent(
                type=AgentEventType.COMPACTION_STARTED,
                text="开始压缩上下文…",
            )

            archive_id = self._archive.new_id()
            try:
                self._archive.save(self._history, archive_id)
            except Exception as exc:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    text=f"保存原始上下文归档失败，已取消压缩: {exc}",
                )
                return

            before_text = render_messages(self._history)
            try:
                summary = await self._summarize(before_text)
            except Exception as exc:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    text=f"调用模型生成压缩摘要失败: {exc}",
                )
                return

            if not summary:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    text="模型未返回有效的压缩摘要，已保留原有上下文。",
                )
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            note = (
                f"> 此前上下文已于 {timestamp} 完成压缩，原始上下文保存在编号为 "
                f"{archive_id} 的归档文件中。如需查找历史信息，请使用 "
                f"recallContext 工具。"
            )
            compressed = (
                "【此前对话的压缩摘要】\n\n"
                f"{summary}\n\n---\n\n{note}"
            )

            self._history = [
                {"role": "system", "content": self._system_prompt},
                {"role": "assistant", "content": compressed},
            ]
            self._inject_project_context()
            self._last_usage_total = self._estimated_tokens()

            yield AgentEvent(
                type=AgentEventType.COMPACTION_FINISHED,
                text=f"上下文压缩完成，原始上下文已归档为 {archive_id}。",
                compaction_before=before_text,
                compaction_after=compressed,
                archive_id=archive_id,
            )
            yield self._context_event()
        finally:
            self._compacting = False

    def _context_window(self) -> tuple[int, bool]:
        getter = getattr(self._llm, "context_window", None)
        if callable(getter):
            try:
                value, is_default = getter()
                if int(value) > 0:
                    return int(value), bool(is_default)
            except Exception:
                pass
        return self._context_config.default_window, True

    def _estimated_tokens(self) -> int:
        tools_text = ""
        try:
            tools_text = json.dumps(
                self._tools.schemas(), ensure_ascii=False, default=str
            )
        except (TypeError, ValueError):
            tools_text = ""
        return estimate_messages_tokens(self._history, extra_text=tools_text)

    def _record_usage(self, reply: AssistantMessage) -> None:
        usage = reply.usage
        if usage is not None and usage.total_tokens > 0:
            self._last_usage_total = usage.total_tokens
        else:
            self._last_usage_total = self._estimated_tokens()

    def _context_event(self) -> AgentEvent:
        usage = self.context_usage()
        return AgentEvent(
            type=AgentEventType.CONTEXT_STATE,
            context_tokens=usage.tokens,
            context_window=usage.window,
            context_ratio=usage.ratio,
            context_window_default=usage.window_is_default,
        )

    async def _summarize(self, history_text: str) -> str:
        messages = [
            {
                "role": "system",
                "content": build_compact_prompt(
                    self._context_config.compact_target_tokens
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是需要压缩的历史上下文，请按系统提示生成工作摘要：\n\n"
                    f"{history_text}"
                ),
            },
        ]
        reply = await self._llm.complete(messages, None)
        return (reply.content or "").strip()

    @staticmethod
    def _parse_arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return None, "工具参数不是合法的 JSON"
        if not isinstance(value, dict):
            return None, "工具参数必须是 JSON 对象"
        return value, None

    @staticmethod
    def _to_assistant_message(reply: AssistantMessage) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": reply.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in reply.tool_calls
            ],
        }
