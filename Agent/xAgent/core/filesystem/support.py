"""文件系统能力的公共支撑逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024


def ok(**data: Any) -> dict[str, Any]:
    return {"ok": True, **data}


def error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def resolve_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if base is not None and not path.is_absolute():
        path = base / path
    return path.resolve()


def detect_text_encoding(path: Path, sample_size: int = 65536) -> str | None:
    try:
        with path.open("rb") as file:
            raw = file.read(sample_size)
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("utf-8", "gbk"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return None


def guard_destructive(target: Path, workspace: Path) -> str | None:
    target = target.resolve()
    workspace = workspace.resolve()
    if target == Path(target.anchor):
        return "不能操作磁盘根目录"
    if workspace == target or workspace.is_relative_to(target):
        return "不能删除或重命名当前工作目录及其上级目录"
    return None
