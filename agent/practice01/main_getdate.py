import configparser
import json
import subprocess

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(api_key=cfg["llm"]["api_key"], base_url=cfg["llm"]["base_url"])


# ===== 【新增 getDate 工具】开始 =====
def get_date_command():
    """调用本地 date / time 命令获取当前电脑的日期和时间"""
    result = subprocess.run(
        "date /t && time /t",
        shell=True,
        capture_output=True,
        text=True,
        encoding="mbcs",  # Windows 系统 ANSI 编码（中文系统为 GBK）
        errors="ignore",
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return " ".join(lines)


tools = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间，通过调用本地 date 命令实现",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
]


def execute_tool(name, arguments):
    if name == "getDate":
        return get_date_command()
    return f"未知工具: {name}"
# ===== 【新增 getDate 工具】结束 =====


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
            model=cfg["llm"]["model"],
            temperature=float(cfg["llm"]["temperature"]),
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
                        "content": result,
                    }
                )
            continue

        print(f"\nAI: {msg.content}")
        history.append({"role": "assistant", "content": msg.content})
        break
    # --- 【新增】函数调用循环结束 ---
    print("---")
