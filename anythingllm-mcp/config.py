"""AnythingLLM MCP Server 配置。

配置来源优先级：环境变量 > 同目录 .env 文件。
真实密钥不得写入仓库；`.env.example` 只提供字段模板。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:3001/api"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2


class ConfigError(RuntimeError):
    """配置缺失或非法。"""


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：只支持 KEY=VALUE / export KEY=VALUE 与 # 注释。"""

    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    base_url: str
    api_key: str
    workspace_slug: str | None
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES


def load_settings(dotenv_path: str | Path | None = None) -> Settings:
    path = Path(dotenv_path) if dotenv_path is not None else Path(__file__).with_name(".env")
    _load_dotenv(path)

    base_url = (os.getenv("ANYTHINGLLM_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    api_key = (os.getenv("ANYTHINGLLM_API_KEY") or "").strip()
    workspace_slug = (os.getenv("ANYTHINGLLM_WORKSPACE_SLUG") or "").strip() or None

    if not base_url.startswith(("http://", "https://")):
        raise ConfigError("ANYTHINGLLM_BASE_URL 必须以 http:// 或 https:// 开头")
    if not api_key:
        raise ConfigError(
            "缺少 ANYTHINGLLM_API_KEY。请在 AnythingLLM 的 Settings -> Developer API "
            "中创建 API Key，并写入环境变量或本地 .env 文件。"
        )

    timeout = _float_env("ANYTHINGLLM_TIMEOUT", DEFAULT_TIMEOUT)
    if timeout <= 0:
        raise ConfigError("ANYTHINGLLM_TIMEOUT 必须大于 0")
    retries = _int_env("ANYTHINGLLM_RETRIES", DEFAULT_RETRIES)
    if retries < 0:
        raise ConfigError("ANYTHINGLLM_RETRIES 不能为负数")

    return Settings(
        base_url=base_url,
        api_key=api_key,
        workspace_slug=workspace_slug,
        timeout=timeout,
        retries=retries,
    )
