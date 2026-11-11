# AnythingLLM MCP Server

把本机 **AnythingLLM** 的工作区、文档和对话能力封装成标准 **MCP Server**（stdio）。
工具可以被 opencode、Claude Desktop 等任意 MCP 客户端枚举和调用。

## 能力覆盖

| 语义 | MCP 工具 | 对应 AnythingLLM API |
| --- | --- | --- |
| 工作区管理 | `list_workspaces` | `GET /api/v1/workspaces` |
| 查看工作区文档 | `get_workspace_documents` | `GET /api/v1/workspace/{slug}` |
| 对话问答 | `ask_workspace` | `POST /api/v1/workspace/{slug}/chat` |
| 向量检索 | `search_workspace` | `POST /api/v1/workspace/{slug}/vector-search` |
| 上传文档 | `upload_document` | `POST /api/v1/document/upload` + `update-embeddings` |
| 重新向量化 | `vectorize_workspace` | `POST /api/v1/workspace/{slug}/update-embeddings` |

所有工具成功时返回 `{"ok": true, "data": ...}`；
失败时返回 `{"ok": false, "error": {"code": "...", "message": "...", "status": 401}}`，
不会把上游 HTML 错误页或裸异常直接抛给模型。

## 安装

```bash
cd anythingllm-mcp
python -m pip install -r requirements.txt
```

## 配置

复制模板并填写（`.env` 已被 `.gitignore` 排除，不要提交真实密钥）：

```bash
copy .env.example .env
```

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | 否 | 默认 `http://localhost:3001/api` |
| `ANYTHINGLLM_API_KEY` | **是** | AnythingLLM → Settings → Developer API 中创建 |
| `ANYTHINGLLM_WORKSPACE_SLUG` | 否 | 固定工作区；留空时自动选择唯一工作区 |
| `ANYTHINGLLM_TIMEOUT` | 否 | 请求超时秒数，默认 30 |
| `ANYTHINGLLM_RETRIES` | 否 | 429/5xx/超时重试次数，默认 2 |

环境变量的优先级高于 `.env`。

## 前置条件

1. 启动 AnythingLLM 桌面端，确认 `http://localhost:3001` 可访问。
2. 在 AnythingLLM 中至少创建一个工作区，并上传文档完成向量化。
3. 生成 API Key（未生成时接口会返回 `403 No valid api key found`）。

## 在 MCP 客户端中注册

opencode / Claude Desktop 的本地 server 配置示例：

```json
{
  "mcp": {
    "anythingllm": {
      "type": "local",
      "command": ["python", "anythingllm-mcp/server.py"],
      "environment": {
        "PYTHONUTF8": "1",
        "ANYTHINGLLM_API_KEY": "your-key"
      },
      "enabled": true
    }
  }
}
```

也可以把 `ANYTHINGLLM_*` 写进 `anythingllm-mcp/.env`，客户端只负责启动进程。

## 调用示例

在 MCP 客户端中直接对话即可，例如：

- “列出我的 AnythingLLM 工作区” → `list_workspaces`
- “用 assistant-chats 工作区回答：项目文档里怎么配置模型？” → `ask_workspace`
- “把 D:/docs/report.pdf 上传并向量化到 assistant-chats” → `upload_document`
- “在 demo 工作区里检索‘部署步骤’” → `search_workspace`

失败示例：

```json
{
  "ok": false,
  "error": {
    "code": "workspace_ambiguous",
    "message": "存在多个工作区，请显式指定 workspace_slug。可用工作区: a, b",
    "status": 400
  }
}
```

## 测试

```bash
cd anythingllm-mcp
python -m pytest -q
```

测试使用 `httpx.MockTransport`，不会访问真实 AnythingLLM。

## 已知限制

- 仅实现 stdio 传输；如需远程部署，可在 MCP 客户端侧用 `mcp-proxy` 等工具转换。
- 文档上传走本机文件路径，服务端需要能读到该路径。
- 流式回答（SSE）未接入；`ask_workspace` 返回完整回答与引用来源。
