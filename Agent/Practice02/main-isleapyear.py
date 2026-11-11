import configparser
import json

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")
if cfg.has_section("llm") and not cfg.has_section("openai"):
    cfg["openai"] = cfg["llm"]

client = OpenAI(api_key=cfg["openai"]["api_key"], base_url=cfg["openai"]["base_url"])


# ===== 【新增 isLeapYear 工具】开始 =====
def is_leap_year(year):
    """用 Python 代码计算 year 是否为闰年：能被4整除且不能被100整除，或能被400整除"""
    year = int(year)
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    return year % 4 == 0


def check_leap_year(year):
    leap = is_leap_year(year)
    return f"{year} 年{'是' if leap else '不是'}闰年"


tools = [
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断指定年份是否为闰年，通过 Python 代码精确计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，如 2024",
                    },
                },
                "required": ["year"],
            },
        },
    }
]


def execute_tool(name, arguments):
    if name == "isLeapYear":
        return check_leap_year(arguments["year"])
    return f"未知工具: {name}"
# ===== 【新增 isLeapYear 工具】结束 =====


history = []  # 本轮会话的多轮聊天记录

while True:
    question = input("\n你: ").strip()

    if question.lower() == "exit":
        print("已退出。")
        break

    history.append({"role": "user", "content": question})

    # --- 【新增】函数调用循环：模型请求调用工具则执行并回传结果，直到返回普通文本 ---
    while True:
        response = client.chat.completions.create(
            model=cfg["openai"]["model"],
            temperature=float(cfg["openai"]["temperature"]),
            messages=history,
            tools=tools,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            history.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                result = execute_tool(tc.function.name, args)
                print(f"\n[工具调用 {tc.function.name}] -> {result}")
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
                    }
                )
            continue

        print(f"\nAI: {msg.content}")
        history.append({"role": "assistant", "content": msg.content})
        break
    # --- 【新增】函数调用循环结束 ---
    print("---")
