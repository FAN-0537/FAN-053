"""文件系统工具定义。"""

from __future__ import annotations

from core.filesystem.service import FileSystemService
from core.tools.base import ToolRegistry, ToolSpec


def register_filesystem_tools(
    registry: ToolRegistry,
    service: FileSystemService,
) -> None:
    specs = [
        ToolSpec(
            name="getCurrentDirectory",
            description="获取当前工作目录的绝对路径",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=service.get_current_directory,
        ),
        ToolSpec(
            name="listDirectory",
            description="列出指定目录下的所有文件和子目录，返回名称、类型、大小和修改时间",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前工作目录",
                    },
                },
                "required": [],
            },
            handler=service.list_directory,
        ),
        ToolSpec(
            name="getFileType",
            description="获取指定文件或目录的类型，包括扩展名、MIME 类型以及是否为纯文本",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录的路径",
                    },
                },
                "required": ["path"],
            },
            handler=service.get_file_type,
        ),
        ToolSpec(
            name="readFile",
            description="读取指定纯文本文件的内容，自动识别 UTF-8/GBK 编码",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": (
                            "最多返回的字符数，默认 "
                            f"{service.default_read_max_chars}"
                        ),
                    },
                },
                "required": ["path"],
            },
            handler=service.read_file,
        ),
        ToolSpec(
            name="createFile",
            description="在指定目录下创建新文件，可自动创建不存在的目录；不会覆盖已有文件",
            parameters={
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
            handler=service.create_file,
        ),
        ToolSpec(
            name="editFile",
            description="编辑纯文本文件，支持整体覆盖（overwrite）、追加（append）和文本替换（replace）",
            parameters={
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
            handler=service.edit_file,
        ),
        ToolSpec(
            name="createDirectory",
            description="创建一个新目录，可自动创建其上级目录",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的目录路径",
                    },
                },
                "required": ["path"],
            },
            handler=service.create_directory,
        ),
        ToolSpec(
            name="deleteDirectory",
            description="删除指定目录及其全部内容（支持非空目录），禁止删除磁盘根目录和当前工作目录",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的目录路径",
                    },
                },
                "required": ["path"],
            },
            handler=service.delete_directory,
        ),
        ToolSpec(
            name="deleteFile",
            description="删除指定的文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径",
                    },
                },
                "required": ["path"],
            },
            handler=service.delete_file,
        ),
        ToolSpec(
            name="renameItem",
            description="重命名指定的文件或目录，新名称不能包含路径分隔符",
            parameters={
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
            handler=service.rename_item,
        ),
    ]

    for spec in specs:
        registry.register(spec)
