# pet-hospital-mcp

宠物医院 REST API 的 **MCP Server**（Python + FastMCP + stdio）。
把本地 `pethospital` 服务的档案、统计和删除能力封装为标准 MCP 工具。

## 工具

| 工具 | 说明 | 关键参数 |
| --- | --- | --- |
| `list_pets` | 查询档案列表，支持筛选、排序、分页 | `species`、`status`、`order`（asc/desc）、`page`（≥1）、`page_size`（1-100） |
| `get_pet` | 按 ID 查询档案详情（含病历与消费明细） | `pet_id` |
| `create_pet` | 新增档案 | 必填 `name/species/owner_name/owner_phone/doctor/disease`；`gender`、`status` 为枚举 |
| `delete_pet` | 按 ID 删除档案 | `pet_id` |
| `get_stats` | 经营统计 | 无 |

返回约定：

- 成功：`{"ok": true, "data": {...}}`
- 失败：`{"ok": false, "error": {"code": "not_found", "message": "...", "status": 404}}`

上游超时、网络错误、非 2xx、业务信封 `code != 2xx`、非 JSON（HTML 错误页）都会转换为结构化错误，
不会把裸异常或 HTML 页面直接抛给模型。429/5xx/超时最多重试 2 次，调用日志写入 stderr（不污染 stdio 协议）。

## 安装

```bash
cd pet-hospital/mcp
python -m pip install -e .
```

或：

```bash
pip install "mcp[cli]" httpx
```

## 前置条件

启动宠物医院服务（Windows 发行包）：

```bash
pethospital.exe
```

默认监听 `http://127.0.0.1:8080`。可用环境变量覆盖：

```bash
set PET_HOSPITAL_URL=http://127.0.0.1:9090
```

## 运行

```bash
python main.py
```

或使用 MCP Inspector：

```bash
mcp dev main.py
```

## 在 MCP 客户端注册

```json
{
  "mcp": {
    "pet-hospital": {
      "type": "local",
      "command": ["python", "pet-hospital/mcp/main.py"],
      "environment": {
        "PYTHONUTF8": "1",
        "PET_HOSPITAL_URL": "http://127.0.0.1:8080"
      },
      "enabled": true
    }
  }
}
```

## 调用示例

```text
用户：列出所有猫，按总花费降序，第一页 5 条
→ list_pets(species="猫", sort_by="totalCost", order="desc", page=1, page_size=5)

用户：新增一只猫，名叫咪咪，主人张三，电话 13800000000，医生李医生，诊断胃炎
→ create_pet(name="咪咪", species="猫", owner_name="张三", owner_phone="13800000000",
             doctor="李医生", disease="胃炎")
```

## 测试

```bash
cd pet-hospital/mcp
python -m pip install pytest
python -m pytest -q
```

测试使用 `httpx.MockTransport`，不访问真实宠物医院服务。

## 目录

```text
pet-hospital/
├── mcp/
│   ├── main.py          # MCP Server
│   ├── pyproject.toml
│   ├── README.md
│   └── tests/
├── windows/             # 宠物医院 Windows 发行包说明
└── docs/                # 开发提示词
```
