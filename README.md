# LLM 单次问答

用 `config.ini` 管理 LLM 配置，`main.py` 单次问答（无循环），流式输出 AI 回复，完成后另起一行打印 `---`。

## 文件

- `config.ini` — LLM 配置
- `main.py` — 入口脚本

## 安装

```powershell
python -m pip install openai
```

## 配置

编辑 `config.ini`：

```ini
[llm]
api_key = 你的 API Key
base_url = https://api.deepseek.com/v1
model = deepseek-chat
temperature = 0.7
```

## 运行

```powershell
python main.py
```

## 效果

```
你: 花儿为什么这么红
AI: “花儿为什么这么红”这个问题，可以从科学和文化两个层面来回答……
---
```

## 说明

- 每次运行只问答一次，退出即结束，不保留上下文。
- 终端中文乱码时先执行 `chcp 65001`，或用 `$env:PYTHONIOENCODING="utf-8"` 启动。
- `api_key` 为明文保存，请勿将 `config.ini` 提交到公开仓库。
