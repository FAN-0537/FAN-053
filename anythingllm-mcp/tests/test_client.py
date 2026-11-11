"""AnythingLLM 客户端单元测试（不访问真实服务）。"""

from __future__ import annotations

import json

import httpx

from anythingllm_client import AnythingLLMClient, AnythingLLMError


def _client(handler) -> AnythingLLMClient:
    return AnythingLLMClient(
        "http://localhost:3001/api",
        "test-key",
        retries=0,
        transport=httpx.MockTransport(handler),
    )


def test_list_workspaces_reads_real_api_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path == "/api/v1/workspaces"
        return httpx.Response(
            200,
            json={"workspaces": [{"slug": "demo", "name": "Demo", "documents": []}]},
        )

    with _client(handler) as client:
        workspaces = client.list_workspaces()
    assert workspaces[0]["slug"] == "demo"


def test_resolve_workspace_reports_ambiguity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "workspaces": [
                    {"slug": "a", "name": "A"},
                    {"slug": "b", "name": "B"},
                ]
            },
        )

    with _client(handler) as client:
        try:
            client.resolve_workspace(None, None)
        except AnythingLLMError as exc:
            assert exc.code == "workspace_ambiguous"
        else:  # pragma: no cover
            raise AssertionError("应当提示工作区歧义")


def test_chat_posts_message_and_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/workspace/demo/chat"
        payload = json.loads(request.content)
        assert payload == {"message": "hello", "mode": "query"}
        return httpx.Response(200, json={"textResponse": "hi", "sources": []})

    with _client(handler) as client:
        result = client.chat("demo", "hello")
    assert result["textResponse"] == "hi"


def test_update_embeddings_posts_adds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/workspace/demo/update-embeddings"
        assert json.loads(request.content) == {"adds": ["custom-documents/a.txt"], "deletes": []}
        return httpx.Response(200, json={"message": "ok"})

    with _client(handler) as client:
        client.update_embeddings("demo", adds=["custom-documents/a.txt"])


def test_http_error_is_structured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "No valid api key found"})

    with _client(handler) as client:
        try:
            client.list_workspaces()
        except AnythingLLMError as exc:
            assert exc.code == "forbidden"
            assert exc.status == 403
            assert "api key" in exc.message.lower()
        else:  # pragma: no cover
            raise AssertionError("401/403 应转换为结构化错误")
