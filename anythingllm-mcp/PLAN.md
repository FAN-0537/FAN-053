# AnythingLLM MCP Server — MVP 开发计划

> 状态：**已实现（见同目录 `server.py` / `anythingllm_client.py` / `README.md`）**
> 初版目标：从唯一一个工作区提取信息进行 AI 回答
> 实现扩展：工作区枚举、文档上传/向量化、向量检索、结构化错误与重试
>
> 本文件保留为设计记录；以 README 与代码为准。

---

## 1. 背景与目标

开发一个本地 MCP Server（Python），桥接本机安装的 **AnythingLLM**（桌面版，`http://localhost:3001`），对外暴露**一个 MCP 工具**：用户提问题 → 基于唯一工作区（`Assistant Chats`）内的知识库内容 → 返回 AI 回答 + 引用来源。

### 1.1 本机环境已验证事实
| 项目 | 结论 |
|---|---|
| 服务进程 | `AnythingLLM.exe` 监听 `127.0.0.1:3001` |
| 数据目录 | `C:\Users\fan li\AppData\Roaming\anythingllm-desktop\storage` |
| 数据库 | `anythingllm.db`（SQLite，只读查询已确认） |
| 唯一工作区 | 名称 `Assistant Chats`，slug **`assistant-chats`** |
| API 规范 | OpenAPI 3.0，base path `/api`，认证 `Authorization: Bearer <token>` |
| 关键端点 | `GET /v1/workspaces`、`POST /v1/workspace/{slug}/chat`、`POST /v1/workspace/{slug}/stream-chat`、`POST /v1/workspace/{slug}/vector-search` |

### 1.2 ⚠️ 前置阻塞项（最新状态，2026-09-20 复核）
- **本实例 `api_keys` 表仍为空（COUNT=0）**，已实时查询 `anythingllm.db` 确认。
- 用户先后提供的两个 key（已脱敏）**均未被注册**，`/api/v1/auth` 均返回 `403 "No valid api key found"`。
- **正确获取方式**：AnythingLLM 界面 → 设置(Settings) → **Developer API / API Keys** → 新建并复制。生成时该 key 会即时写入本机 `api_keys` 表，之后才能通过 Bearer 认证。
- **两个推进方案（二选一，待用户确认）**：
  - **A（推荐，无风险）**：用户在 UI 内生成 key 后发我 → 用 curl 验证 `authenticated:true` 再开发。
  - **B（需用户同意）**：我在开发阶段把给定 key 的 SHA-256 哈希直接插入 `anythingllm.db` 的 `api_keys` 表（开发前先备份 DB，仅限本地单用户环境）。
- 正式 key 仅放 `.env`，不入库、不提交。

---

## 2. 技术选型（已确认）

| 项 | 选择 |
|---|---|
| 语言 | Python 3.13.7（本机已装） |
| MCP | 官方 `mcp` Python SDK（**最新版**）。用户要求的 `2026-97-28` 为非合法版本号（MCP 协议版本格式为 `YYYY-MM-DD`），**已确认改为：不写死，由 SDK 自动协商其支持的最新协议版本** |
| 传输方式 | **stdio**（与现有 `pet-hospital-mcp` 一致，便于 opencode 等客户端本地调用） |
| HTTP 客户端 | `httpx`（`mcp` 依赖中自带，无需额外引入 requests） |
| 配置读取 | `python-dotenv` |
| 入口约定 | 与现有约定一致：Python 直跑 + `PYTHONUTF8=1` |

---

## 3. 目录结构（MVP）

```
D:\xie\anythingllm-mcp\
├── server.py              # MCP 入口（FastMCP + stdio），注册唯一工具
├── anythingllm_client.py  # AnythingLLM REST API 客户端封装
├── config.py              # 读取 .env（BASE_URL / API_KEY / WORKSPACE_SLUG）
├── requirements.txt       # mcp, httpx, python-dotenv
├── .env                   # 本地配置（不入库）
├── .env.example           # 配置模板（含注释）
├── PLAN.md                # 本文件
└── README.md              # 最终使用说明（M3 阶段补齐）
```

