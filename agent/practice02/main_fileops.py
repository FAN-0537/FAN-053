import configparser
import json
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path

from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent

cfg = configparser.ConfigParser()
cfg.read(BASE_DIR / "config.ini", encoding="utf-8")

client = OpenAI(api_key=cfg["llm"]["api_key"], base_url=cfg["llm"]["base_url"])

MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024


def _ok(**data):
    return json.dumps({"ok": True, **data}, ensure_ascii=False)


def _err(message):
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _path(value):
    return Path(value).expanduser().resolve()


def _detect_text_encoding(path, sample_size=65536):
    try:
        with path.open("rb") as f:
            raw = f.read(sample_size)
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


def _guard_destructive(target):
    cwd = Path.cwd().resolve()
    if target == Path(target.anchor):
        return "不能操作磁盘根目录"
    if cwd == target or cwd.is_relative_to(target):
        return "不能删除或重命名当前工作目录及其上级目录"
    return None


def is_leap_year(year):
    year = int(year)
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    return year % 4 == 0


def check_leap_year(year):
    leap = is_leap_year(year)
    return f"{year} 年{'是' if leap else '不是'}闰年"


def get_current_directory():
    return _ok(cwd=str(Path.cwd()))


def list_directory(path="."):
    target = _path(path or ".")
    if not target.exists():
        return _err(f"目录不存在: {target}")
    if not target.is_dir():
        return _err(f"不是目录: {target}")
    entries = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    stat = entry.stat()
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "directory" if entry.is_dir() else "file",
                            "size": stat.st_size if entry.is_file() else None,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                                timespec="seconds"
                            ),
                        }
                    )
                except OSError as exc:
                    entries.append(
                        {"name": entry.name, "type": "unknown", "error": str(exc)}
                    )
    except OSError as exc:
        return _err(f"读取目录失败: {exc}")
    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    return _ok(path=str(target), count=len(entries), entries=entries)


def get_file_type(path):
    target = _path(path)
    if not target.exists():
        return _err(f"文件或目录不存在: {target}")
    if target.is_dir():
        return _ok(
            path=str(target),
            file_type="directory",
            extension="",
            mime_type="inode/directory",
        )
    if not target.is_file():
        return _ok(path=str(target), file_type="other", extension="", mime_type="")
    extension = target.suffix.lower()
    mime_type, _ = mimetypes.guess_type(target.name)
    encoding = _detect_text_encoding(target)
    return _ok(
        path=str(target),
        file_type="text" if encoding else "binary",
        extension=extension,
        mime_type=mime_type or "application/octet-stream",
        encoding=encoding,
    )


def read_file(path, max_chars=10000):
    target = _path(path)
    if not target.exists():
        return _err(f"文件不存在: {target}")
    if not target.is_file():
        return _err(f"不是文件: {target}")
    size = target.stat().st_size
    if size > MAX_TEXT_FILE_BYTES:
        return _err(f"文件过大（{size} 字节），暂不支持读取")
    encoding = _detect_text_encoding(target)
    if not encoding:
        return _err("仅支持读取纯文本文件，该文件可能是二进制文件或编码不受支持")
    try:
        content = target.read_text(encoding=encoding, newline="")
    except (OSError, UnicodeDecodeError) as exc:
        return _err(f"读取文件失败: {exc}")
    max_chars = max(1, int(max_chars))
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    return _ok(
        path=str(target),
        encoding=encoding,
        size=size,
        truncated=truncated,
        content=content,
    )


def create_file(directory, filename, content="", create_dirs=True):
    directory_path = _path(directory or ".")
    name = str(filename).strip()
    if not name or Path(name).name != name or name in (".", ".."):
        return _err("文件名不合法，只能提供文件名，不能包含路径分隔符")
    directory_existed = directory_path.is_dir()
    try:
        if create_dirs:
            directory_path.mkdir(parents=True, exist_ok=True)
        elif not directory_existed:
            return _err(f"目录不存在: {directory_path}")
    except OSError as exc:
        return _err(f"创建目录失败: {exc}")
    target = directory_path / name
    if target.exists():
        return _err(f"文件已存在，不能覆盖: {target}")
    try:
        with target.open("x", encoding="utf-8", newline="") as f:
            f.write(content or "")
    except OSError as exc:
        return _err(f"创建文件失败: {exc}")
    return _ok(
        path=str(target),
        size=target.stat().st_size,
        directory_created=create_dirs and not directory_existed,
    )


def edit_file(path, content="", mode="overwrite", old_text=None, new_text=None):
    target = _path(path)
    if not target.exists():
        return _err(f"文件不存在: {target}")
    if not target.is_file():
        return _err(f"不是文件: {target}")
    encoding = _detect_text_encoding(target)
    if not encoding:
        return _err("仅支持编辑纯文本文件，该文件可能是二进制文件或编码不受支持")
    mode = str(mode or "overwrite").lower()
    try:
        if mode == "overwrite":
            target.write_text(content or "", encoding=encoding, newline="")
            return _ok(path=str(target), mode=mode, size=target.stat().st_size)
        if mode == "append":
            append_encoding = "utf-8" if encoding == "utf-8-sig" else encoding
            with target.open("a", encoding=append_encoding, newline="") as f:
                f.write(content or "")
            return _ok(path=str(target), mode=mode, size=target.stat().st_size)
        if mode == "replace":
            if old_text is None or new_text is None:
                return _err("replace 模式需要同时提供 old_text 和 new_text")
            text = target.read_text(encoding=encoding, newline="")
            count = text.count(old_text)
            if count == 0:
                return _err("未找到要替换的内容")
            target.write_text(
                text.replace(old_text, new_text), encoding=encoding, newline=""
            )
            return _ok(
                path=str(target), mode=mode, replaced=count, size=target.stat().st_size
            )
        return _err("mode 只能是 overwrite、append 或 replace")
    except (OSError, UnicodeDecodeError) as exc:
        return _err(f"编辑文件失败: {exc}")


