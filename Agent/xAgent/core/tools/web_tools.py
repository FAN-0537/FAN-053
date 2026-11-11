"""网页读取与网络搜索工具。

- ``fetchWebPage``：真实发起 HTTP 请求读取网页，并抽取可读文本。
- ``webSearch``：调用可配置的搜索服务 API（默认 Tavily），返回结构化结果。

两个工具都返回结构化 JSON，失败时由 ToolSpec 统一包装为 ``{"ok": false, "error": ...}``。
"""

from __future__ import annotations

import html
import json
import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config import ToolsConfig
from core.filesystem.support import error, ok
from core.tools.base import ToolRegistry, ToolSpec

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 xAgent"
)

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "li",
    "tr",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "pre",
    "blockquote",
}

# 测试可替换为 httpx.MockTransport。
_TRANSPORT: httpx.AsyncBaseTransport | None = None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        text = data.strip()
        if text:
            self.parts.append(text + " ")

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _html_to_text(source: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(source)
    parser.close()
    return parser.title.strip(), parser.text()


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…（已截断，原长 {len(text)} 字符）", True


def _validate_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return "URL 格式不合法"
    if parsed.scheme not in {"http", "https"}:
        return "仅支持 http/https 网址"
    if not parsed.netloc:
        return "URL 缺少主机名"
    return None


def _new_client(options: ToolsConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=options.web_timeout,
        follow_redirects=True,
        transport=_TRANSPORT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"},
    )


async def fetch_web_page(
    url: str,
    max_chars: int | None = None,
    options: ToolsConfig | None = None,
) -> dict[str, Any]:
    config = options or ToolsConfig()
    problem = _validate_url(url)
    if problem:
        return error(problem)

    limit = max_chars if max_chars is not None else config.web_max_chars
    try:
        async with _new_client(config) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return {"ok": False, "error": "网页请求超时", "code": "timeout"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"网页请求失败: {exc}", "code": "network_error"}

    if response.status_code >= 400:
        return {
            "ok": False,
            "error": f"网页返回 HTTP {response.status_code}",
            "code": f"http_{response.status_code}",
            "url": str(response.url),
        }

    raw = response.content
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if len(raw) > config.web_max_bytes:
        return {"ok": False, "error": "网页内容超过大小上限", "code": "too_large"}

    charset = response.encoding or "utf-8"
    try:
        text = raw.decode(charset, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")

    title = ""
    if "html" in content_type or text.lstrip().lower().startswith(("<!doctype html", "<html")):
        title, text = _html_to_text(text)
    elif "json" in content_type:
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except ValueError:
            pass
    else:
        text = html.unescape(text)

    effective_limit = max(1, int(limit))
    text, truncated = _truncate(text, effective_limit)
    return ok(
        url=str(response.url),
        status=response.status_code,
        content_type=content_type or "unknown",
        title=title,
        truncated=truncated,
        text=text,
    )


async def web_search(
    query: str,
    max_results: int | None = None,
    options: ToolsConfig | None = None,
) -> dict[str, Any]:
    keyword = str(query or "").strip()
    if not keyword:
        return {"ok": False, "error": "query 不能为空", "code": "invalid_argument"}

    config = options or ToolsConfig()
    api_key = (os.getenv("XAGENT_SEARCH_API_KEY") or config.search_api_key or "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": (
                "缺少搜索 API Key。请设置环境变量 XAGENT_SEARCH_API_KEY，"
                "或在 config.ini 的 [tools] search_api_key 中填写。"
            ),
            "code": "missing_api_key",
        }

    count = max_results if max_results is not None else config.search_max_results
    count = max(1, min(int(count), 20))
    payload = {
        "api_key": api_key,
        "query": keyword,
        "max_results": count,
        "search_depth": "basic",
        "include_answer": True,
    }

    try:
        async with _new_client(config) as client:
            response = await client.post(
                config.search_api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": "搜索请求超时", "code": "timeout"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"搜索请求失败: {exc}", "code": "network_error"}

    if response.status_code >= 400:
        return {
            "ok": False,
            "error": f"搜索服务返回 HTTP {response.status_code}: {response.text[:300]}",
            "code": f"http_{response.status_code}",
        }

    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "error": "搜索服务返回的不是合法 JSON", "code": "bad_response"}

    results = data.get("results") if isinstance(data, dict) else None
    cleaned: list[dict[str, Any]] = []
    if isinstance(results, list):
        for item in results[:count]:
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "content": (item.get("content") or "")[:1200],
                    "score": item.get("score"),
                }
            )

    return ok(
        query=keyword,
        answer=(data.get("answer") if isinstance(data, dict) else "") or "",
        count=len(cleaned),
        results=cleaned,
    )


def register_web_tools(registry: ToolRegistry, options: ToolsConfig | None = None) -> None:
    config = options or ToolsConfig()

    async def fetch_handler(url: str, max_chars: int | None = None) -> dict[str, Any]:
        if max_chars is not None:
            max_chars = max(1, min(int(max_chars), config.web_max_chars))
        else:
            max_chars = config.web_max_chars
        return await fetch_web_page(url, max_chars, config)

    registry.register(
        ToolSpec(
            name="fetchWebPage",
            description=(
                "读取 http/https 网页并抽取可读文本。适合读取静态文章、文档页和 JSON 接口。"
                "max_chars 控制返回文本上限，默认使用配置值。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要读取的完整网页地址，例如 https://example.com",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": f"最多返回的字符数，默认 {config.web_max_chars}",
                    },
                },
                "required": ["url"],
            },
            handler=fetch_handler,
        )
    )

    async def search_handler(query: str, max_results: int | None = None) -> dict[str, Any]:
        return await web_search(query, max_results, config)

    registry.register(
        ToolSpec(
            name="webSearch",
            description=(
                "调用搜索服务 API（默认 Tavily）检索互联网信息，返回标题、链接、摘要和可选总结。"
                "需要配置 XAGENT_SEARCH_API_KEY。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或自然语言问题",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": f"返回结果数量，默认 {config.search_max_results}，范围 1-20",
                    },
                },
                "required": ["query"],
            },
            handler=search_handler,
        )
    )
