import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    for name in list(sys.modules):
        if name == "dhub" or name.startswith("dhub."):
            del sys.modules[name]
    with TestClient(importlib.import_module("dhub.app").app) as test_client:
        yield test_client


def test_mcp_config_can_be_managed_and_immediately_merged(client):
    config = {"name": "local", "tools": [{"name": "echo", "description": "test"}]}
    response = client.put(
        "/mcp/configs",
        json={"namespace": "global", "server_id": "local", "config": config},
    )
    assert response.status_code == 200
    tools = client.post("/mcp/tools/list", json={}).json()["tools"]
    assert tools[0]["name"] == "rmcp__local__echo"
    assert (
        client.delete(
            "/mcp/configs", params={"namespace": "global", "server_id": "local"}
        ).status_code
        == 200
    )
    assert client.post("/mcp/tools/list", json={}).json()["tools"] == []


def test_skill_management_respects_project_override(client):
    client.put(
        "/skills", json={"namespace": "global", "name": "review", "content": "global"}
    )
    client.put(
        "/skills",
        json={"namespace": "projects/alpha", "name": "review", "content": "project"},
    )
    result = client.get("/skills/review", params={"project": "alpha"}).json()
    assert result["content"] == "project"
    assert result["source"] == "project"


def test_backup_and_restore_roundtrip(client):
    client.post(
        "/wiki/page",
        json={"namespace": "global", "title": "durable", "content": "before"},
    )
    created = client.post("/backup").json()
    backup_name = created["path"].rsplit("/", 1)[-1]
    client.post(
        "/wiki/page",
        json={"namespace": "global", "title": "durable", "content": "after"},
    )
    restored = client.post(f"/backup/{backup_name}/restore")
    assert restored.status_code == 200
    assert (
        client.get(
            "/wiki/page", params={"namespace": "global", "title": "durable"}
        ).json()["content"]
        == "before"
    )


def test_sync_records_blocked_state_without_model_credentials(client):
    client.post(
        "/memory/add",
        json={"namespace": "global", "agent_id": "shared", "content": "a fact"},
    )
    result = client.post("/sync/trigger").json()
    assert result["status"] == "blocked"
    history = client.get("/sync/history").json()["history"]
    assert history[0]["status"] == "blocked"


def test_audit_records_mutations_without_secrets(client):
    client.post("/register", json={"agent_id": "minis"})
    records = client.get("/logs").json()["audit"]
    assert records[0]["path"] == "/register"
    assert "body" not in records[0]
