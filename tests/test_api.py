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


@pytest.fixture
def agent_key_client(tmp_path, monkeypatch):
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


def test_registration_returns_agent_key_once_and_hides_hash(authenticated_client):
    headers = {"Authorization": "Bearer test-secret"}
    first = authenticated_client.post(
        "/register",
        headers=headers,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()
    second = authenticated_client.post(
        "/register",
        headers=headers,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()
    listed = authenticated_client.get("/agents", headers=headers).json()["agents"]
    assert first["api_key"]
    assert "api_key" not in second
    assert "api_key_hash" not in listed[0]


def test_agent_key_only_authorizes_bound_mcp_project(authenticated_client):
    admin = {"Authorization": "Bearer test-secret"}
    key = authenticated_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()["api_key"]
    agent = {"Authorization": f"Bearer {key}"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26"},
    }
    allowed = authenticated_client.post(
        "/mcp?agent_id=codex&project=alpha", headers=agent, json=payload
    )
    denied = authenticated_client.post(
        "/mcp?agent_id=codex&project=beta", headers=agent, json=payload
    )
    management = authenticated_client.get("/agents", headers=agent)
    assert allowed.status_code == 200
    assert denied.status_code == 401
    assert management.status_code == 401


def test_disabled_agent_key_cannot_initialize_mcp(agent_key_client):
    admin = {"Authorization": "Bearer admin-secret"}
    key = agent_key_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()["api_key"]
    agent_key_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"], "enabled": False},
    )
    denied = agent_key_client.post(
        "/mcp?agent_id=codex&project=alpha",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )
    assert denied.status_code == 401


def test_agent_mcp_key_cannot_access_global_native_scope(agent_key_client):
    admin = {"Authorization": "Bearer admin-secret"}
    key = agent_key_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()["api_key"]
    agent = {"Authorization": f"Bearer {key}"}
    initialized = agent_key_client.post(
        "/mcp?agent_id=codex&project=alpha",
        headers=agent,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )
    session = initialized.headers["mcp-session-id"]
    denied = agent_key_client.post(
        "/mcp",
        headers={**agent, "Mcp-Session-Id": session},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "dhub_memory_add",
                "arguments": {"scope": "global", "content": "forbidden"},
            },
        },
    )
    assert denied.status_code == 200
    assert denied.json()["error"]["code"] == -32003


def test_disabling_agent_revokes_existing_mcp_session(agent_key_client):
    admin = {"Authorization": "Bearer admin-secret"}
    key = agent_key_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"]},
    ).json()["api_key"]
    agent = {"Authorization": f"Bearer {key}"}
    initialized = agent_key_client.post(
        "/mcp?agent_id=codex&project=alpha",
        headers=agent,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )
    session = initialized.headers["mcp-session-id"]
    agent_key_client.post(
        "/register",
        headers=admin,
        json={"agent_id": "codex", "projects": ["alpha"], "enabled": False},
    )
    revoked = agent_key_client.post(
        "/mcp",
        headers={**agent, "Mcp-Session-Id": session},
        json={"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
    )
    assert revoked.status_code == 404


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
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
    assert "dhub_memory_search" in tools
    assert tools["rmcp__local__echo"]["description"] == "Project echo"

    native_call = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "dhub_files_list", "arguments": {}},
        },
    )
    assert native_call.status_code == 200
    assert native_call.json()["result"]["structuredContent"] == {"files": []}

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
        json={"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}},
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
    remote = next(tool for tool in tools if tool["name"] == "rmcp__server__echo")
    assert remote == {
        "name": "rmcp__server__echo",
        "description": "project",
        "inputSchema": {"type": "object", "properties": {}},
        "server": "server",
    }


def test_project_memory_is_shared_across_agents(client):
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
    also_yes = client.post(
        "/memory/search",
        json={
            "namespace": "projects/alpha",
            "agent_id": "claude",
            "query": "PostgreSQL",
        },
    ).json()
    assert len(yes["results"]) == 1 and len(also_yes["results"]) == 1


def test_agent_memory_namespaces_are_isolated(client):
    client.post(
        "/memory/add",
        json={
            "namespace": "agents/minis",
            "agent_id": "minis",
            "content": "private observation",
        },
    )
    yes = client.post(
        "/memory/search",
        json={
            "namespace": "agents/minis",
            "agent_id": "minis",
            "query": "private",
        },
    ).json()
    no = client.post(
        "/memory/search",
        json={
            "namespace": "agents/claude",
            "agent_id": "claude",
            "query": "private",
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


def test_memory_backends_and_health_endpoints(client):
    backends = client.get("/memory/backends")
    assert backends.status_code == 200
    assert "backends" in backends.json()
    health = client.get("/memory/health")
    assert health.status_code == 200
    assert "backend" in health.json()


def test_memory_get_update_export(client):
    added = client.post(
        "/memory/add",
        json={"namespace": "agents/codex", "agent_id": "codex",
              "content": "store this fact"},
    ).json()
    mid = added["id"]
    got = client.get(f"/memory/{mid}", params={"namespace": "agents/codex", "agent_id": "codex"})
    assert got.status_code == 200
    assert got.json()["content"] == "store this fact"
    patched = client.patch(
        f"/memory/{mid}",
        json={"namespace": "agents/codex", "agent_id": "codex",
              "content": "updated fact"},
    )
    assert patched.status_code == 200
    exported = client.post(
        "/memory/export",
        params={"namespace": "agents/codex", "agent_id": "codex"},
    )
    assert exported.status_code == 200
    assert len(exported.json()["records"]) == 1


def test_memory_delete_respects_namespace_scope(client):
    added = client.post(
        "/memory/add",
        json={
            "namespace": "agents/codex",
            "agent_id": "codex",
            "content": "delete this scoped fact",
        },
    ).json()
    memory_id = added["id"]

    wrong_scope = client.delete(
        f"/memory/{memory_id}",
        params={"namespace": "global", "agent_id": "shared"},
    )
    assert wrong_scope.status_code == 404
    assert client.get(
        f"/memory/{memory_id}",
        params={"namespace": "agents/codex", "agent_id": "codex"},
    ).status_code == 200

    deleted = client.delete(
        f"/memory/{memory_id}",
        params={"namespace": "agents/codex", "agent_id": "codex"},
    )
    assert deleted.status_code == 200
    assert client.get(
        f"/memory/{memory_id}",
        params={"namespace": "agents/codex", "agent_id": "codex"},
    ).status_code == 404
