"""命令行工具定义。

仅用于受控教学实验环境：本阶段不提供命令白名单、黑名单或审批机制，
命令以运行 xAgent 的当前用户权限执行。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.config import ToolsConfig
from core.filesystem.support import error, ok
from core.tools.base import ToolRegistry, ToolSpec

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_OUTPUT_CHARS = 8000


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, dict[str, Any]]:
    original_chars = len(text)
    if original_chars <= limit:
        return text, {
            "truncated": False,
            "original_chars": original_chars,
            "returned_chars": original_chars,
        }
    marker = f"\n...[输出已截断，原长度 {original_chars} 字符，仅显示前 {limit} 字符]"
    return text[:limit] + marker, {
        "truncated": True,
        "original_chars": original_chars,
        "returned_chars": limit,
    }


def _coerce_timeout(
    value: int | str | None,
    default: int,
    maximum: int,
) -> int:
    try:
        timeout = int(value) if value is not None else default
    except (TypeError, ValueError):
        timeout = default
    return max(1, min(timeout, maximum))


def register_cli_tools(
    registry: ToolRegistry,
    cwd: str | Path | None = None,
    config: ToolsConfig | None = None,
) -> None:
    options = config or ToolsConfig()
    workdir = (Path(cwd) if cwd is not None else Path.cwd()).expanduser().resolve()

    def run_cli(
        command: str,
        args: list[str] | None = None,
        timeout: int | str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(command, str) or not command.strip():
            return error("参数 command 必须是非空的程序名称")

        if args is None:
            args = []
        elif isinstance(args, str):
            return error("参数 args 必须是字符串数组，例如 [\"--version\"]")
        elif not isinstance(args, (list, tuple)):
            return error("参数 args 必须是字符串数组")

        argv = [command, *(str(arg) for arg in args)]
        timeout_seconds = _coerce_timeout(
            timeout, options.cli_timeout, options.cli_timeout_max
        )

        try:
            completed = subprocess.run(
                argv,
                cwd=str(workdir),
                capture_output=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
        except FileNotFoundError:
            return error(f"命令不存在或无法启动: {command}")
        except PermissionError:
            return error(f"没有权限执行命令: {command}")
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_info = _truncate(
                _decode(exc.stdout), options.cli_output_max_chars
            )
            stderr, stderr_info = _truncate(
                _decode(exc.stderr), options.cli_output_max_chars
            )
            return {
                "ok": False,
                "error": f"命令执行超时（{timeout_seconds} 秒）",
                "command": argv,
                "cwd": str(workdir),
                "exitcode": None,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_info": stdout_info,
                "stderr_info": stderr_info,
            }
        except OSError as exc:
            return error(f"命令启动失败: {exc}")

        stdout, stdout_info = _truncate(
            _decode(completed.stdout), options.cli_output_max_chars
        )
        stderr, stderr_info = _truncate(
            _decode(completed.stderr), options.cli_output_max_chars
        )

        return ok(
            command=argv,
            cwd=str(workdir),
            exitcode=completed.returncode,
            success=completed.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            stdout_info=stdout_info,
            stderr_info=stderr_info,
        )

    registry.register(
        ToolSpec(
            name="RunCli",
            description=(
                "调用本地已安装的命令行程序并返回标准输出、标准错误和退出码。"
                "command 为程序名称（如 python、git、where），args 为参数数组；"
                "不会经过 Shell 解析，因此不能使用管道、重定向或 Shell 内置命令。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的程序名称或可执行文件路径，如 python 或 git",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "传给程序的参数数组，如 [\"--version\"] 或 [\"status\", \"--short\"]",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            f"执行超时时间（秒），默认 {options.cli_timeout}，"
                            f"最大 {options.cli_timeout_max}"
                        ),
                    },
                },
                "required": ["command"],
            },
            handler=run_cli,
        )
    )
