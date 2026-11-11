# 练习 01 · 多轮问答与 getDate 工具

用 `config.ini` 管理 LLM 配置，演示两条渐进路线：

- `main.py`：多轮问答（保留 `history`），流式输出 AI 回复，输入 `exit` 退出。
- `main_getdate.py`：在 Function Calling 循环中注册 `getDate` 工具，调用本地 `date/time` 命令获取当前日期时间，并支持多轮工具调用。

## 文件

- `config.ini` — 本地 LLM 配置（`api_key` 留空）
- `config.example.ini` — 配置模板
- `main.py` — 多轮流式问答
- `main_getdate.py` — `getDate` 工具调用示例

## 安装

```powershell
python -m pip install openai
```

## 配置

复制模板并填写：

```powershell
copy config.example.ini config.ini
```

```ini
[llm]
api_key = 你的 API Key
base_url = https://api.deepseek.com/v1
model = deepseek-chat
temperature = 0.7
```

## 运行

```powershell
python main.py          # 多轮问答
python main_getdate.py  # getDate 工具调用
```

## 效果

```text
你: 花儿为什么这么红
AI: “花儿为什么这么红”这个问题，可以从科学和文化两个层面来回答……
---
你: 现在几点
[工具调用 getDate] -> 2026/11/11 10:30
AI: 当前时间是 2026/11/11 10:30。
```

## 说明

- `main.py` 会保留本轮会话历史；输入 `exit` 退出，不写入磁盘。
- `main_getdate.py` 使用 Windows 的 `date /t && time /t`，非 Windows 环境请改为对应命令。
- 终端中文乱码时先执行 `chcp 65001`，或设置 `$env:PYTHONIOENCODING = "utf-8"`。
- `api_key` 不要提交到公开仓库；`.gitignore` 已忽略本地密钥文件。
