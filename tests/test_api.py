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
    app = importlib.import_module("dhub.app").app
    with TestClient(app) as c:
        yield c


def test_health_and_dashboard_have_all_modules(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert client.get("/ui").status_code == 200
    for module in [
        "overview",
        "agents",
        "mcp",
        "memory",
        "wiki",
        "skills",
        "files",
        "sync",
        "logs",
        "config",
        "backup",
    ]:
        assert client.get(f"/dashboard/{module}").status_code == 200


def test_register_and_list_agent(client):
    r = client.post(
        "/register",
        json={
            "agent_id": "minis",
            "host": "phone",
            "tools": ["wiki"],
            "projects": ["alpha"],
        },
    )
    assert r.status_code == 200 and r.json()["agent_id"] == "minis"
    assert client.get("/agents").json()["agents"][0]["agent_id"] == "minis"


def test_mcp_project_overrides_agent_and_global(client, tmp_path):
    for tier, desc in [
        ("global", "global"),
        ("agents/minis", "agent"),
        ("projects/alpha", "project"),
    ]:
        d = tmp_path / "mcp" / tier
        d.mkdir(parents=True, exist_ok=True)
        (d / "server.json").write_text(
            '{"name":"server","tools":[{"name":"echo","description":"' + desc + '"}]}'
        )
    tools = client.post(
        "/mcp/tools/list", json={"agent_id": "minis", "project": "alpha"}
    ).json()["tools"]
    assert tools == [
        {"name": "rmcp__server__echo", "description": "project", "server": "server"}
    ]


def test_memory_namespaces_are_isolated(client):
    added = client.post(
        "/memory/add",
        json={
            "namespace": "projects/alpha",
            "agent_id": "minis",
            "content": "PostgreSQL is selected",
        },
    ).json()
    assert added["id"]
    yes = client.post(
        "/memory/search",
        json={
            "namespace": "projects/alpha",
            "agent_id": "minis",
            "query": "PostgreSQL",
        },
    ).json()
    no = client.post(
        "/memory/search",
        json={
            "namespace": "projects/alpha",
            "agent_id": "claude",
            "query": "PostgreSQL",
        },
    ).json()
    assert len(yes["results"]) == 1 and no["results"] == []


def test_wiki_crud_search_history_and_traversal(client):
    r = client.post(
        "/wiki/page",
        json={
            "namespace": "projects/alpha",
            "title": "architecture",
            "content": "# Decision\nUse PostgreSQL for memory.",
        },
    )
    assert r.status_code == 200
    assert (
        client.get(
            "/wiki/page",
            params={"namespace": "projects/alpha", "title": "architecture"},
        )
        .json()["content"]
        .startswith("# Decision")
    )
    assert (
        client.get(
            "/wiki/search", params={"namespace": "projects/alpha", "q": "PostgreSQL"}
        ).json()["results"][0]["title"]
        == "architecture"
    )
    assert client.get(
        "/wiki/history", params={"namespace": "projects/alpha", "title": "architecture"}
    ).json()["history"]
    assert (
        client.get(
            "/wiki/page", params={"namespace": "projects/alpha", "title": "../secret"}
        ).status_code
        == 400
    )


def test_files_roundtrip_and_traversal_is_rejected(client):
    r = client.post(
        "/files/upload?namespace=global",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 200
    assert (
        client.get(
            "/files/download", params={"namespace": "global", "file": "note.txt"}
        ).content
        == b"hello"
    )
    assert (
        client.get(
            "/files/download",
            params={"namespace": "global", "file": "../../etc/passwd"},
        ).status_code
        == 400
    )
