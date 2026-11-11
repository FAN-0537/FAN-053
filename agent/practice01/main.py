import configparser
import time  # 【新增循环代码块】

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(api_key=cfg["llm"]["api_key"], base_url=cfg["llm"]["base_url"])

# ===== 【新增循环代码块】开始 =====
ENABLE_SLEEP = True   # 延时开关：True 开启，False 关闭
SLEEP_SECONDS = 1     # 每轮间隔秒数
# ===== 【新增循环代码块】结束 =====

history = []  # 【新增】本轮会话的多轮聊天记录

# ===== 【新增循环代码块】开始：最外层 while True 包裹 =====
while True:
    # --- 以下为原有 Agent 代码（仅整体缩进一层，逻辑一行未改） ---
    question = input("\n你: ").strip()

    # --- 【新增循环代码块】：可选退出机制，输入 exit 跳出 ---
    if question.lower() == "exit":
        print("已退出。")
        break
    # --- 【新增循环代码块】结束 ---

    # --- 【新增】把本轮提问记入聊天记录 ---
    history.append({"role": "user", "content": question})

    print("\nAI: ", end="", flush=True)
    reply = ""  # 【新增】累积流式返回内容，用于写回聊天记录
    for chunk in client.chat.completions.create(
        model=cfg["llm"]["model"],
        temperature=float(cfg["llm"]["temperature"]),
        messages=history,  # 【新增】携带之前的所有聊天记录
        stream=True,
    ):
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
            reply += chunk.choices[0].delta.content  # 【新增】
    # --- 【新增】把 AI 回复记入聊天记录 ---
    history.append({"role": "assistant", "content": reply})
    print("\n---")

    # --- 【新增循环代码块】：可选延时，仅做间隔控制 ---
    if ENABLE_SLEEP:
        time.sleep(SLEEP_SECONDS)
    # --- 【新增循环代码块】结束 ---
# ===== 【新增循环代码块】结束 =====
