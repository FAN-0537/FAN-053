# Practice02 · 基于大模型 Function Calling 的命令行 Agent 实践

本目录包含三个逐步递进的命令行（CLI）对话 Agent 示例，采用 OpenAI 兼容的
`/chat/completions` 接口，演示 **Function Calling（工具调用）** 与 **流式输出**。

| 文件 | 说明 | 内置工具 |
| --- | --- | --- |
| `main-getdate.py` | 入门版：让模型通过工具获取本机当前日期时间 | `getDate` |
| `main-isleapyear.py` | 进阶版：在 `getDate` 基础上增加闰年判断工具 | `getDate`、`isLeapYear` |
| `main-filetools.py` | 完整版：具备本地文件/目录读写与操作能力 | 11 个文件系统工具 |

> 架构图：`main-filetools-architecture.mmd`（Mermaid 格式，可在 GitHub、VS Code 插件、
> Mermaid Live Editor 中渲染）。

---

## 一、环境准备

### 1. 依赖

```bash
pip install openai
```

其余模块（`configparser`、`json`、`os`、`subprocess`、`shutil`、`pathlib`）均为 Python 标准库。

### 2. 配置文件

复制 `config.example.ini` 为 `config.ini`，填写真实参数：

```ini
[openai]
base_url = https://api.deepseek.com/v1
api_key = your-api-key
model = deepseek-chat
temperature = 0.7
```

### 3. 运行

```bash
python main-getdate.py
python main-isleapyear.py
python main-filetools.py
```

---

## 二、main-getdate.py

- 声明无参数工具 `getDate`。
- 通过 Windows 的 `date /t && time /t` 获取当前日期时间，并使用 `mbcs`/`utf-8` 解码。
- 模型返回 `tool_calls` 后执行工具，把结果以 `role=tool` 回填，再次请求模型。

## 三、main-isleapyear.py

- 在 `getDate` 基础上增加 `isLeapYear(year: integer)`。
- 闰年规则：能被 4 整除且不能被 100 整除，或能被 400 整除。
- 工具结果统一回填 `tool_call_id`，支持同轮多个工具调用。

## 四、main-filetools.py

- 11 个文件/目录工具：当前目录、列目录、文件类型、读文件、创建文件、
  编辑/追加/替换、创建目录、删除目录、删除文件、重命名、闰年。
- 所有工具返回 JSON 字符串；`execute_tool` 统一捕获未知工具与内部异常。
- 安全保护：拒绝删除磁盘根目录与当前工作目录及其上级；创建文件不覆盖；
  文件名校验拒绝路径分隔符；读取限制 10 MB 并支持截断。
- 危险操作保护、编码探测和响应封装位于 `_ok` / `_err` / `_path` /
  `_detect_text_encoding` / `_guard_destructive`。

## 五、返回值约定

```json
{"ok": true, "path": "...", "count": 4, "entries": []}
{"ok": false, "error": "错误描述"}
```

`execute_tool` 对未知工具和函数异常做统一兜底，不会让主循环崩溃。

## 已知限制

- 无对话历史长度控制，长会话会持续增长 `history`。
- 工具结果直接单行打印，不做流式输出。
- `rename_item` 仅支持同目录改名，不支持跨目录移动。
