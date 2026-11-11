# Practice01 · 多轮流式对话

用 `openai` SDK 调用 OpenAI 兼容接口，演示最基础的多轮流式对话：

- 保留本轮 `history`，支持连续追问
- 流式打印模型回复
- 输入 `exit` 退出
- 配置从 `config.ini` 的 `[openai]` 段读取，代码中不硬编码密钥

## 文件

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序：配置加载 + 多轮流式对话 |
| `config.example.ini` | 配置模板，复制为 `config.ini` 后填写 |
| `config.ini` | 本地真实配置（已被 `.gitignore` 忽略，不要提交） |

## 快速开始

```bash
python -m pip install openai
copy config.example.ini config.ini
```

编辑 `config.ini`：

```ini
[openai]
base_url = https://api.deepseek.com/v1
api_key = your-api-key
model = deepseek-chat
temperature = 0.7
```

运行：

```bash
python main.py
```

## 运行效果

```text
你: 花儿为什么这么红
AI: “花儿为什么这么红”这个问题，可以从科学和文化两个层面来回答……
---
你: 再展开讲讲文化层面
AI: 从文化角度看，红色在中文语境里常与喜庆、吉祥相关……
---
```

## 说明

- 多轮历史只保存在内存中，退出即清空。
- 终端中文乱码时先执行 `chcp 65001`，或设置 `$env:PYTHONIOENCODING = "utf-8"`。
- `config.ini` 不要提交到公开仓库。
