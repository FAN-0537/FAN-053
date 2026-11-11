"""Skill 动态加载工具定义。"""

from __future__ import annotations

from core.skills import SkillManager
from core.tools.base import ToolRegistry, ToolSpec


def register_skill_tools(registry: ToolRegistry, skills: SkillManager) -> None:
    def create_skill(name: str, skillContext: str):
        return skills.create_skill(name, skillContext)

    registry.register(
        ToolSpec(
            name="loadSkill",
            description=(
                "加载指定 Skill 的完整说明，或读取该 Skill 目录中的附件文件。"
                "只提供 name 时读取 SKILL.md 全文；同时提供 filename 时只读取附件文件。"
                "filename 必须是相对于该 Skill 目录的路径（含仅文件名），不允许越出 Skill 目录；"
                "只提供文件名时会递归搜索该 Skill 目录，若存在多个同名文件则返回候选路径。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "要加载的 Skill 名称，如 pdf-processing",
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "可选，需要加载的附件文件路径或文件名，"
                            "如 references/api.md 或 template.json"
                        ),
                    },
                },
                "required": ["name"],
            },
            handler=skills.load_skill,
        )
    )

    registry.register(
        ToolSpec(
            name="createSkill",
            description=(
                "根据用户需求创建一个新的 Agent Skill。"
                "会在当前项目的 .agents/skills/ 下创建名为 name 的英文子目录，"
                "并生成符合 Agent Skills 规范的 SKILL.md（包含 name、description "
                "YAML Frontmatter 和正文）。"
                "name 只能使用小写英文字母、数字和连字符；"
                "skillContext 为需要写入 SKILL.md 的完整内容，"
                "可包含 Frontmatter 与正文。若 Skill 已存在则不会覆盖。"
                "如需补充 references/、scripts/ 等目录或辅助文件，"
                "请在创建成功后继续调用 createDirectory、createFile 等文件工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill 名称，使用小写字母、数字和连字符，如 pdf-processing",
                    },
                    "skillContext": {
                        "type": "string",
                        "description": (
                            "需要写入 SKILL.md 的完整内容，包含使用说明、步骤、示例等；"
                            "也可自带 YAML Frontmatter，工具会规范化 name 和 description"
                        ),
                    },
                },
                "required": ["name", "skillContext"],
            },
            handler=create_skill,
        )
    )
