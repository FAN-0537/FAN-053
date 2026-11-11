"""文件系统业务能力。

这一层是纯业务逻辑：不依赖命令行、Textual 或任何其他界面框架，
所有方法均返回可直接序列化给模型的结构化字典。
"""

from __future__ import annotations

import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.filesystem.support import (
    MAX_TEXT_FILE_BYTES,
    detect_text_encoding,
    error,
    guard_destructive,
    ok,
    resolve_path,
)


class FileSystemService:
    """以指定工作目录为基准的文件系统服务。"""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        max_text_file_bytes: int = MAX_TEXT_FILE_BYTES,
        default_read_max_chars: int = 10000,
    ) -> None:
        self.root = (Path(root) if root is not None else Path.cwd()).expanduser().resolve()
        self.max_text_file_bytes = max(1, int(max_text_file_bytes))
        self.default_read_max_chars = max(1, int(default_read_max_chars))

    def _resolve(self, value: str | Path | None) -> Path:
        return resolve_path(value or ".", self.root)

    def get_current_directory(self) -> dict[str, Any]:
        return ok(cwd=str(self.root))

    def list_directory(self, path: str | Path = ".") -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"目录不存在: {target}")
        if not target.is_dir():
            return error(f"不是目录: {target}")

        entries: list[dict[str, Any]] = []
        try:
            with os.scandir(target) as iterator:
                for entry in iterator:
                    try:
                        stat = entry.stat()
                        entries.append(
                            {
                                "name": entry.name,
                                "type": "directory" if entry.is_dir() else "file",
                                "size": stat.st_size if entry.is_file() else None,
                                "modified": datetime.fromtimestamp(
                                    stat.st_mtime
                                ).isoformat(timespec="seconds"),
                            }
                        )
                    except OSError as exc:
                        entries.append(
                            {"name": entry.name, "type": "unknown", "error": str(exc)}
                        )
        except OSError as exc:
            return error(f"读取目录失败: {exc}")

        entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
        return ok(path=str(target), count=len(entries), entries=entries)

    def get_file_type(self, path: str | Path) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"文件或目录不存在: {target}")
        if target.is_dir():
            return ok(
                path=str(target),
                file_type="directory",
                extension="",
                mime_type="inode/directory",
            )
        if not target.is_file():
            return ok(path=str(target), file_type="other", extension="", mime_type="")

        extension = target.suffix.lower()
        mime_type, _ = mimetypes.guess_type(target.name)
        encoding = detect_text_encoding(target)
        return ok(
            path=str(target),
            file_type="text" if encoding else "binary",
            extension=extension,
            mime_type=mime_type or "application/octet-stream",
            encoding=encoding,
        )

    def read_file(
        self,
        path: str | Path,
        max_chars: int | None = None,
    ) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"文件不存在: {target}")
        if not target.is_file():
            return error(f"不是文件: {target}")

        size = target.stat().st_size
        if size > self.max_text_file_bytes:
            return error(f"文件过大（{size} 字节），暂不支持读取")

        encoding = detect_text_encoding(target)
        if not encoding:
            return error("仅支持读取纯文本文件，该文件可能是二进制文件或编码不受支持")

        try:
            content = target.read_text(encoding=encoding, newline="")
        except (OSError, UnicodeDecodeError) as exc:
            return error(f"读取文件失败: {exc}")

        if max_chars is None:
            max_chars = self.default_read_max_chars
        try:
            limit = max(1, int(max_chars))
        except (TypeError, ValueError):
            return error("max_chars 必须是整数")

        truncated = len(content) > limit
        if truncated:
            content = content[:limit]
        return ok(
            path=str(target),
            encoding=encoding,
            size=size,
            truncated=truncated,
            content=content,
        )

    def create_file(
        self,
        directory: str | Path,
        filename: str,
        content: str = "",
        create_dirs: bool = True,
    ) -> dict[str, Any]:
        directory_path = self._resolve(directory)
        name = str(filename).strip()
        if not name or Path(name).name != name or name in (".", ".."):
            return error("文件名不合法，只能提供文件名，不能包含路径分隔符")

        directory_existed = directory_path.is_dir()
        try:
            if create_dirs:
                directory_path.mkdir(parents=True, exist_ok=True)
            elif not directory_existed:
                return error(f"目录不存在: {directory_path}")
        except OSError as exc:
            return error(f"创建目录失败: {exc}")

        target = directory_path / name
        if target.exists():
            return error(f"文件已存在，不能覆盖: {target}")
        try:
            with target.open("x", encoding="utf-8", newline="") as file:
                file.write(content or "")
        except OSError as exc:
            return error(f"创建文件失败: {exc}")
        return ok(
            path=str(target),
            size=target.stat().st_size,
            directory_created=create_dirs and not directory_existed,
        )

    def edit_file(
        self,
        path: str | Path,
        content: str = "",
        mode: str = "overwrite",
        old_text: str | None = None,
        new_text: str | None = None,
    ) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"文件不存在: {target}")
        if not target.is_file():
            return error(f"不是文件: {target}")

        encoding = detect_text_encoding(target)
        if not encoding:
            return error("仅支持编辑纯文本文件，该文件可能是二进制文件或编码不受支持")

        edit_mode = str(mode or "overwrite").lower()
        try:
            if edit_mode == "overwrite":
                target.write_text(content or "", encoding=encoding, newline="")
                return ok(path=str(target), mode=edit_mode, size=target.stat().st_size)
            if edit_mode == "append":
                append_encoding = "utf-8" if encoding == "utf-8-sig" else encoding
                with target.open("a", encoding=append_encoding, newline="") as file:
                    file.write(content or "")
                return ok(path=str(target), mode=edit_mode, size=target.stat().st_size)
            if edit_mode == "replace":
                if old_text is None or new_text is None:
                    return error("replace 模式需要同时提供 old_text 和 new_text")
                text = target.read_text(encoding=encoding, newline="")
                count = text.count(old_text)
                if count == 0:
                    return error("未找到要替换的内容")
                target.write_text(
                    text.replace(old_text, new_text),
                    encoding=encoding,
                    newline="",
                )
                return ok(
                    path=str(target),
                    mode=edit_mode,
                    replaced=count,
                    size=target.stat().st_size,
                )
            return error("mode 只能是 overwrite、append 或 replace")
        except (OSError, UnicodeDecodeError) as exc:
            return error(f"编辑文件失败: {exc}")

    def create_directory(self, path: str | Path) -> dict[str, Any]:
        target = self._resolve(path)
        if target.exists():
            return error(f"路径已存在: {target}")
        try:
            target.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            return error(f"创建目录失败: {exc}")
        return ok(path=str(target), created=True)

    def delete_directory(self, path: str | Path) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"目录不存在: {target}")
        if not target.is_dir():
            return error(f"不是目录: {target}")

        guard = guard_destructive(target, self.root)
        if guard:
            return error(guard)
        try:
            shutil.rmtree(target)
        except OSError as exc:
            return error(f"删除目录失败: {exc}")
        return ok(path=str(target), deleted=True)

    def delete_file(self, path: str | Path) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return error(f"文件不存在: {target}")
        if not target.is_file():
            return error(f"不是文件: {target}")

        guard = guard_destructive(target, self.root)
        if guard:
            return error(guard)
        try:
            target.unlink()
        except OSError as exc:
            return error(f"删除文件失败: {exc}")
        return ok(path=str(target), deleted=True)

    def rename_item(self, source: str | Path, new_name: str) -> dict[str, Any]:
        source_path = self._resolve(source)
        if not source_path.exists():
            return error(f"文件或目录不存在: {source_path}")

        name = str(new_name).strip()
        if not name or Path(name).name != name or name in (".", ".."):
            return error("新名称不合法，只能提供文件名或目录名，不能包含路径分隔符")

        guard = guard_destructive(source_path, self.root)
        if guard:
            return error(guard)

        destination = source_path.with_name(name)
        if destination.exists():
            return error(f"目标已存在: {destination}")

        item_type = "directory" if source_path.is_dir() else "file"
        try:
            source_path.rename(destination)
        except OSError as exc:
            return error(f"重命名失败: {exc}")
        return ok(
            source=str(source_path),
            destination=str(destination),
            item_type=item_type,
        )
