# office · xAgent 技能工作区

本目录用于演示 `Agent/xAgent` 的 Agent Skills 机制：在 `office/` 下启动 xAgent 时，
它会扫描 `.agents/skills/`，只把每个技能的 `name` 与 `description` 注入系统提示，
模型需要时再通过 `loadSkill` 读取完整 `SKILL.md` 或附件。

## 目录

```text
office/
├── .agents/
│   ├── skills/
│   │   ├── demo/          # 最小结构示例
│   │   ├── minijiami/     # 数字转中文大写（自建示例）
│   │   └── notice/        # 公司通知撰写（自建示例）
│   ├── context/           # 上下文压缩归档（运行时生成，不应提交）
│   └── sessions/          # 会话日志（运行时生成，不应提交）
├── config.ini             # 本地配置（已忽略）
└── .mcp.json              # MCP Server 配置
```

## 使用

```bash
cd office
copy ..\Agent\xAgent\config.example.ini config.ini
# 编辑 config.ini 的 [openai] 段
python ..\Agent\xAgent\main.py
```

xAgent 会读取当前目录下的 `.mcp.json`，并在后台异步连接
`pethospitalMCP` 与 `anythingllm_mcp1`；连接失败不会阻塞主流程。

## 示例技能

- `demo`：演示 frontmatter + 正文 + 附件目录的最小结构。
- `minijiami`：把阿拉伯数字金额转成中文大写金额，适合合同/票据。
- `notice`：按“部门 + 事项”规范撰写公司内部通知，并引用示例文件。

## 说明

这些技能为自建示例，用于演示渐进加载；不包含第三方技能包。
