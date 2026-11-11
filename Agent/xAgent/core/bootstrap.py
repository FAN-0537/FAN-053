"""依赖装配入口。

所有界面层都通过这里获得配置完整的 AgentSession；
MCP 不再在启动阶段阻塞加载，而是由界面层异步触发。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.agent import AgentSession
from core.config import AppConfig, load_app_config
from core.filesystem.service import FileSystemService
from core.filesystem.support import detect_text_encoding
from core.llm.openai_client import OpenAICompatibleClient
from core.prompts import build_system_prompt
from core.sessions import SessionStore
from core.skills import SkillManager
from core.tools.base import ToolRegistry
from core.tools.cli_tools import register_cli_tools
from core.tools.context_tools import register_context_tools
from core.tools.filesystem_tools import register_filesystem_tools
from core.tools.misc_tools import register_misc_tools
from core.tools.skill_tools import register_skill_tools
from core.tools.web_tools import register_web_tools


@dataclass(slots=True)
class AgentRuntime:
    session: AgentSession
    config: AppConfig
    workspace: Path
    session_store: SessionStore


def _read_project_context(
    root: Path,
    filename: str,
    max_bytes: int,
) -> str:
    """读取项目 AGENTS.md（一次注入，后续复用）。"""

    path = root / filename
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    encoding = detect_text_encoding(path)
    if not encoding:
        return ""
    try:
        if size > max_bytes:
            raw = path.read_bytes()[:max_bytes]
            text = raw.decode(encoding, errors="ignore")
        else:
            text = path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        return ""
    return text.strip()


def build_runtime(
    config_path: str | Path | None = None,
    workspace: str | Path | None = None,
) -> AgentRuntime:
    config = load_app_config(config_path)
    llm = OpenAICompatibleClient(
        config.llm,
        default_context_window=config.context.default_window,
    )
    service = FileSystemService(
        workspace,
        max_text_file_bytes=config.tools.max_text_file_bytes,
        default_read_max_chars=config.tools.read_max_chars,
    )
    skills = SkillManager(
        service.root,
        max_text_file_bytes=config.tools.max_text_file_bytes,
        max_name_length=config.skills.max_name_length,
        max_description_length=config.skills.max_description_length,
    )
    registry = ToolRegistry()
    register_filesystem_tools(registry, service)
    register_cli_tools(registry, service.root, config.tools)
    register_misc_tools(registry)
    register_web_tools(registry, config.tools)
    register_skill_tools(registry, skills)
    register_context_tools(registry, service.root, config.context)

    project_context = _read_project_context(
        service.root,
        config.agent.agents_md_file,
        config.tools.max_text_file_bytes,
    )
    session_store = SessionStore(service.root, config.sessions.directory)

    session = AgentSession(
        llm=llm,
        tools=registry,
        system_prompt=build_system_prompt(skills.render_system_prompt()),
        max_tool_rounds=config.agent.max_tool_rounds,
        workspace=service.root,
        context_config=config.context,
        session_store=session_store,
        project_context=project_context,
    )
    return AgentRuntime(
        session=session,
        config=config,
        workspace=service.root,
        session_store=session_store,
    )


def build_agent_session(
    config_path: str | Path | None = None,
    workspace: str | Path | None = None,
) -> AgentSession:
    """兼容旧接口：只返回 AgentSession。"""

    return build_runtime(config_path, workspace).session