> 放在子目录 `D:\xie\anythingllm-mcp\`，不动已有的 `pet-hospital-mcp` 等项目。

---

## 4. 功能设计

### 4.1 唯一 MCP 工具：`ask_workspace`

**输入参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | string | ✔ | 用户问题 |
| `mode` | string | ✘ | `chat`（多轮，结合历史，默认）或 `query`（单轮，纯检索回答） |
| `session_id` | string | ✘ | 多轮会话延续（对应 AnythingLLM 的 sessionId） |

**执行流程**
1. 启动时（或首次调用时）`GET /api/v1/workspaces` 获取工作区列表；若 `.env` 未配置 slug，自动取唯一工作区；若配置了，校验其存在。
2. `POST /api/v1/workspace/{slug}/chat`，body：
   ```json
   { "message": "<query>", "mode": "chat|query", "sessionId": "<optional>" }
   ```
3. 返回结构化结果：
   ```json
   {
     "answer": "<textResponse>",
     "sources": [ { "title": "<文档标题>", "chunk": "<引用片段>" } ]
   }
   ```

**错误处理（MCP 内以清晰文本报错）**
- `401/403` → 「AnythingLLM API key 无效，请检查 .env」
- `404` → 「工作区不存在或 slug 错误」
- 网络/超时 → 连接失败提示

### 4.2 初版范围之外（后续实现状态）
- ✅ 多工作区选择/切换（`list_workspaces` + `workspace_slug` 参数）
- ❌ 流式回答（SSE / stream-chat）仍未实现
- ✅ 独立的 vector-search 工具（`search_workspace`）
- ✅ 文档上传 / 工作区管理类工具（`upload_document`、`vectorize_workspace`）
- ❌ 跨工作区检索仍未实现

---

## 5. 配置设计（.env）

```ini
ANYTHINGLLM_BASE_URL=http://localhost:3001/api
ANYTHINGLLM_API_KEY=<UI 新生成的 key>
# 留空则自动发现唯一工作区；预填可跳过启动探测
ANYTHINGLLM_WORKSPACE_SLUG=assistant-chats
```

---

## 6. 开发里程碑

### M0 — 前置验证（阻塞项，需用户配合）
- [ ] 生成有效 key：UI → Settings → Developer API / API Keys → 新建（或在确认后由我方案 B 直插 DB）
- [ ] 用 curl 验证：`GET /api/v1/auth` → `{"authenticated":true}`；`GET /api/v1/workspaces` → 返回 `assistant-chats`

### M1 — 脚手架
- `requirements.txt`、`config.py`（含默认值与报错）、空 `server.py`（FastMCP 挂在 stdio）
- 用 `mcp dev server.py` 验证客户端能握手（此步不依赖真实 API key）

### M2 — AnythingLLM 客户端 + 冒烟
- `anythingllm_client.py`：`list_workspaces()`、`chat(slug, message, mode, session_id)`
- 写一个独立 CLI 冒烟入口（`python anythingllm_client.py "问题"`）直接用真实 key 跑通
- 若 M0 未完成，可用 mock/fixture 先行写逻辑，冒烟留待 key 到位

### M3 — 工具接入
- 注册 `ask_workspace`，透传参数、解析 `textResponse` + `sources`
- 在 `opencode.json` 增加注册项（仿照既有 `pet-hospital`）：
  ```json
  "anythingllm": {
    "type": "local",
    "command": ["C:\\Users\\fan li\\AppData\\Local\\Programs\\Python\\Python313\\python.exe", "D:\\xie\\anythingllm-mcp\\server.py"],
    "environment": { "PYTHONUTF8": "1" },
    "enabled": true
  }
  ```

### M4 — 测试与文档
- 覆盖：问答返回、来源引用、错误分支（坏 key、坏 slug、超时）
- README：安装、配置、连接方式、示例调用

---

## 7. 验收标准

在 opencode（或其他 MCP 客户端）中调用 `ask_workspace("你工作区里有什么")`：
- ✅ 返回基于 `assistant-chats` 工作区内容的回答
- ✅ 附带引用来源（标题 + 片段）
- ✅ 错误场景提示清晰

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| API key 未生成 | 阻塞 M0/M1 真实调用 | 客户端逻辑先用 mock 写，验证等 key；不阻塞架构搭建 |
| 服务重启/迁移 | 数据路径可能变化 | 配置全部走 .env，不硬编码 |
| 聊天模式污染会话 | `mode=chat` 累积上下文 | MVP 默认 `query` 单轮，`chat` 需显式传入 |
| 并发 | 不影响 | 单工作区、单客户端，无需锁 |