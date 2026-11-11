"""会话事件日志的保存、列出与恢复。

每个会话保存为 ``.agents/sessions/<id>.jsonl``：
第一行是 meta 事件，之后每行是一条消息事件。这样既保留了消息顺序，
也把 AGENTS.md 等注入内容作为真实历史持久化下来。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_CONTEXT_PREFIX = "【项目 AGENTS.md 上下文】"
DEFAULT_SESSION_DIR = ".agents/sessions"
MAX_TITLE_LENGTH = 48


@dataclass(frozen=True, slots=True)
class SessionSummary:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class SessionStore:
    def __init__(
        self,
        workspace: str | Path,
        directory: str = DEFAULT_SESSION_DIR,
    ) -> None:
        self.directory = (
            Path(workspace).expanduser().resolve() / directory
        )

    def new_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = base
        counter = 1
        while (self.directory / f"{candidate}.jsonl").exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def save(
        self,
        messages: list[dict[str, Any]],
        session_id: str | None = None,
        *,
        title: str | None = None,
        created_at: str | None = None,
    ) -> SessionSummary:
        self.directory.mkdir(parents=True, exist_ok=True)
        identifier = session_id or self.new_id()
        path = self.directory / f"{identifier}.jsonl"

        previous = self._read_meta(path)
        now = datetime.now().isoformat(timespec="seconds")
        resolved_title = (
            title
            or (previous.title if previous is not None else "")
            or _derive_title(messages)
        )
        if not resolved_title:
            resolved_title = "新会话"
        created = created_at or (
            previous.created_at if previous is not None else now
        )

        temp = path.with_suffix(".jsonl.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as file:
            meta = {
                "type": "meta",
                "id": identifier,
                "title": resolved_title,
                "created_at": created,
                "updated_at": now,
                "message_count": len(messages),
            }
            file.write(json.dumps(meta, ensure_ascii=False))
            file.write("\n")
            for message in messages:
                event = {"type": "message", "message": message}
                file.write(json.dumps(event, ensure_ascii=False, default=str))
                file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp.replace(path)

        return SessionSummary(
            id=identifier,
            title=resolved_title,
            created_at=created,
            updated_at=now,
            message_count=len(messages),
        )

    def load(self, session_id: str) -> list[dict[str, Any]] | None:
        path = self._resolve(session_id)
        if path is None or not path.exists():
            return None
        messages: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "message":
                message = event.get("message")
                if isinstance(message, dict):
                    messages.append(message)
        return messages

    def list(self) -> list[SessionSummary]:
        if not self.directory.is_dir():
            return []
        summaries: list[SessionSummary] = []
        for path in self.directory.glob("*.jsonl"):
            meta = self._read_meta(path)
            if meta is None:
                continue
            summaries.append(meta)
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def _read_meta(self, path: Path) -> SessionSummary | None:
        try:
            with path.open("r", encoding="utf-8") as file:
                first_line = file.readline()
        except OSError:
            return None
        try:
            event = json.loads(first_line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict) or event.get("type") != "meta":
            return None
        identifier = str(event.get("id") or path.stem)
        return SessionSummary(
            id=identifier,
            title=str(event.get("title") or "未命名会话"),
            created_at=str(event.get("created_at") or ""),
            updated_at=str(event.get("updated_at") or ""),
            message_count=int(event.get("message_count") or 0),
        )

    def _resolve(self, session_id: str) -> Path | None:
        name = str(session_id).strip()
        if name.endswith(".jsonl"):
            name = name[: -len(".jsonl")]
        if not name or Path(name).name != name or name in (".", ".."):
            return None
        return self.directory / f"{name}.jsonl"


def _derive_title(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        text = " ".join(content.strip().split())
        if not text or text.startswith(PROJECT_CONTEXT_PREFIX):
            continue
        if len(text) > MAX_TITLE_LENGTH:
            text = text[:MAX_TITLE_LENGTH].rstrip() + "…"
        return text
    return ""


def has_project_context(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if (
            message.get("role") == "user"
            and isinstance(content, str)
            and content.startswith(PROJECT_CONTEXT_PREFIX)
        ):
            return True
    return False
