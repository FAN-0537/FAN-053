"""配置加载与默认配置生成。

所有可调参数都集中在 ``config.ini`` 中；配置文件缺省时使用本模块内置的
默认值，并可通过 :func:`ensure_config_file` 自动生成一份带 mock 信息的模板。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = Path.cwd() / "config.ini"
DEFAULT_CONTEXT_WINDOW = 128 * 1024
DEFAULT_CONFIG_FILENAME = "config.ini"


class ConfigError(RuntimeError):
    """配置缺失或非法。"""


@dataclass(frozen=True, slots=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.7
    context_window: int | None = None


@dataclass(frozen=True, slots=True)
class AgentConfig:
    max_tool_rounds: int = 8
    agents_md_file: str = "AGENTS.md"


@dataclass(frozen=True, slots=True)
class ContextConfig:
    default_window: int = DEFAULT_CONTEXT_WINDOW
    warning_ratio: float = 0.6
    compact_target_tokens: int = 5000
    recall_max_matches: int = 8
    recall_max_chars: int = 6000
    snippet_radius: int = 160
    archive_dir: str = ".agents/context"


@dataclass(frozen=True, slots=True)
class SessionConfig:
    directory: str = ".agents/sessions"


@dataclass(frozen=True, slots=True)
class ToolsConfig:
    max_text_file_bytes: int = 10 * 1024 * 1024
    read_max_chars: int = 10000
    cli_timeout: int = 30
    cli_timeout_max: int = 300
    cli_output_max_chars: int = 8000
    web_timeout: float = 20.0
    web_max_chars: int = 8000
    web_max_bytes: int = 2 * 1024 * 1024
    search_api_url: str = "https://api.tavily.com/search"
    search_api_key: str = ""
    search_max_results: int = 5


@dataclass(frozen=True, slots=True)
class MCPRuntimeConfig:
    connect_timeout: float = 30.0
    call_timeout: float = 120.0
    close_timeout: float = 10.0


@dataclass(frozen=True, slots=True)
class UIConfig:
    message_max_chars: int = 6000


@dataclass(frozen=True, slots=True)
class SkillsConfig:
    max_name_length: int = 64
    max_description_length: int = 1024


@dataclass(frozen=True, slots=True)
class AppConfig:
    llm: LLMConfig
    agent: AgentConfig = field(default_factory=AgentConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    mcp: MCPRuntimeConfig = field(default_factory=MCPRuntimeConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)


DEFAULT_CONFIG_TEMPLATE = """# XAgent 配置文件（自动生成的 mock 配置）
# 请修改 [openai] 中的 api_key、base_url、model 后重新启动。

[openai]
api_key = sk-mock-please-edit-this-key
base_url = https://api.example.com/v1
model = mock-model
temperature = 0.7
# 可选：模型上下文窗口大小（Token）。不填时默认 131072 并显示“默认”。
# context_window = 131072

[agent]
max_tool_rounds = 8
agents_md_file = AGENTS.md

[context]
default_window = 131072
warning_ratio = 0.6
compact_target_tokens = 5000
recall_max_matches = 8
recall_max_chars = 6000
snippet_radius = 160
archive_dir = .agents/context

[session]
dir = .agents/sessions

[tools]
max_text_file_bytes = 10485760
read_max_chars = 10000
cli_timeout = 30
cli_timeout_max = 300
cli_output_max_chars = 8000
web_timeout = 20
web_max_chars = 8000
web_max_bytes = 2097152

[search]
# 默认 Tavily；也可用环境变量 XAGENT_SEARCH_API_KEY 覆盖
tavily_api_key =
top_k = 5
timeout = 20

[mcp]
connect_timeout = 30
call_timeout = 120
close_timeout = 10

[ui]
message_max_chars = 6000

