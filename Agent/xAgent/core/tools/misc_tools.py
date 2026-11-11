"""示例类工具：当前日期时间与闰年判断。"""

from __future__ import annotations

from datetime import datetime

from core.tools.base import ToolRegistry, ToolSpec


def get_current_datetime() -> dict[str, str]:
    """返回进程所在机器的当前本地日期时间（跨平台，非硬编码）。"""

    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": now.tzname() or "",
    }


def is_leap_year(year: int | str) -> bool:
    value = int(year)
    if value % 400 == 0:
        return True
    if value % 100 == 0:
        return False
    return value % 4 == 0


def check_leap_year(year: int | str) -> str:
    return f"{year} 年{'是' if is_leap_year(year) else '不是'}闰年"


def register_misc_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="getCurrentDateTime",
            description="获取当前本地日期时间、星期与时区（来自系统时钟，跨平台）。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_current_datetime,
        )
    )
    registry.register(
        ToolSpec(
            name="isLeapYear",
            description="判断指定年份是否为闰年，通过 Python 代码精确计算",
            parameters={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，如 2024",
                    },
                },
                "required": ["year"],
            },
            handler=check_leap_year,
        )
    )
