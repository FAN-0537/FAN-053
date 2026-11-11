"""历史上下文检索工具（recallContext）。"""

from __future__ import annotations

from pathlib import Path

from core.config import ContextConfig
from core.context import ContextArchive
from core.tools.base import ToolRegistry, ToolSpec


def register_context_tools(
    registry: ToolRegistry,
    workspace: str | Path,
    config: ContextConfig | None = None,
) -> None:
    options = config or ContextConfig()
    archive = ContextArchive(
        workspace,
        directory=options.archive_dir,
        max_matches=options.recall_max_matches,
        max_chars=options.recall_max_chars,
        snippet_radius=options.snippet_radius,
    )

    def recall_context(text: str, id: str | None = None) -> dict:
        return archive.recall(text, id)

    registry.register(
        ToolSpec(
            name="recallContext",
            description=(
                "在已压缩并归档的历史上下文中进行全文关键词检索。"
                "当压缩摘要缺少某些历史细节时，可用它找回原始记录。"
                "不传 id 时检索历史归档目录下的所有文件；结果包含归档编号、"
                "所在行号和原始内容片段。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要查找的关键词或文本内容，必填",
                    },
                    "id": {
                        "type": "string",
                        "description": (
                            "可选的归档编号，如 20261022-153000；"
                            "不提供时检索全部历史归档"
                        ),
                    },
                },
                "required": ["text"],
            },
            handler=recall_context,
        )
    )
