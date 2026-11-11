"""TUI 启动入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.bootstrap import build_runtime
from core.config import ConfigError, default_config_path, ensure_config_file
from tui.app import ConfigNoticeApp, FileOpsTuiApp


def main() -> None:
    parser = argparse.ArgumentParser(description="XAgent 文件操作助手 TUI")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径")
    parser.add_argument("--workspace", type=Path, default=None, help="工作目录")
    args = parser.parse_args()

    config_path = args.config or default_config_path()
    try:
        if ensure_config_file(config_path):
            ConfigNoticeApp(config_path).run()
            return
        runtime = build_runtime(config_path, args.workspace)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        FileOpsTuiApp(runtime).run()
    finally:
        runtime.session.close()


if __name__ == "__main__":
    main()