[skills]
max_name_length = 64
max_description_length = 1024
"""


def default_config_path() -> Path:
    return Path.cwd() / DEFAULT_CONFIG_FILENAME


def ensure_config_file(path: str | Path | None = None) -> bool:
    """配置文件不存在时生成完整模板，返回是否新建。"""

    config_path = Path(path) if path is not None else default_config_path()
    if config_path.exists():
        return False
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"创建配置文件失败: {exc}") from exc
    return True


def _int_value(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    if not parser.has_section(section):
        return default
    raw = parser[section].get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ConfigError(f"[{section}] {key} 必须是整数") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"[{section}] {key} 不能小于 {minimum}")
    return value


def _float_value(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: float,
) -> float:
    if not parser.has_section(section):
        return default
    raw = parser[section].get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError as exc:
        raise ConfigError(f"[{section}] {key} 必须是数字") from exc


def _str_value(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: str,
) -> str:
    if not parser.has_section(section):
        return default
    raw = parser[section].get(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


def load_app_config(path: str | Path | None = None) -> AppConfig:
    """读取完整配置，缺失项自动使用默认值。"""

    config_path = Path(path) if path is not None else default_config_path()
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding="utf-8"):
        raise ConfigError(f"找不到配置文件: {config_path}")
    if not parser.has_section("llm") and not parser.has_section("openai"):
        raise ConfigError(f"配置文件缺少 [openai]（或兼容的 [llm]）段: {config_path}")

    section_name = "openai" if parser.has_section("openai") else "llm"
    section = parser[section_name]
    api_key = (os.getenv("XAGENT_API_KEY") or section.get("api_key", "")).strip()
    base_url = (os.getenv("XAGENT_BASE_URL") or section.get("base_url", "")).strip()
    model = (os.getenv("XAGENT_MODEL") or section.get("model", "")).strip()

    if not api_key:
        raise ConfigError("未配置 api_key，请在 config.ini 或 XAGENT_API_KEY 中设置")
    if not model:
        raise ConfigError("未配置 model，请在 config.ini 或 XAGENT_MODEL 中设置")

    temperature = _float_value(parser, section_name, "temperature", 0.7)

    context_window: int | None = None
    raw_window = (
        os.getenv("XAGENT_CONTEXT_WINDOW")
        or section.get("context_window", "")
    ).strip()
    if raw_window:
        try:
            context_window = int(raw_window)
        except ValueError as exc:
            raise ConfigError("context_window 必须是整数") from exc
        if context_window <= 0:
            raise ConfigError("context_window 必须是正整数")

    warning_ratio = _float_value(parser, "context", "warning_ratio", 0.6)
    if not 0 < warning_ratio < 1:
        raise ConfigError("context.warning_ratio 必须在 0 和 1 之间")

    session_section = "session" if parser.has_section("session") else "sessions"
    search_api_key = (
        os.getenv("XAGENT_SEARCH_API_KEY")
        or section.get("search_api_key", "")
        or _str_value(parser, "search", "tavily_api_key", "")
        or _str_value(parser, "search", "api_key", "")
        or _str_value(parser, "tools", "search_api_key", "")
    ).strip()
    search_api_url = _str_value(
        parser,
        "search",
        "api_url",
        _str_value(parser, "tools", "search_api_url", "https://api.tavily.com/search"),
    )
    search_max_results = _int_value(
        parser,
        "search",
        "top_k",
        _int_value(parser, "tools", "search_max_results", 5, minimum=1),
        minimum=1,
    )
    web_timeout = _float_value(
        parser,
        "search",
        "timeout",
        _float_value(parser, "tools", "web_timeout", 20.0),
    )

    config = AppConfig(
        llm=LLMConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            context_window=context_window,
        ),
        agent=AgentConfig(
            max_tool_rounds=_int_value(
                parser, "agent", "max_tool_rounds", 8, minimum=1
            ),
            agents_md_file=_str_value(
                parser, "agent", "agents_md_file", "AGENTS.md"
            ),
        ),
        context=ContextConfig(
            default_window=_int_value(
                parser,
                "context",
                "default_window",
                DEFAULT_CONTEXT_WINDOW,
                minimum=1,
            ),
            warning_ratio=warning_ratio,
            compact_target_tokens=_int_value(
                parser, "context", "compact_target_tokens", 5000, minimum=1
            ),
            recall_max_matches=_int_value(
                parser, "context", "recall_max_matches", 8, minimum=1
            ),
            recall_max_chars=_int_value(
                parser, "context", "recall_max_chars", 6000, minimum=1
            ),
            snippet_radius=_int_value(
                parser, "context", "snippet_radius", 160, minimum=1
            ),
            archive_dir=_str_value(
                parser, "context", "archive_dir", ".agents/context"
            ),
        ),
        sessions=SessionConfig(
            directory=_str_value(
                parser, session_section, "dir", ".agents/sessions"
            )
        ),
        tools=ToolsConfig(
            max_text_file_bytes=_int_value(
                parser,
                "tools",
                "max_text_file_bytes",
                10 * 1024 * 1024,
                minimum=1,
            ),
            read_max_chars=_int_value(
                parser, "tools", "read_max_chars", 10000, minimum=1
            ),
            cli_timeout=_int_value(
                parser, "tools", "cli_timeout", 30, minimum=1
            ),
            cli_timeout_max=_int_value(
                parser, "tools", "cli_timeout_max", 300, minimum=1
            ),
            cli_output_max_chars=_int_value(
                parser, "tools", "cli_output_max_chars", 8000, minimum=1
            ),
            web_timeout=web_timeout,
            web_max_chars=_int_value(
                parser, "tools", "web_max_chars", 8000, minimum=1
            ),
            web_max_bytes=_int_value(
                parser, "tools", "web_max_bytes", 2 * 1024 * 1024, minimum=1
            ),
            search_api_url=search_api_url,
            search_api_key=search_api_key,
            search_max_results=search_max_results,
        ),
        mcp=MCPRuntimeConfig(
            connect_timeout=_float_value(
                parser, "mcp", "connect_timeout", 30.0
            ),
            call_timeout=_float_value(parser, "mcp", "call_timeout", 120.0),
            close_timeout=_float_value(parser, "mcp", "close_timeout", 10.0),
        ),
        ui=UIConfig(
            message_max_chars=_int_value(
                parser, "ui", "message_max_chars", 6000, minimum=1
            )
        ),
        skills=SkillsConfig(
            max_name_length=_int_value(
                parser, "skills", "max_name_length", 64, minimum=1
            ),
            max_description_length=_int_value(
                parser, "skills", "max_description_length", 1024, minimum=1
            ),
        ),
    )
    return config


def load_config(path: str | Path | None = None) -> LLMConfig:
    """兼容旧接口：只返回 LLM 配置。"""

    return load_app_config(path).llm
