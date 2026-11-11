"""Agent 对外发布的领域事件。

所有界面（TUI / Web / Desktop）都消费同一套事件，不依赖具体 UI 框架。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentEventType(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    TURN_COMPLETE = "turn_complete"
    CONTEXT_STATE = "context_state"
    COMPACTION_STARTED = "compaction_started"
    COMPACTION_FINISHED = "compaction_finished"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    type: AgentEventType
    text: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result: str | None = None
    context_tokens: int | None = None
    context_window: int | None = None
    context_ratio: float | None = None
    context_window_default: bool = False
    compaction_before: str | None = None
    compaction_after: str | None = None
    archive_id: str | None = None
