"""AnythingLLM MCP Server（stdio）。

工具按语义覆盖三类能力：
- 工作区：列出工作区、查看工作区文档
- 文档：上传文档、加入工作区并触发向量化
- 对话/检索：基于工作区问答、向量检索

启动：
    python server.py
客户端配置（例如 opencode.json）：
    {
      "type": "local",
      "command": ["python", "anythingllm_mcp1/server.py"],
      "environment": {"PYTHONUTF8": "1"}
    }
"""

from __future__ import annotations

import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from anythingllm_client import AnythingLLMClient, AnythingLLMError
from config import ConfigError, Settings, load_settings

mcp = FastMCP("anythingllm")

_SETTINGS: Settings | None = None
_CLIENT: AnythingLLMClient | None = None


def _settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings()
    return _SETTINGS


def _client() -> AnythingLLMClient:
    global _CLIENT
    if _CLIENT is None:
        settings = _settings()
        _CLIENT = AnythingLLMClient(
            settings.base_url,
            settings.api_key,
            timeout=settings.timeout,
            retries=settings.retries,
        )
    return _CLIENT


def _fail(code: str, message: str, status: int | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if status is not None:
        error["status"] = status
    return {"ok": False, "error": error}


def _run(action: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "data": action()}
    except AnythingLLMError as exc:
        return _fail(exc.code, exc.message, exc.status)
    except ConfigError as exc:
        return _fail("config_error", str(exc))
    except Exception as exc:  # noqa: BLE001 - 工具边界必须返回结构化错误
        return _fail("internal_error", f"{type(exc).__name__}: {exc}")


@mcp.tool()
def list_workspaces() -> dict[str, Any]:
    """列出 AnythingLLM 中所有工作区（slug、名称、文档数量等）。"""

    def action() -> Any:
        workspaces = _client().list_workspaces()
        return {
            "count": len(workspaces),
            "workspaces": [
                {
                    "slug": item.get("slug") or item.get("name"),
                    "name": item.get("name"),
                    "document_count": len(item.get("documents") or []),
                }
                for item in workspaces
            ],
        }

    return _run(action)


@mcp.tool()
def ask_workspace(
    query: str,
    workspace_slug: str | None = None,
    mode: Literal["query", "chat"] = "query",
    session_id: str | None = None,
) -> dict[str, Any]:
    """基于指定工作区的知识库回答问题。

    - query: 用户问题（必填）
    - workspace_slug: 工作区 slug；留空时自动使用唯一工作区，多工作区会报错
    - mode: query=单轮纯检索；chat=结合会话历史
    - session_id: chat 模式下用于延续多轮会话
    """

    def action() -> Any:
        if not query.strip():
            raise AnythingLLMError("invalid_argument", "query 不能为空", 400)
        client = _client()
        settings = _settings()
        slug = client.resolve_workspace(workspace_slug, settings.workspace_slug)
        result = client.chat(
            slug, query.strip(), mode=mode, session_id=session_id
        )
        sources = result.get("sources") or []
        return {
            "workspace": slug,
            "answer": result.get("textResponse")
            or result.get("response")
            or result.get("answer")
            or "",
            "sources": sources,
            "mode": mode,
            "session_id": result.get("id") or session_id,
            "raw": result,
        }

    return _run(action)


@mcp.tool()
def search_workspace(
    query: str,
    workspace_slug: str | None = None,
    top_n: int = Field(default=4, ge=1, le=20),
) -> dict[str, Any]:
    """在工作区向量库中检索相关文档片段（不调用大模型）。"""

    def action() -> Any:
        if not query.strip():
            raise AnythingLLMError("invalid_argument", "query 不能为空", 400)
        client = _client()
        settings = _settings()
        slug = client.resolve_workspace(workspace_slug, settings.workspace_slug)
        result = client.vector_search(slug, query.strip(), top_n=top_n)
        return {"workspace": slug, "query": query, "results": result}

    return _run(action)


@mcp.tool()
def get_workspace_documents(workspace_slug: str | None = None) -> dict[str, Any]:
    """列出工作区当前已挂载的文档（名称、类型、向量化状态等）。"""

    def action() -> Any:
        client = _client()
        settings = _settings()
        slug = client.resolve_workspace(workspace_slug, settings.workspace_slug)
        documents = client.list_workspace_documents(slug)
        return {
            "workspace": slug,
            "count": len(documents),
            "documents": [
                {
                    "name": item.get("title")
                    or item.get("name")
                    or item.get("location"),
                    "location": item.get("location"),
                    "type": item.get("docType") or item.get("type"),
                }
                for item in documents
            ],
        }

    return _run(action)


@mcp.tool()
def upload_document(
    file_path: str,
    workspace_slug: str | None = None,
    vectorize: bool = True,
) -> dict[str, Any]:
    """上传本地文档到 AnythingLLM，并可立即加入工作区并触发向量化。"""

    def action() -> Any:
        client = _client()
        settings = _settings()
        slug = client.resolve_workspace(workspace_slug, settings.workspace_slug)
        uploaded = client.upload_document(file_path)
        documents = uploaded.get("documents") or []
        location = ""
        if documents and isinstance(documents[0], dict):
            location = str(documents[0].get("location") or "")
        if not location:
            location = str(uploaded.get("location") or uploaded.get("name") or "")

        added = None
        if vectorize and location:
            added = client.add_document_to_workspace(slug, location)

        return {
            "workspace": slug,
            "uploaded": uploaded,
            "location": location,
            "vectorized": bool(added),
            "vectorize_result": added,
        }

    return _run(action)


@mcp.tool()
def vectorize_workspace(workspace_slug: str | None = None) -> dict[str, Any]:
    """把工作区中尚未向量化的文档重新提交向量化。"""

    def action() -> Any:
        client = _client()
        settings = _settings()
        slug = client.resolve_workspace(workspace_slug, settings.workspace_slug)
        return client.vectorize_workspace(slug)

    return _run(action)


def main() -> None:
    # 启动时做一次配置体检，但缺失 key 只打印到 stderr，不阻塞 MCP 握手，
    # 这样客户端仍可枚举工具并看到结构化错误。
    try:
        load_settings()
    except ConfigError as exc:
        print(f"[anythingllm_mcp1] 配置提示: {exc}", file=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
