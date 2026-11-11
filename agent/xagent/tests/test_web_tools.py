import asyncio

import httpx

from core.config import ToolsConfig
from core.tools import web_tools


def test_html_extraction_strips_scripts() -> None:
    title, text = web_tools._html_to_text(
        "<html><head><title>标题</title><style>.a{}</style></head>"
        "<body><h1>Hello</h1><script>alert(1)</script><p>世界</p></body></html>"
    )
    assert title == "标题"
    assert "Hello" in text
    assert "世界" in text
    assert "alert" not in text


def test_fetch_web_page_uses_http_and_extracts_text(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) in {"https://example.com", "https://example.com/"}
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><title>T</title><body><p>可读内容</p></body></html>",
        )

    monkeypatch.setattr(web_tools, "_TRANSPORT", httpx.MockTransport(handler))
    result = asyncio.run(
        web_tools.fetch_web_page("https://example.com", 1000, ToolsConfig())
    )
    assert result["ok"] is True
    assert result["title"] == "T"
    assert "可读内容" in result["text"]


def test_web_search_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("XAGENT_SEARCH_API_KEY", raising=False)
    result = asyncio.run(web_tools.web_search("xagent", options=ToolsConfig()))
    assert result["ok"] is False
    assert result["code"] == "missing_api_key"


def test_web_search_parses_results(monkeypatch) -> None:
    monkeypatch.setenv("XAGENT_SEARCH_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        return httpx.Response(
            200,
            json={
                "answer": "总结",
                "results": [
                    {"title": "A", "url": "https://a.example", "content": "内容", "score": 0.9}
                ],
            },
        )

    monkeypatch.setattr(web_tools, "_TRANSPORT", httpx.MockTransport(handler))
    options = ToolsConfig(search_api_url="https://search.example/search")
    result = asyncio.run(web_tools.web_search("xagent", options=options))
    assert result["ok"] is True
    assert result["answer"] == "总结"
    assert result["results"][0]["title"] == "A"
