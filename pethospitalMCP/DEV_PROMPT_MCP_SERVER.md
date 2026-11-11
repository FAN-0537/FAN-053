# 宠物医院 MCP Server 开发提示词（Python MVP）

> 本文档供 AI Agent 使用，基于 **MCP 协议 2026-07-28**，使用 **Python** 开发宠物医院数据提取 Server 的 **MVP 版本**（仅实现 `list_pets` 功能）。

---

## 一、项目概述

### 目标
开发一个 **MCP Server**（使用 Python），通过 REST API 消费宠物医院管理系统的数据，**MVP 阶段仅实现 `list_pets` 工具**——列出宠物并支持各种参数筛选。

### 源系统
- **项目**：宠物医院 · Pet Hospital REST API（Go 标准库实现）
- **基础 URL**：`http://127.0.0.1:8080`
- **认证**：无鉴权、无登录
- **数据库**：单文件 `data/pet.db`（嵌入式存储引擎）
- **版本**：1.0.0，现有 308 条档案数据
- **API 文档**：`GET /api/v1/endpoints` 返回完整 JSON 接口清单
- **元数据**：`GET /api/v1/meta` 返回枚举字典与字段说明

### MCP 协议与 SDK
- **MCP 协议版本**：`2026-07-28`（最新版）
- **Python SDK**：`mcp` 包 **v2.1.1**（PyPI）
- **Python 版本**：3.10+
- **传输层**：`stdio`（标准输入输出）
- **HTTP 客户端**：`httpx`（异步）
- **关键 import**：
  ```python
  from mcp.server.fastmcp import FastMCP
  import httpx
  import json
  ```

### 依赖安装
```bash
pip install "mcp[cli]" httpx
```

或使用 uv：
```bash
uv add "mcp[cli]" httpx
```

---

## 二、核心架构要求

### 2.1 Server 初始化（FastMCP）
使用 `FastMCP` 类，它提供装饰器风格的 API：
```python
mcp = FastMCP("pet-hospital", version="1.0.0")
```

### 2.2 传输层
通过 `mcp.run()` 启动 stdio 传输：
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 2.3 数据获取模式
Server 作为**代理层**，所有数据通过 `httpx.AsyncClient` 请求 `http://127.0.0.1:8080` 获取：
- 使用 `httpx.AsyncClient` 作为异步 HTTP 客户端
- 所有 REST API 响应信封格式为：
  ```json
  { "code": 200, "message": "ok", "data": { }, "time": "2025-01-01T00:00:00+08:00" }
  ```
- 错误处理：`code != 200` 时抛出异常或返回错误内容

### 2.4 工具注册模式
使用 `@mcp.tool()` 装饰器，类型自动推断 Schema：
```python
@mcp.tool()
async def list_pets(...) -> dict:
    ...
```

---

## 三、MVP 范围：仅实现 `list_pets`

### 3.1 MVP 定义
**只开发一个 MCP Tool：`list_pets`**
- 功能：列出宠物档案
- 支持根据各种参数进行筛选
- 不需要实现 create/update/delete/search/records/charges/stats 等其他功能
- 不需要实现 Resource 和 Prompt

### 3.2 REST API 映射

| REST 方法 | 路径 | MCP Tool 名称 | 说明 |
|-----------|------|---------------|------|
| GET | `/api/v1/pets` | `list_pets` | 列表：过滤+排序+分页 |

### 3.3 `list_pets` 支持的全部查询参数

对应 `GET /api/v1/pets` 的查询字符串参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `species` | str | 按种类筛选 |
| `doctor` | str | 按医生筛选 |
| `status` | str | 按就诊状态筛选 |
| `disease` | str | 按疾病筛选 |
| `ownerName` | str | 按主人姓名筛选 |
| `ownerPhone` | str | 按主人电话筛选 |
| `q` | str | 全文检索关键词（跨字段+病历全文，空格分词AND） |
| `sortBy` | str | 排序字段（name, totalCost, visitCount 等） |
| `order` | str | 排序方向（asc, desc） |
| `page` | int | 页码 |
| `pageSize` | int | 每页条数 |
| `min` | int | 最低总花费 |
| `max` | int | 最高总花费 |

---

## 四、数据模型

### 4.1 Pet 字段（JSON 响应结构）
```python
# 来自 REST API GET /api/v1/pets 的 data 结构
{
    "pets": [
        {
            "id": "PET-000001",
            "name": "旺财",
            "species": "犬",
            "breed": "金毛",
            "gender": "公",
            "ageMonths": 36,
            "color": "金色",
            "chipID": "CHIP-001",
            "ownerName": "张三",
            "ownerPhone": "13800001111",
            "ownerAddress": "北京市",
            "doctor": "李医生",
            "disease": "急性肠胃炎",
            "status": "待就诊",
            "allergy": "无",
            "totalCost": 1200.0,
            "visitCount": 3
        }
    ],
    "total": 308,
    "page": 1,
    "pageSize": 10
}
```

