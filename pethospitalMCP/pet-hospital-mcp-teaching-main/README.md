# 宠物医院教学后端与 MCP Server

本目录包含课程宠物医院项目的三部分：

- Go 后端源码：`main.go`、`internal/`、`go.mod`、`Makefile`、`build.sh`。
- `windows/`：宠物医院 Windows 发行包说明、接口文档与 `LICENSE`。
- `pet-hospital-mcp-server/`：把宠物医院 REST API 封装为 MCP 工具（FastMCP + stdio）。

> Go 后端为课程教学代码，遵循本目录 `LICENSE`；个人实现为 MCP Server 封装与测试。

## 启动顺序

### 方式一：使用课程发行包

```bash
cd windows
pethospital.exe
```

### 方式二：从源码运行 Go 后端

需要 Go 1.22+：

```bash
go run . -addr 127.0.0.1:8080 -seed -count 100
```

### 启动 MCP Server

```bash
cd pet-hospital-mcp-server
python -m pip install -e ".[test]"
python server.py
```

在 MCP 客户端中注册 `server.py`，或直接运行测试：

```bash
python -m pytest -q
```

完整接口文档见 [`windows/README.md`](windows/README.md)；
MCP 细节见 [`pet-hospital-mcp-server/README.md`](pet-hospital-mcp-server/README.md)。
