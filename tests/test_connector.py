"""Tests for the cross-device Agent Connector (Phase 3)."""

import importlib
import sys
import time

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


def _admin_headers():
    return {"Authorization": "Bearer admin-secret"}


def _register(client, agent_id, **kw):
    payload = {"agent_id": agent_id, **kw}
    resp = client.post("/v1/connector/register", headers=_admin_headers(), json=payload)
    assert resp.status_code == 200
    return resp.json()


def _agent_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_one_time_token_and_hides_hash(client):
    result = _register(client, "machine-a", capabilities=["memory", "task"])
    assert result["agent_id"] == "machine-a"
    token = result["token"]
    assert token
    # re-register does not issue a new token
    again = _register(client, "machine-a")
    assert "token" not in again
    agents = client.get("/v1/connector/status", headers=_admin_headers()).json()["agents"]
    assert any(a["agent_id"] == "machine-a" and "token_hash" not in a for a in agents)


def test_two_agents_exchange_via_poll_ack(client):
    a = _register(client, "agent-a")["token"]
    b = _register(client, "agent-b")["token"]
    # A sends a task to B
    sent = client.post(
        "/v1/connector/send",
        headers=_agent_headers(a),
        json={
            "sender_agent_id": "agent-a",
            "recipient_agent_id": "agent-b",
            "type": "task",
            "payload": {"command": "summarize"},
            "idempotency_key": "idem-1",
        },
    )
    assert sent.status_code == 200
    mid = sent.json()["id"]
    # B polls and gets the message
    polled = client.post(
        "/v1/connector/poll",
        headers=_agent_headers(b),
        json={"agent_id": "agent-b", "limit": 10},
    )
    assert polled.status_code == 200
    assert polled.json()["count"] == 1
    assert polled.json()["messages"][0]["id"] == mid
    # B acks
    acked = client.post(
        "/v1/connector/ack",
        headers=_agent_headers(b),
        json={"agent_id": "agent-b", "message_id": mid},
    )
    assert acked.status_code == 200
    # after ack, no longer pending for B
    polled2 = client.post(
        "/v1/connector/poll",
        headers=_agent_headers(b),
        json={"agent_id": "agent-b", "limit": 10},
    )
    assert polled2.json()["count"] == 0


def test_idempotency_duplicate_send(client):
    a = _register(client, "agent-a")["token"]
    _register(client, "agent-b")
    payload = {
        "sender_agent_id": "agent-a",
        "recipient_agent_id": "agent-b",
        "payload": {"x": 1},
        "idempotency_key": "same-key",
    }
    first = client.post("/v1/connector/send", headers=_agent_headers(a), json=payload)
    second = client.post("/v1/connector/send", headers=_agent_headers(a), json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]


def test_unauthorized_token_rejected(client):
    _register(client, "agent-a")
    resp = client.post(
        "/v1/connector/poll",
        headers=_agent_headers("wrong-token"),
        json={"agent_id": "agent-a", "limit": 5},
    )
    assert resp.status_code == 401


def test_offline_message_delivered_on_reconnect(client):
    a = _register(client, "agent-a")["token"]
    b_token = _register(client, "agent-b")["token"]
    # B sends to A while A is offline
    sent = client.post(
        "/v1/connector/send",
        headers=_agent_headers(b_token),
        json={"sender_agent_id": "agent-b", "recipient_agent_id": "agent-a",
              "payload": {"hello": "a"}},
    )
    assert sent.status_code == 200
    # A reconnects and polls
    polled = client.post(
        "/v1/connector/poll",
        headers=_agent_headers(a),
        json={"agent_id": "agent-a", "limit": 5},
    )
    assert polled.json()["count"] == 1


def test_ttl_expiry_moves_to_dead(client):
    a = _register(client, "agent-a")["token"]
    b_token = _register(client, "agent-b")["token"]
    past = str(time.time() - 10)
    client.post(
        "/v1/connector/send",
        headers=_agent_headers(a),
        json={"sender_agent_id": "agent-a", "recipient_agent_id": "agent-b",
              "payload": {}, "expires_at": past},
    )
    polled = client.post(
        "/v1/connector/poll",
        headers=_agent_headers(b_token),
        json={"agent_id": "agent-b", "limit": 5},
    )
    assert polled.json()["count"] == 0
    status = client.get("/v1/connector/status", headers=_admin_headers()).json()
    assert status["dead"] >= 1


def test_recipient_scope_must_match(client):
    a = _register(client, "agent-a", namespace="agents/alpha")["token"]
    b_token = _register(client, "agent-b", namespace="agents/beta")["token"]
    # send to a scope, poll only sees matching scope
    client.post(
        "/v1/connector/send",
        headers=_agent_headers(a),
        json={"sender_agent_id": "agent-a", "recipient_scope": "agents/alpha",
              "namespace": "agents/alpha", "payload": {}},
    )
    # agent-b in different scope should not get it
    polled = client.post(
        "/v1/connector/poll",
        headers=_agent_headers(b_token),
        json={"agent_id": "agent-b", "limit": 5},
    )
    assert polled.json()["count"] == 0


def test_required_capability_enforced(client):
    token_a = _register(client, "agent-a", capabilities=["read"])["token"]
    _register(client, "agent-b")
    # A lacks 'write' capability
    denied = client.post(
        "/v1/connector/send",
        headers=_agent_headers(token_a),
        json={"sender_agent_id": "agent-a", "recipient_agent_id": "agent-b",
              "required_capability": "write", "payload": {}},
    )
    assert denied.status_code == 403