### 4.2 完整字段说明
- **id**: 格式 `PET-XXXXXX`
- **species**: 犬/猫/兔/鸟等 17 种
- **breed**: 品种名
- **gender**: 公/母
- **ageMonths**: 月龄（整数）
- **color**: 毛色
- **chipID**: 芯片号（20% 宠物无）
- **ownerName**: 主人姓名
- **ownerPhone**: 主人电话
- **ownerAddress**: 住址
- **doctor**: 12 位医生之一
- **disease**: 46 种真实兽医疾病之一
- **status**: 待就诊/就诊中/住院中/已康复/慢性病随访
- **allergy**: 过敏史（多数为"无"）
- **totalCost**: 在医院总花费 = charges[].amount 之和（派生字段）
- **visitCount**: 就诊次数 = records 条数（派生字段）

---

## 五、MCP Tool 详细实现

### 5.1 `list_pets` Tool

```python
@mcp.tool()
async def list_pets(
    species: str | None = None,
    doctor: str | None = None,
    status: str | None = None,
    disease: str | None = None,
    owner_name: str | None = None,
    owner_phone: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = 10,
    min_cost: int | None = None,
    max_cost: int | None = None,
) -> dict:
    """
    查询宠物档案列表，支持多种过滤、排序和分页参数。
    
    参数说明：
    - species: 按种类筛选（如 犬、猫）
    - doctor: 按医生筛选
    - status: 按就诊状态筛选
    - disease: 按疾病筛选
    - owner_name: 按主人姓名筛选
    - owner_phone: 按主人电话筛选
    - q: 全文检索关键词（跨字段和病历全文搜索）
    - sort_by: 排序字段（name, totalCost, visitCount 等）
    - order: 排序方向（asc 或 desc）
    - page: 页码（从1开始）
    - page_size: 每页条数
    - min_cost: 最低总花费
    - max_cost: 最高总花费
    """
    # 构建查询参数
    params = {}
    if species is not None:
        params["species"] = species
    if doctor is not None:
        params["doctor"] = doctor
    if status is not None:
        params["status"] = status
    if disease is not None:
        params["disease"] = disease
    if owner_name is not None:
        params["ownerName"] = owner_name
    if owner_phone is not None:
        params["ownerPhone"] = owner_phone
    if q is not None:
        params["q"] = q
    if sort_by is not None:
        params["sortBy"] = sort_by
    if order is not None:
        params["order"] = order
    params["page"] = page
    params["pageSize"] = page_size
    if min_cost is not None:
        params["min"] = min_cost
    if max_cost is not None:
        params["max"] = max_cost

    # 调用 REST API
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "http://127.0.0.1:8080/api/v1/pets",
            params=params
        )
        response.raise_for_status()
        result = response.json()

    # 检查 API 响应码
    if result.get("code") != 200:
        raise Exception(f"API error: code={result.get('code')}, message={result.get('message')}")

    return result["data"]
```

### 5.2 类型推断说明
`FastMCP` 会根据 Python 类型注解自动生成 JSON Schema：
- `str | None = None` → 可选字符串
- `int = 1` → 有默认值的整数
- 函数 docstring 作为 Tool 的 Description
- 参数名使用 snake_case，MCP 层会自动处理

---

## 六、完整项目结构

```
pet-hospital-mcp/
├── server.py              # 入口：初始化 FastMCP、注册 Tool、启动
├── pyproject.toml       # 或 requirements.txt
└── README.md            # 项目说明
```

---

## 七、server.py 完整骨架代码

```python
from mcp.server.fastmcp import FastMCP
import httpx

mcp = FastMCP("pet-hospital", version="1.0.0")


@mcp.tool()
async def list_pets(
    species: str | None = None,
    doctor: str | None = None,
    status: str | None = None,
    disease: str | None = None,
    owner_name: str | None = None,
    owner_phone: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = 10,
    min_cost: int | None = None,
    max_cost: int | None = None,
) -> dict:
    """查询宠物档案列表，支持多种过滤、排序和分页参数。"""
    params = {}
    if species is not None:
        params["species"] = species
    if doctor is not None:
        params["doctor"] = doctor
    if status is not None:
        params["status"] = status
    if disease is not None:
        params["disease"] = disease
    if owner_name is not None:
        params["ownerName"] = owner_name
    if owner_phone is not None:
        params["ownerPhone"] = owner_phone
    if q is not None:
        params["q"] = q
    if sort_by is not None:
        params["sortBy"] = sort_by
    if order is not None:
        params["order"] = order
    params["page"] = page
    params["pageSize"] = page_size
    if min_cost is not None:
        params["min"] = min_cost
    if max_cost is not None:
        params["max"] = max_cost

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("http://127.0.0.1:8080/api/v1/pets", params=params)
        response.raise_for_status()
        result = response.json()

    if result.get("code") != 200:
        raise Exception(f"API error: code={result.get('code')}, message={result.get('message')}")

    return result["data"]


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 八、HTTP 客户端封装建议

虽然 MVP 可以内联在 Tool 函数中，但建议抽取一个异步 HTTP 客户端：

```python
import httpx
from functools import lru_cache

