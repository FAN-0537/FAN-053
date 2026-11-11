import asyncio

import httpx

import server


def test_list_pets_returns_structured_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pets"
        assert request.url.params["page"] == "1"
        assert request.url.params["pageSize"] == "10"
        return httpx.Response(
            200,
            json={"code": 200, "message": "ok", "data": {"items": [], "total": 0}},
        )

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(handler))
    result = asyncio.run(server.list_pets())
    assert result["ok"] is True
    assert result["data"]["total"] == 0


def test_upstream_404_is_structured(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "pet not found"})

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(handler))
    result = asyncio.run(server.get_pet("PET-999999"))
    assert result["ok"] is False
    assert result["error"]["code"] == "not_found"
    assert result["error"]["status"] == 404


def test_envelope_error_is_structured(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 500, "message": "database corrupted", "data": None}
        )

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(handler))
    result = asyncio.run(server.get_stats())
    assert result["ok"] is False
    assert result["error"]["code"] == "api_error"
    assert "database corrupted" in result["error"]["message"]


def test_retry_on_503_then_success(monkeypatch) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"message": "temporarily unavailable"})
        return httpx.Response(200, json={"code": 200, "data": {"pets": 1}})

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)
    result = asyncio.run(server.get_stats())
    assert calls["count"] == 2
    assert result["ok"] is True
