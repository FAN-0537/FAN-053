"""AnythingLLM REST API 客户端。

所有请求都打到 AnythingLLM 官方 `/api/v1/*` 端点；失败统一转换为
``AnythingLLMError``（包含机器可读 code、HTTP 状态码和可读消息）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}
ERROR_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    429: "rate_limited",
    500: "server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class AnythingLLMError(RuntimeError):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status is not None:
            payload["status"] = self.status
        return payload


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else f"HTTP {response.status_code}"
    if isinstance(data, dict):
        for key in ("error", "message", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return str(data)[:500]


class AnythingLLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise AnythingLLMError("missing_api_key", "缺少 AnythingLLM API Key")
        self.base_url = base_url.rstrip("/")
        self.retries = max(0, int(retries))
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AnythingLLMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: AnythingLLMError | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                last_error = AnythingLLMError(
                    "timeout", f"AnythingLLM 请求超时: {exc}", None
                )
            except httpx.HTTPError as exc:
                last_error = AnythingLLMError(
                    "network_error", f"无法连接 AnythingLLM: {exc}", None
                )
            else:
                if response.status_code in RETRY_STATUS and attempt < self.retries:
                    time.sleep(min(0.5 * (2**attempt), 4.0))
                    continue
                if response.status_code >= 400:
                    raise AnythingLLMError(
                        ERROR_CODE_BY_STATUS.get(
                            response.status_code, f"http_{response.status_code}"
                        ),
                        _error_message(response),
                        response.status_code,
                    )
                if response.status_code == 204 or not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {
                        "raw": response.text,
                        "content_type": response.headers.get("content-type", ""),
                    }

            if attempt < self.retries:
                time.sleep(min(0.5 * (2**attempt), 4.0))

        assert last_error is not None
        raise last_error

    # ---- 工作区 ---------------------------------------------------------
    def list_workspaces(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/v1/workspaces")
        if isinstance(data, dict):
            workspaces = data.get("workspaces")
            if isinstance(workspaces, list):
                return [item for item in workspaces if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def get_workspace(self, slug: str) -> dict[str, Any]:
        data = self._request("GET", f"/v1/workspace/{slug}")
        if isinstance(data, dict):
            workspace = data.get("workspace")
            if isinstance(workspace, dict):
                return workspace
            return data
        return {}

    def resolve_workspace(self, slug: str | None = None, configured: str | None = None) -> str:
        explicit = (slug or configured or "").strip()
        workspaces = self.list_workspaces()
        slugs = [
            str(item.get("slug") or item.get("name") or "").strip()
            for item in workspaces
        ]
        slugs = [item for item in slugs if item]
        if explicit:
            if slug and slugs and explicit not in slugs:
                raise AnythingLLMError(
                    "workspace_not_found",
                    f"工作区不存在: {explicit}。可用工作区: {', '.join(slugs)}",
                    404,
                )
            return explicit
        if not slugs:
            raise AnythingLLMError(
                "workspace_not_found", "AnythingLLM 中没有可用工作区", 404
            )
        if len(slugs) > 1:
            raise AnythingLLMError(
                "workspace_ambiguous",
                f"存在多个工作区，请显式指定 workspace_slug。可用工作区: {', '.join(slugs)}",
                400,
            )
        return slugs[0]

    # ---- 对话 -----------------------------------------------------------
    def chat(
        self,
        slug: str,
        message: str,
        *,
        mode: str = "query",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": message, "mode": mode}
        if session_id:
            payload["sessionId"] = session_id
        data = self._request("POST", f"/v1/workspace/{slug}/chat", json=payload)
        return data if isinstance(data, dict) else {"raw": data}

    def vector_search(
        self,
        slug: str,
        query: str,
        *,
        top_n: int = 4,
    ) -> dict[str, Any]:
        data = self._request(
            "POST",
            f"/v1/workspace/{slug}/vector-search",
            json={"query": query, "topN": top_n},
        )
        return data if isinstance(data, dict) else {"raw": data}

    # ---- 文档与向量化 ---------------------------------------------------
    def upload_document(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise AnythingLLMError("file_not_found", f"文件不存在: {path}", 404)
        mime = "application/octet-stream"
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".csv"}:
            mime = "text/plain"
        elif suffix == ".pdf":
            mime = "application/pdf"
        elif suffix in {".json"}:
            mime = "application/json"
        with path.open("rb") as file:
            data = self._request(
                "POST",
                "/v1/document/upload",
                files={"file": (path.name, file.read(), mime)},
            )
        return data if isinstance(data, dict) else {"raw": data}

    def list_workspace_documents(self, slug: str) -> list[dict[str, Any]]:
        workspace = self.get_workspace(slug)
        documents = workspace.get("documents")
        if not isinstance(documents, list):
            return []
        return [item for item in documents if isinstance(item, dict)]

    def update_embeddings(
        self,
        slug: str,
        *,
        adds: list[str] | None = None,
        deletes: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {"adds": adds or [], "deletes": deletes or []}
        data = self._request(
            "POST", f"/v1/workspace/{slug}/update-embeddings", json=payload
        )
        return data if isinstance(data, dict) else {"raw": data}

    def vectorize_workspace(self, slug: str) -> dict[str, Any]:
        documents = self.list_workspace_documents(slug)
        locations = [
            str(item.get("location") or "").strip()
            for item in documents
            if str(item.get("location") or "").strip()
        ]
        if not locations:
            return {
                "workspace": slug,
                "vectorized": False,
                "message": "工作区没有可向量化的文档",
            }
        result = self.update_embeddings(slug, adds=locations)
        return {
            "workspace": slug,
            "vectorized": True,
            "document_count": len(locations),
            "result": result,
        }

    def add_document_to_workspace(
        self, slug: str, document_location: str
    ) -> dict[str, Any]:
        result = self.update_embeddings(slug, adds=[document_location])
        return {
            "workspace": slug,
            "document": document_location,
            "result": result,
        }