BASE_URL = "http://127.0.0.1:8080"

@lru_cache()
def get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

async def api_get(path: str, params: dict | None = None) -> dict:
    client = get_client()
    response = await client.get(path, params=params)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise Exception(f"API error: code={result.get('code')}, message={result.get('message')}")
    return result["data"]
```

---

## 九、启动与运行

### 9.1 前提条件
1. 确保宠物医院服务已启动：
   ```bash
   # Windows
   pethospital.exe
   # macOS/Linux
   ./pethospital
   ```
2. 确认服务运行在 `http://127.0.0.1:8080`

### 9.2 运行 MCP Server
```bash
# 方式一：直接运行
python server.py

# 方式二：使用 mcp CLI 工具
mcp dev server.py

# 方式三：通过 uv
uv run --with "mcp[cli]" python server.py
```

### 9.3 验证
- 使用 `mcp dev server.py` 打开 MCP Inspector
- 调用 `list_pets` 工具，验证能返回宠物数据
- 测试各种筛选参数

---

## 十、配置与扩展参数

### 10.1 环境变量
支持通过环境变量覆盖默认配置：
- `PET_HOSPITAL_URL`: 宠物医院 API 基础 URL（默认 `http://127.0.0.1:8080`）

```python
import os
BASE_URL = os.environ.get("PET_HOSPITAL_URL", "http://127.0.0.1:8080")
```

### 10.2 pyproject.toml
```toml
[project]
name = "pet-hospital-mcp"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]>=2.0.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 十一、关键约束与注意事项

1. **MCP 协议 2026-07-28**：使用 `mcp v2.1.1`，不使用已废弃特性
2. **无鉴权**：REST API 无需 token 或认证头
3. **只使用 stdio 传输**：`mcp.run(transport="stdio")`
4. **只实现 `list_pets` 一个 Tool**：MVP 不做其他功能
5. **使用 `FastMCP` + 装饰器**：不要用低层 `Server` 类
6. **使用 `httpx.AsyncClient`**：异步 HTTP 调用
7. **类型注解必须完整**：`FastMCP` 依赖类型推断生成 JSON Schema
8. **错误处理**：REST API 返回非 200 code 时抛出异常
9. **超时设置**：HTTP 请求设置 30 秒超时
10. **不硬编码模拟数据**：所有数据必须通过 REST API 获取
11. **Python 3.10+**：使用 `str | None` 语法
12. **返回 dict 类型**：`list_pets` 返回 `dict`，SDK 自动序列化

---

## 十二、验证清单

完成开发后，逐一验证：

- [ ] `pip install "mcp[cli]" httpx` 安装成功
- [ ] `python server.py` 启动无报错
- [ ] `list_pets` Tool 已注册并可在 MCP Inspector 中看到
- [ ] 调用 `list_pets` 无参数能返回宠物列表
- [ ] 调用 `list_pets` 带 `species=犬` 能正确筛选
- [ ] 调用 `list_pets` 带 `doctor=李医生` 能正确筛选
- [ ] 调用 `list_pets` 带 `status=待就诊` 能正确筛选
- [ ] 调用 `list_pets` 带 `page=1&page_size=5` 能正确分页
- [ ] 调用 `list_pets` 带 `sortBy=totalCost&order=desc` 能正确排序
- [ ] 调用 `list_pets` 带 `q=肠胃炎` 能全文检索
- [ ] 调用 `list_pets` 带 `min_cost=100&max_cost=500` 能按花费筛选
- [ ] 协议版本为 `2026-07-28`
- [ ] 所有参数的类型注解正确，Schema 自动生成

---

## 十三、快速启动命令

```bash
# 1. 确保宠物医院服务已启动
pethospital.exe    # Windows
./pethospital      # macOS/Linux

# 2. 创建项目目录
mkdir pet-hospital-mcp && cd pet-hospital-mcp

# 3. 创建虚拟环境
python -m venv venv
# 或
uv venv

# 4. 安装依赖
uv add "mcp[cli]" httpx
# 或
pip install "mcp[cli]" httpx

# 5. 编写 server.py（参考上方代码）

# 6. 运行
python server.py
# 或
mcp dev server.py
```

---

## 十四、参考文档

- MCP Python SDK 文档：https://py.sdk.modelcontextprotocol.io/server
- MCP Python SDK GitHub：https://github.com/modelcontextprotocol/python-sdk
- MCP 规范：https://modelcontextprotocol.io/specification/2026-07-28
- 宠物医院 API 文档：`GET http://127.0.0.1:8080/api/v1/endpoints`
- PyPI 包：https://pypi.org/project/mcp/2.1.1
- httpx 文档：https://www.python-httpx.org/
