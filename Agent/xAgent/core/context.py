"""上下文长度估算、原始上下文归档与历史全文检索。

本模块刻意只使用标准库，便于理解：不引入向量数据库或 Embedding，
压缩归档保存为 JSONL，历史检索采用本地关键词匹配。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from core.filesystem.support import error, ok

DEFAULT_CONTEXT_WINDOW = 128 * 1024
CONTEXT_WARNING_RATIO = 0.6
ARCHIVE_DIR_NAME = ".agents/context"

MAX_RECALL_MATCHES = 8
MAX_RECALL_CHARS = 6000
RECALL_SNIPPET_RADIUS = 160


@dataclass(frozen=True, slots=True)
class ContextUsage:
    """一次上下文占用快照。"""

    tokens: int
    window: int
    ratio: float
    window_is_default: bool


def estimate_tokens(text: str) -> int:
    """粗略估算文本 Token 数：中日韩字符按 1 计，其余按 4 字符 1 计。"""

    if not text:
        return 0
    cjk = 0
    other = 0
    for char in text:
        code = ord(char)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3000 <= code <= 0x30FF
            or 0xAC00 <= code <= 0xD7AF
        ):
            cjk += 1
        else:
            other += 1
    return cjk + (other + 3) // 4


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(content)


def message_text(message: dict[str, Any]) -> str:
    """把一条消息展开成适合检索／展示的纯文本。"""

    parts: list[str] = []
    role = message.get("role")
    if role:
        parts.append(f"role: {role}")
    name = message.get("name")
    if name:
        parts.append(f"tool_name: {name}")
    tool_call_id = message.get("tool_call_id")
    if tool_call_id:
        parts.append(f"tool_call_id: {tool_call_id}")
    content = message.get("content")
    if content is not None:
        parts.append(_content_text(content))
    tool_calls = message.get("tool_calls")
    if tool_calls:
        parts.append(
            "tool_calls: "
            + json.dumps(tool_calls, ensure_ascii=False, default=str)
        )
    return "\n".join(parts)


def render_messages(messages: Iterable[dict[str, Any]]) -> str:
    """按消息顺序渲染完整上下文，供压缩 Prompt 与预览面板使用。"""

    blocks: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = message.get("role", "unknown")
        title = f"[消息 {index}] {role}"
        block = f"### {title}\n{message_text(message)}"
        blocks.append(block)
    return "\n\n".join(blocks)


def estimate_messages_tokens(
    messages: Iterable[dict[str, Any]],
    extra_text: str = "",
) -> int:
    """估算一批消息占用的 Token，包含工具定义等额外文本。"""

    total = 0
    for message in messages:
        total += 4
        total += estimate_tokens(message_text(message))
    total += estimate_tokens(extra_text)
    return total


class ContextArchive:
    """`<workspace>/.agents/context/` 下的上下文归档读写。"""

    def __init__(
        self,
        workspace: str | Path,
        *,
        directory: str = ARCHIVE_DIR_NAME,
        max_matches: int = MAX_RECALL_MATCHES,
        max_chars: int = MAX_RECALL_CHARS,
        snippet_radius: int = RECALL_SNIPPET_RADIUS,
    ) -> None:
        self.directory = Path(workspace).expanduser().resolve() / directory
        self.max_matches = max(1, int(max_matches))
        self.max_chars = max(1, int(max_chars))
        self.snippet_radius = max(1, int(snippet_radius))

    def new_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = base
        counter = 1
        while (self.directory / f"{candidate}.jsonl").exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def save(self, messages: list[dict[str, Any]], archive_id: str | None = None) -> str:
        """保存原始上下文，返回归档编号。成功返回即代表已落盘。"""

        self.directory.mkdir(parents=True, exist_ok=True)
        identifier = archive_id or self.new_id()
        path = self.directory / f"{identifier}.jsonl"
        temp = path.with_suffix(".jsonl.tmp")

        with temp.open("w", encoding="utf-8", newline="\n") as file:
            for message in messages:
                file.write(json.dumps(message, ensure_ascii=False, default=str))
                file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp.replace(path)

        if not path.exists() or path.stat().st_size == 0:
            raise OSError(f"归档写入失败: {path}")
        return identifier

    def _resolve(self, archive_id: str) -> Path | None:
        name = str(archive_id).strip()
        if name.endswith(".jsonl"):
            name = name[: -len(".jsonl")]
        if not name or Path(name).name != name or name in (".", ".."):
            return None
        return self.directory / f"{name}.jsonl"

    def recall(self, text: str, archive_id: str | None = None) -> dict[str, Any]:
        """在归档中做全文关键词检索，返回带来源信息的相关片段。"""

        keyword = str(text or "").strip()
        if not keyword:
            return error("参数 text 不能为空")

        if archive_id:
            path = self._resolve(archive_id)
            if path is None:
                return error("归档编号不合法")
            if not path.exists():
                return error(f"未找到归档: {archive_id}")
            files = [path]
        else:
            if not self.directory.is_dir():
                return ok(keyword=keyword, matches=[], scanned_archives=0)
            files = sorted(
                self.directory.glob("*.jsonl"),
                key=lambda item: item.name,
                reverse=True,
            )

        lowered = keyword.lower()
        matches: list[dict[str, Any]] = []
        used_chars = 0
        truncated = False
        scanned = 0

        for path in files:
            if not path.exists():
                continue
            scanned += 1
            try:
                lines = path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError as exc:
                return error(f"读取归档失败: {exc}")

            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                haystack = message_text(message)
                index = haystack.lower().find(lowered)
                if index < 0:
                    continue

                snippet = _make_snippet(
                    haystack, index, len(keyword), self.snippet_radius
                )
                if (
                    len(matches) >= self.max_matches
                    or used_chars + len(snippet) > self.max_chars
                ):
                    truncated = True
                    break
                matches.append(
                    {
                        "archive": path.stem,
                        "line": line_number,
                        "role": message.get("role"),
                        "snippet": snippet,
                    }
                )
                used_chars += len(snippet)

            if truncated:
                break

        return ok(
            keyword=keyword,
            scanned_archives=scanned,
            matches=matches,
            truncated=truncated,
        )


def _make_snippet(
    text: str,
    index: int,
    length: int,
    radius: int = RECALL_SNIPPET_RADIUS,
) -> str:
    start = max(0, index - radius)
    end = min(len(text), index + length + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    body = text[start:end].replace("\r", " ").replace("\n", " ")
    return f"{prefix}{body}{suffix}"
