"""Fake-server contract tests for the TencentDB Agent Memory adapter (Phase 2).

No real credentials are used. httpx.MockTransport simulates the Tencent v3
data-plane responses. E2E against a real service is marked NOT VERIFIED.
"""

import time

import httpx
import pytest

from dhub.backends.tencent_backend import TencentAgentMemoryBackend
from dhub.memory_models import (
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)


def _make_backend(handler, retries=0, **env):
    transport = httpx.MockTransport(handler)
    return TencentAgentMemoryBackend(transport=transport), env


def _ok_handler(store):
    """A fake Tencent v3 data plane backed by an in-memory dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content or b"{}")
        path = request.url.path
        if not path.endswith("/conversation/add"):
            # conversation/query, conversation/search, conversation/delete,
            # atomic/update
            if path.endswith("/conversation/query"):
                rows = list(store.values())
                sid = body.get("session_id")
                if sid:
                    rows = [r for r in rows if r["session_id"] == sid]
                return httpx.Response(
                    200, json={"code": 0, "data": {"messages": rows, "total": len(rows)}}
                )
            if path.endswith("/conversation/search"):
                rows = [
                    r for r in store.values()
                    if body.get("query", "").lower() in r["content"].lower()
                ]
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "data": {"results": rows[: body.get("limit", 10)], "total": len(rows)},
                    },
                )
            if path.endswith("/conversation/delete"):
                ids = body.get("message_ids") or []
                for rid in ids:
                    store.pop(rid, None)
                return httpx.Response(200, json={"code": 0, "data": {"deleted": len(ids)}})
            if path.endswith("/atomic/update"):
                rid = body.get("id")
                if rid in store:
                    store[rid]["content"] = body.get("content")
                    store[rid]["metadata"] = store[rid].get("metadata", {})
                return httpx.Response(200, json={"code": 0, "data": {"id": rid}})
            return httpx.Response(200, json={"code": 0, "data": {}})

        # add
        messages = body.get("messages") or []
        content = messages[0]["content"] if messages else ""
        rid = f"msg-{len(store) + 1}"
        store[rid] = {
            "id": rid,
            "session_id": body.get("session_id"),
            "agent_id": body.get("agent_id"),
            "user_id": body.get("user_id"),
            "role": "assistant",
            "content": content,
            "metadata": messages[0].get("metadata") or {},
            "timestamp": "2026-01-01T00:00:00Z",
            "recorded_at": "2026-01-01T00:00:00Z",
        }
        return httpx.Response(
            200, json={"code": 0, "data": {"accepted_ids": [rid]}}
        )

    return handler


def _env(**kwargs):
    env = {
        "DHUB_AGENT_MEMORY_URL": "https://memory.tencentyun.com",
        "DHUB_AGENT_MEMORY_API_KEY": "sk-test-placeholder",
        "DHUB_AGENT_MEMORY_SERVICE_ID": "mem-test",
        "DHUB_AGENT_MEMORY_TIMEOUT_MS": "2000",
        "DHUB_AGENT_MEMORY_RETRIES": "0",
    }
    env.update(kwargs)
    return env


@pytest.fixture
def backend_env(monkeypatch):
    def _apply(**over):
        for k, v in _env(**over).items():
            monkeypatch.setenv(k, v)
    _apply()
    return monkeypatch


def _record(content="remember the plan", namespace="agents/codex", agent_id="codex"):
    return MemoryRecord(content=content, namespace=namespace, agent_id=agent_id)


def test_successful_add_and_search(backend_env):
    store = {}
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(_ok_handler(store)))
    result = backend.add(_record())
    assert result.status == "ok"
    assert result.external_id
    hits = backend.search(
        MemoryQuery(query="plan", namespace="agents/codex", agent_id="codex")
    )
    assert len(hits) == 1
    assert "plan" in hits[0].content


def test_empty_result(backend_env):
    store = {}
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(_ok_handler(store)))
    hits = backend.search(
        MemoryQuery(query="nothing", namespace="global", agent_id="shared")
    )
    assert hits == []


def test_get_and_delete(backend_env):
    store = {}
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(_ok_handler(store)))
    added = backend.add(_record())
    rid = added.external_id
    got = backend.get(rid, MemoryScope(namespace="agents/codex", agent_id="codex"))
    assert got is not None and got.id == rid
    deleted = backend.delete(rid, MemoryScope(namespace="agents/codex", agent_id="codex"))
    assert deleted.status == "ok"
    assert backend.get(rid, MemoryScope(namespace="agents/codex", agent_id="codex")) is None


def test_timeout(backend_env, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    result = backend.add(_record())
    assert result.status == "error"
    assert "timeout" in (result.error or "")


def test_429_retries_then_succeeds(backend_env, monkeypatch):
    calls = {"n": 0}
    store = {}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"code": 429, "message": "rate limited"})
        return _ok_handler(store)(request)

    monkeypatch.setenv("DHUB_AGENT_MEMORY_RETRIES", "3")
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    result = backend.add(_record())
    assert result.status == "ok"
    assert calls["n"] >= 3


def test_401_auth_failure_not_retried(backend_env, monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"code": 401, "message": "unauthorized"})

    monkeypatch.setenv("DHUB_AGENT_MEMORY_RETRIES", "3")
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    result = backend.add(_record())
    assert result.status == "error"
    assert "authentication" in (result.error or "")
    assert calls["n"] == 1  # not retried


def test_500_failure(backend_env):
    def handler(request):
        return httpx.Response(500, json={"code": 500, "message": "boom"})

    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    result = backend.add(_record())
    assert result.status == "error"


def test_malformed_response(backend_env):
    def handler(request):
        return httpx.Response(200, content=b"<html>not json</html>")

    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    result = backend.add(_record())
    assert result.status == "error"
    assert "malformed" in (result.error or "")


def test_version_config_path(backend_env, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"code": 0, "data": {}})

    monkeypatch.setenv("DHUB_AGENT_MEMORY_API_VERSION", "v2")
    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    backend.add(_record())
    assert any(p.startswith("/v2/") for p in seen)


def test_not_configured_does_not_raise():
    backend = TencentAgentMemoryBackend()  # no env
    health = backend.health()
    assert health.ok is False
    result = backend.add(_record())
    assert result.status == "error"


def test_circuit_breaker(backend_env, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"code": 500, "message": "boom"})

    backend = TencentAgentMemoryBackend(transport=httpx.MockTransport(handler))
    backend._circuit.max_failures = 2
    backend._circuit.cooldown_s = 60
    backend.add(_record())
    backend.add(_record())
    # circuit should now be open
    result = backend.add(_record())
    assert result.status == "error"
    assert "circuit" in (result.error or "")
