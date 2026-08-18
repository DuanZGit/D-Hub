"""Integration acceptance: fully-local simulated two-device flow (Phase 5).

Simulates Agent A and Agent B on different devices talking through D-Hub:
  1. A writes a project decision to memory
  2. B searches and finds that decision
  3. A sends a structured task to B
  4. B polls and acks the task
  5. B writes a result back to memory
  6. D-Hub keeps provenance
"""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    monkeypatch.setenv("DHUB_ADMIN_KEY", "admin-secret")
    monkeypatch.delenv("DHUB_API_KEY", raising=False)
    for name in list(sys.modules):
        if name == "dhub" or name.startswith("dhub."):
            del sys.modules[name]
    app = importlib.import_module("dhub.app").app
    with TestClient(app) as c:
        yield c


def _admin():
    return {"Authorization": "Bearer admin-secret"}


def _register(client, agent_id, **kw):
    r = client.post("/v1/connector/register", headers=_admin(), json={"agent_id": agent_id, **kw})
    assert r.status_code == 200
    return r.json()["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_two_device_memory_and_task_flow(client):
    token_a = _register(client, "agent-a", capabilities=["memory", "task"])
    token_b = _register(client, "agent-b", capabilities=["memory", "task"])

    # 1. Agent A writes a project decision
    add = client.post(
        "/memory/add",
        headers=_admin(),
        json={
            "namespace": "projects/p1",
            "agent_id": "shared",
            "content": "Decision: use PostgreSQL for the shared memory store.",
            "metadata": {"source": "agent-a", "project": "p1"},
        },
    )
    assert add.status_code == 200

    # 2. Agent B searches and finds that decision
    found = client.post(
        "/memory/search",
        headers=_admin(),
        json={"namespace": "projects/p1", "agent_id": "shared", "query": "postgres"},
    )
    assert found.status_code == 200
    assert any("PostgreSQL" in r["content"] for r in found.json()["results"])

    # 3. Agent A sends a structured task to B
    sent = client.post(
        "/v1/connector/send",
        headers=_hdr(token_a),
        json={
            "sender_agent_id": "agent-a",
            "recipient_agent_id": "agent-b",
            "type": "task",
            "namespace": "projects/p1",
            "project_id": "p1",
            "payload": {"command": "summarize", "topic": "storage"},
            "idempotency_key": "task-001",
        },
    )
    assert sent.status_code == 200
    mid = sent.json()["id"]

    # 4. Agent B polls and acks the task
    polled = client.post(
        "/v1/connector/poll",
        headers=_hdr(token_b),
        json={"agent_id": "agent-b", "project": "p1", "limit": 5},
    )
    assert polled.status_code == 200
    assert polled.json()["count"] == 1
    assert polled.json()["messages"][0]["id"] == mid
    acked = client.post(
        "/v1/connector/ack",
        headers=_hdr(token_b),
        json={"agent_id": "agent-b", "message_id": mid},
    )
    assert acked.status_code == 200

    # 5. Agent B writes the result back to memory
    result = client.post(
        "/memory/add",
        headers=_admin(),
        json={
            "namespace": "projects/p1",
            "agent_id": "shared",
            "content": "Summary: the storage decision favours PostgreSQL for vector search.",
            "metadata": {"source": "agent-b", "in_reply_to": mid, "project": "p1"},
        },
    )
    assert result.status_code == 200

    # 6. D-Hub keeps provenance (audit has connector.send; memory metadata retained)
    audit = client.get("/logs", headers=_admin()).json()["audit"]
    assert any(e.get("action") == "connector.send" for e in audit)
    exported = client.post(
        "/memory/export",
        headers=_admin(),
        params={"namespace": "projects/p1", "agent_id": "shared"},
    ).json()["records"]
    assert any("agent-b" in (r.get("metadata") or {}).get("source", "") for r in exported)
