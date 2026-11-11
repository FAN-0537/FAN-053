"""示例类工具：闰年判断。"""

from __future__ import annotations

from core.tools.base import ToolRegistry, ToolSpec


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
