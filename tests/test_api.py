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


@pytest.fixture
def authenticated_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    monkeypatch.setenv("DHUB_API_KEY", "test-secret")
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


def test_root_redirects_to_dashboard(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_root_redirect_reaches_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "d-hub" in response.text


def test_api_key_protects_non_public_routes(authenticated_client):
    assert authenticated_client.get("/health").status_code == 200
    assert authenticated_client.get("/ui").status_code == 200
    unauthorized = authenticated_client.get("/agents")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    authorized = authenticated_client.get(
        "/agents", headers={"Authorization": "Bearer test-secret"}
    )
    assert authorized.status_code == 200


def test_streamable_http_mcp_initializes_and_lists_tools(client):
    for namespace, description in [
        ("global", "Global echo"),
        ("projects/alpha", "Project echo"),
    ]:
        client.put(
            "/mcp/configs",
            json={
                "namespace": namespace,
                "server_id": "local",
                "config": {
                    "name": "local",
                    "tools": [{"name": "echo", "description": description}],
                },
            },
        )
    initialized = client.post(
        "/mcp?agent_id=minis&project=alpha",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "d-hub"
    session_id = initialized.headers["mcp-session-id"]

    listed = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200
    assert listed.json()["result"]["tools"][0]["name"] == "rmcp__local__echo"
    assert listed.json()["result"]["tools"][0]["description"] == "Project echo"

    notification = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert notification.status_code == 202
    closed = client.delete("/mcp", headers={"Mcp-Session-Id": session_id})
    assert closed.status_code == 204
    after_close = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}},
    )
    assert after_close.status_code == 404
    assert after_close.json()["error"]["code"] == -32001


def test_disabled_mcp_server_cannot_be_called(client):
    client.put(
        "/mcp/configs",
        json={
            "namespace": "global",
            "server_id": "disabled",
            "config": {"enabled": False, "tools": [{"name": "echo"}]},
        },
    )
    response = client.post(
        "/mcp/tools/call",
        json={"name": "rmcp__disabled__echo", "arguments": {}},
    )
    assert response.status_code == 404


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
        {
            "name": "rmcp__server__echo",
            "description": "project",
            "inputSchema": {"type": "object", "properties": {}},
            "server": "server",
        }
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
