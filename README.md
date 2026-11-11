# LLM 技术与应用课程项目 · FAN-053

本仓库包含四个可独立运行的部分：宠物医院 MCP Server、AnythingLLM MCP Server、
AnythingLLM 文档上传网页，以及定制终端 Agent `xAgent`。各模块都有独立 README，
本文件给出项目地图、依赖、配置和分步启动方式。

## 项目地图

```text
FAN-053/
├── pethospitalMCP/                                  # A. 宠物医院 REST API + MCP Server
│   ├── DEV_PROMPT_MCP_SERVER.md                     #    课程开发提示词
│   └── pet-hospital-mcp-teaching-main/
│       ├── main.go / internal/                       #    Go REST API（课程教学后端）
│       ├── windows/                                  #    宠物医院 Windows 发行包说明与接口文档
│       └── pet-hospital-mcp-server/
│           ├── server.py                             #    MCP 入口（FastMCP + stdio）
│           ├── tests/                                #    httpx.MockTransport 单元测试
│           └── pyproject.toml
├── anythingllm_mcp1/                                # B. AnythingLLM MCP Server
│   ├── server.py                                    #    MCP 入口（6 个工具）
│   ├── anythingllm_client.py                        #    AnythingLLM API 客户端
│   ├── config.py / .env.example                     #    环境变量配置
│   └── tests/
├── anythingllmserver/                               # C. AnythingLLM 文档上传网页
│   ├── index.html                                   #    单页应用（内联 CSS/JS）
│   └── README.md
├── Agent/
│   ├── Practice01/                                  #    多轮流式对话入门
│   ├── Practice02/                                  #    时间/闰年/文件工具练习
│   └── xAgent/                                      # D. 定制 Agent（core + tui）
│       ├── AGENTS.md                                #    项目长期规则示例
│       ├── core/                                    #    对话循环、工具、MCP、技能、会话、压缩
│       ├── tui/                                     #    Textual 终端界面
│       └── tests/                                   #    pytest 单元测试
└── office/                                          # xAgent 的技能工作区（示例）
    ├── .agents/skills/                              #    demo / minijiami / notice
    └── .mcp.json
```

## 环境要求

| 组件 | 版本 / 说明 |
|---|---|
| Python | 3.10+（开发环境 3.13） |
| Go | 1.22+（可选，用于从源码运行宠物医院后端；也可直接使用 Windows 发行包） |
| 宠物医院服务 | Windows 发行包 `pethospital.exe`（无需 Go/数据库运行时） |
| AnythingLLM | 本地实例，默认 `http://localhost:3001`，需要 API Key 与工作区 |
| 网络 | 网页读取使用 `httpx`；搜索默认使用 Tavily API Key |
| 依赖 | 各子项目的 `requirements.txt` / `pyproject.toml` |

真实密钥只放在各目录下被 `.gitignore` 忽略的本地配置中（`.env`、`config.ini`），
仓库只提供 `.env.example`、`config.example.ini` 等模板。

## 快速开始

### A. 宠物医院 MCP

```bash
# 1) 启动后端（使用课程发行包）
cd pethospitalMCP/pet-hospital-mcp-teaching-main/windows
pethospital.exe

# 2) 安装并启动 MCP Server（stdio）
cd ../pet-hospital-mcp-server
pip install -e ".[test]"
python server.py
```

验证：输出 `test_server.py` 全部通过；MCP 客户端应能枚举 5 个工具。
详见 [`pet-hospital-mcp-server/README.md`](pethospitalMCP/pet-hospital-mcp-teaching-main/pet-hospital-mcp-server/README.md)。

### B. AnythingLLM MCP

```bash
cd anythingllm_mcp1
pip install -e ".[test]"
copy .env.example .env           # 填写 ANYTHINGLLM_API_KEY / BASE_URL / WORKSPACE_SLUG
python server.py                 # stdio
```

工具：`list_workspaces`、`ask_workspace`、`search_workspace`、
`get_workspace_documents`、`upload_document`、`vectorize_workspace`。
详见 [`anythingllm_mcp1/README.md`](anythingllm_mcp1/README.md)。

### C. AnythingLLM 文档上传网页

```bash
cd anythingllmserver
python -m http.server 5173
# 浏览器打开 http://127.0.0.1:5173/
```

页面会提示输入 API Key（不写入代码），随后列出工作区、上传文件并触发向量化。
详见 [`anythingllmserver/README.md`](anythingllmserver/README.md)。

### D. xAgent

```bash
cd Agent/xAgent
pip install -r requirements.txt
copy config.example.ini config.ini
# 修改 [openai] 的 base_url / api_key / model，按需填写 [search]
python main.py
```

`xAgent` 会在后台异步连接当前目录 `.mcp.json` 中的 MCP Server，自动发现工具；
技能放在 `.agents/skills/`，会话与上下文归档分别写入 `.agents/sessions/`、
`.agents/context/`。详见 [`Agent/xAgent/README.md`](Agent/xAgent/README.md)。

## 配置与密钥

| 模块 | 模板 | 必填项 | 说明 |
|---|---|---|---|
| 宠物医院 MCP | 环境变量 | `PET_HOSPITAL_URL` | 默认 `http://127.0.0.1:8080` |
| AnythingLLM MCP | `anythingllm_mcp1/.env.example` | `ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_BASE_URL`、`ANYTHINGLLM_WORKSPACE_SLUG` | 工作区 slug 可用 `list_workspaces` 查询 |
| 网页 | 页面内输入 | API Key | 只保存在 `sessionStorage`，不写死 |
| xAgent | `Agent/xAgent/config.example.ini` | `[openai] base_url`、`api_key`、`model` | 可选 `[search] tavily_api_key` |
| xAgent MCP | `Agent/xAgent/.mcp.json` | 每个 server 填写 | 支持 stdio / streamable_http |

## 验证清单

```bash
# A. 宠物医院 MCP
cd pethospitalMCP/pet-hospital-mcp-teaching-main/pet-hospital-mcp-server
python -m pytest -q

# B. AnythingLLM MCP
cd ../../../anythingllm_mcp1
python -m pytest -q

# D. xAgent 单元测试
cd ../Agent/xAgent
python -m pytest -q

# D. xAgent 启动
python main.py
```

手工验证：

- 浏览器打开 `http://127.0.0.1:8080/` 可访问宠物医院界面。
- AnythingLLM 网页上传文档后，工作区文档数增加，并可提问。
- xAgent TUI 输入 `/status` 可看到模型、上下文与 MCP 状态。

## 目录与代码规模

| 目录 | 语言 | 规模（约） |
|---|---|---|
| `Agent/xAgent` | Python | 4,500+ 行，core/tui 分层 |
| `Agent/Practice02` | Python | 950 行，三个递进示例 |
| `pethospitalMCP/.../pet-hospital-mcp-server` | Python | 300 行，5 个 MCP 工具 |
| `anythingllm_mcp1` | Python | 700 行，6 个 MCP 工具 |
| `anythingllmserver` | HTML/JS | 单页，约 450 行 |
| `office` | Markdown | 3 个示例技能 |

## 第三方与许可

- `pethospitalMCP/pet-hospital-mcp-teaching-main/windows`：课程宠物医院发行包说明，遵循其自带 `LICENSE`。
- `office/.agents/skills/*`：本仓库自建示例技能，不含第三方技能包。
- 个人实现为 `Agent/xAgent`、两个 MCP Server 的封装、网页与各模块文档/测试。