def create_directory(path):
    target = _path(path)
    if target.exists():
        return _err(f"路径已存在: {target}")
    try:
        target.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return _err(f"创建目录失败: {exc}")
    return _ok(path=str(target), created=True)


def delete_directory(path):
    target = _path(path)
    if not target.exists():
        return _err(f"目录不存在: {target}")
    if not target.is_dir():
        return _err(f"不是目录: {target}")
    guard = _guard_destructive(target)
    if guard:
        return _err(guard)
    try:
        shutil.rmtree(target)
    except OSError as exc:
        return _err(f"删除目录失败: {exc}")
    return _ok(path=str(target), deleted=True)


def delete_file(path):
    target = _path(path)
    if not target.exists():
        return _err(f"文件不存在: {target}")
    if not target.is_file():
        return _err(f"不是文件: {target}")
    guard = _guard_destructive(target)
    if guard:
        return _err(guard)
    try:
        target.unlink()
    except OSError as exc:
        return _err(f"删除文件失败: {exc}")
    return _ok(path=str(target), deleted=True)


def rename_item(source, new_name):
    source_path = _path(source)
    if not source_path.exists():
        return _err(f"文件或目录不存在: {source_path}")
    name = str(new_name).strip()
    if not name or Path(name).name != name or name in (".", ".."):
        return _err("新名称不合法，只能提供文件名或目录名，不能包含路径分隔符")
    guard = _guard_destructive(source_path)
    if guard:
        return _err(guard)
    destination = source_path.with_name(name)
    if destination.exists():
        return _err(f"目标已存在: {destination}")
    item_type = "directory" if source_path.is_dir() else "file"
    try:
        source_path.rename(destination)
    except OSError as exc:
        return _err(f"重命名失败: {exc}")
    return _ok(
        source=str(source_path),
        destination=str(destination),
        item_type=item_type,
    )


tools = [
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断指定年份是否为闰年，通过 Python 代码精确计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，如 2024",
                    },
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getCurrentDirectory",
            "description": "获取当前工作目录的绝对路径",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDirectory",
            "description": "列出指定目录下的所有文件和子目录，返回名称、类型、大小和修改时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前工作目录",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件或目录的类型，包括扩展名、MIME 类型以及是否为纯文本",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录的路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件的内容，自动识别 UTF-8/GBK 编码",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最多返回的字符数，默认 10000",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "在指定目录下创建新文件，可自动创建不存在的目录；不会覆盖已有文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "文件所在目录，如 D:\\data 或 ./docs",
                    },
                    "filename": {
                        "type": "string",
                        "description": "文件名，如 note.txt；不能包含路径分隔符",
                    },
                    "content": {
                        "type": "string",
                        "description": "初始文件内容，默认为空",
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "目录不存在时是否自动创建，默认 true",
                    },
                },
                "required": ["directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑纯文本文件，支持整体覆盖（overwrite）、追加（append）和文本替换（replace）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "overwrite 或 append 模式下写入的内容",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "append", "replace"],
                        "description": "编辑模式，默认 overwrite",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "replace 模式下被替换的原文",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "replace 模式下替换后的新文本",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDirectory",
            "description": "创建一个新目录，可自动创建其上级目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的目录路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteDirectory",
            "description": "删除指定目录及其全部内容（支持非空目录），禁止删除磁盘根目录和当前工作目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的目录路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除指定的文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renameItem",
            "description": "重命名指定的文件或目录，新名称不能包含路径分隔符",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "原文件或目录的路径",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "新的文件或目录名称",
                    },
                },
                "required": ["source", "new_name"],
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "isLeapYear": check_leap_year,
    "getCurrentDirectory": get_current_directory,
    "listDirectory": list_directory,
    "getFileType": get_file_type,
    "readFile": read_file,
    "createFile": create_file,
    "editFile": edit_file,
    "createDirectory": create_directory,
    "deleteDirectory": delete_directory,
    "deleteFile": delete_file,
    "renameItem": rename_item,
}


def execute_tool(name, arguments):
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return _err(f"未知工具: {name}")
    try:
        return func(**arguments)
    except Exception as exc:
        return _err(f"工具执行失败: {exc}")


SYSTEM_PROMPT = (
    "你是一个可以操作本地文件系统的助手。"
    "当用户需要查看目录、读取、创建、编辑、删除文件或目录、重命名时，"
    "必须调用提供的工具获取真实结果，不要凭空编造文件内容。"
    "执行删除或重命名前，先确认目标路径是否正确。"
)


def main():
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        question = input("\n你: ").strip()

        if question.lower() == "exit":
            print("已退出。")
            break

        history.append({"role": "user", "content": question})

        while True:
            response = client.chat.completions.create(
                model=cfg["llm"]["model"],
                temperature=float(cfg["llm"]["temperature"]),
                messages=history,
                tools=tools,
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                history.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        result = _err("工具参数不是合法的 JSON")
                    else:
                        result = execute_tool(tc.function.name, args)
                    print(f"\n[工具调用 {tc.function.name}] -> {result}")
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result),
                        }
                    )
                continue

            print(f"\nAI: {msg.content}")
            history.append({"role": "assistant", "content": msg.content})
            break
        print("---")


if __name__ == "__main__":
    main()
