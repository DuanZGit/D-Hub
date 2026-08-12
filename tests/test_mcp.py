import json
import time

import httpx
import pytest

from dhub.mcp import McpRouter


@pytest.mark.asyncio
async def test_http_mcp_initializes_session_before_tool_call(monkeypatch):
    calls = []

    def upstream(request):
        payload = json.loads(request.content)
        calls.append((payload["method"], request.headers.get("mcp-session-id")))
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-1"},
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {}},
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": [{"name": "echo"}]},
            },
        )

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(upstream)
    monkeypatch.setattr(
        "dhub.mcp.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    result = await McpRouter()._rpc(
        {"transport": "http", "url": "http://upstream.test/mcp"},
        "tools/list",
        {},
    )

    assert result == {"tools": [{"name": "echo"}]}
    assert calls == [
        ("initialize", None),
        ("notifications/initialized", "session-1"),
        ("tools/list", "session-1"),
    ]


def test_http_mcp_decodes_sse_response():
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n',
    )

    assert McpRouter._decode_http_response(response, 7)["result"] == {"ok": True}


def test_clear_drops_tool_cache_sessions_and_session_locks():
    router = McpRouter()
    router.cache["config"] = (time.monotonic() + 60, [])
    router.http_sessions["secret-bearing-key"] = (time.monotonic(), "session-1")
    router.http_session_locks["secret-bearing-key"] = __import__("asyncio").Lock()

    router.clear()

    assert router.cache == {}
    assert router.http_sessions == {}
    assert router.http_session_locks == {}


def test_expired_http_session_and_lock_are_pruned():
    router = McpRouter(session_ttl=10)
    router.http_sessions["old"] = (time.monotonic() - 11, "session-1")
    router.http_session_locks["old"] = __import__("asyncio").Lock()

    router._prune_http_sessions()

    assert "old" not in router.http_sessions
    assert "old" not in router.http_session_locks
