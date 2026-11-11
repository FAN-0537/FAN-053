# main_fileops.py —— 本地文件系统 AI 助手

一个基于 **OpenAI 兼容接口（Function Calling / Tools）** 的命令行 AI 助手，让大模型通过工具调用真实地查看、读取、创建、编辑、删除本地文件与目录。所有文件操作均返回 JSON 字符串，模型据此继续推理或直接答复用户。

## 目录结构

```
practice02/
├── main_fileops.py      # 主程序：配置加载、工具定义、调度与 REPL 循环
├── config.ini           # LLM 配置（api_key / base_url / model / temperature）
├── architecture.mmd     # Mermaid 代码架构图（纯文本）
├── main_leapyear.py     # 闰年判断示例（独立脚本）
└── README.md            # 本说明
```

## 架构总览

架构图见 [`architecture.mmd`](./architecture.mmd)，可直接用支持 Mermaid 的渲染器（GitHub、VS Code 插件、mermaid.live 等）打开。

整体分为五层：

| 层次 | 组成 | 职责 |
| --- | --- | --- |
| 配置层 | `config.ini`、`BASE_DIR`、`client` | 读取 `[llm]` 段配置并构造 `OpenAI` 客户端 |
| 入口层 | `main()`、`SYSTEM_PROMPT` | 初始化对话历史，进入 REPL 循环 |
| 对话循环 | `client.chat.completions.create`、`history` | 多轮对话 + 工具调用回灌，直到模型不再请求工具 |
| 调度层 | `tools`（11 个 schema）、`TOOL_FUNCTIONS`、`execute_tool` | 把模型返回的 `tool_calls` 映射到具体函数并统一异常处理 |
| 能力层 | 11 个文件操作实现函数 | 真正执行磁盘读写，返回统一 JSON 结果 |
| 公共支撑 | `_ok` / `_err` / `_path` / `_detect_text_encoding` / `_guard_destructive` | 响应封装、路径规范化、编码探测、危险操作保护 |

## 环境准备

```bash
pip install openai
```

`config.ini` 示例：

```ini
[llm]
api_key = sk-xxxxxxxxxxxxxxxx
base_url = https://api.deepseek.com/v1
model = deepseek-chat
temperature = 0.7
```

> 注意：`config.ini` 中含明文 API Key，请勿提交到公开仓库，建议改用环境变量或 `.gitignore` 排除。

## 运行

```bash
python main_fileops.py
```

交互示例：

```
你: 看看当前目录有什么
[工具调用 listDirectory] -> {"ok": true, "path": "...", "count": 4, "entries": [...]}
AI: 当前目录下有 4 个条目，分别是 ...
---
你: exit
已退出。
```

输入 `exit`（不区分大小写）退出程序。

## 工具清单

模型侧工具名为驼峰式，Python 侧实现为下划线式，两者通过 `TOOL_FUNCTIONS` 映射。

| 工具名 | 实现函数 | 说明 | 关键参数 |
| --- | --- | --- | --- |
| `isLeapYear` | `check_leap_year` | 判断年份是否闰年（基于 `is_leap_year`） | `year` |
| `getCurrentDirectory` | `get_current_directory` | 返回当前工作目录 | 无 |
| `listDirectory` | `list_directory` | 列出目录内容，目录优先、名称升序 | `path`（默认 `.`） |
| `getFileType` | `get_file_type` | 返回扩展名、MIME、是否纯文本及编码 | `path` |
| `readFile` | `read_file` | 读取纯文本文件，自动识别 UTF-8/GBK | `path`、`max_chars`（默认 10000） |
| `createFile` | `create_file` | 创建新文件，可自动建目录，**不覆盖已有文件** | `directory`、`filename`、`content`、`create_dirs` |
| `editFile` | `edit_file` | 编辑文本文件，支持三种模式 | `path`、`content`、`mode`、`old_text`、`new_text` |
| `createDirectory` | `create_directory` | 创建目录（可递归创建上级） | `path` |
| `deleteDirectory` | `delete_directory` | 递归删除目录及其全部内容 | `path` |
| `deleteFile` | `delete_file` | 删除单个文件 | `path` |
| `renameItem` | `rename_item` | 重命名文件或目录（同目录内改名） | `source`、`new_name` |

### `editFile` 的三种模式

- `overwrite`：整体覆盖文件内容（默认）。
- `append`：追加内容到末尾（`utf-8-sig` 文件追加时改用 `utf-8`，避免重复写入 BOM）。
- `replace`：按 `old_text` → `new_text` 做全文替换，必须同时提供两者；找不到原文时返回错误，成功时返回替换次数 `replaced`。

## 返回值约定

所有工具函数返回 JSON 字符串，便于直接回灌给模型：

- 成功：`{"ok": true, ...}`，附带 `path`、`size`、`entries`、`replaced` 等业务字段。
- 失败：`{"ok": false, "error": "错误描述"}`。

`execute_tool` 对未知工具名和函数内部异常做统一兜底，分别返回 `未知工具: xxx` 与 `工具执行失败: xxx`，不会让主循环崩溃。

## 安全与健壮性设计

- **危险操作保护**（`_guard_destructive`）：禁止删除/重命名磁盘根目录，禁止操作当前工作目录及其上级目录。
- **不覆盖写入**：`create_file` 使用 `"x"` 模式独占创建；`rename_item` 在目标已存在时直接报错。
- **文件名校验**：`create_file` / `rename_item` 拒绝空名、`.`、`..` 以及包含路径分隔符的名称。
- **编码探测**（`_detect_text_encoding`）：读取前 64 KB 采样，含 `\x00` 判为二进制，识别 `utf-8-sig` BOM，依次尝试 `utf-8`、`gbk`；无法解码则拒绝读写，避免损坏二进制文件。
- **大小限制**：`MAX_TEXT_FILE_BYTES = 10 MB`，超出则拒绝读取。
- **读取截断**：`read_file` 按 `max_chars` 截断并返回 `truncated` 标记。
- **异常收敛**：文件系统操作统一捕获 `OSError` / `UnicodeDecodeError`，转为错误 JSON 返回。

## 扩展新工具

1. 在文件中新增实现函数，返回 `_ok(...)` / `_err(...)`。
2. 在 `tools` 列表中追加对应的 function schema（`name`、`description`、`parameters`）。
3. 在 `TOOL_FUNCTIONS` 字典中注册 `"工具名": 实现函数`。

无需修改 `execute_tool` 与 `main()`。

## 已知限制

- 无对话历史长度控制，长会话会持续增长 `history`，可能触及模型上下文上限。
- 不支持流式输出，工具调用结果直接以 JSON 单行打印。
- `rename_item` 仅支持同目录改名，不支持跨目录移动。
- 文本编辑按整文件读写实现，超大文件的 `replace` 会较慢。
