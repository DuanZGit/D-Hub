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


def test_session_lifecycle_roundtrip(client):
    created = client.post(
        "/sessions",
        json={"namespace": "global", "title": "demo", "cwd": "/repo"},
    )
    assert created.status_code == 200
    sid = created.json()["session_id"]

    client.post(
        f"/sessions/{sid}/messages",
        json={
            "namespace": "global",
            "messages": [
                {"role": "user", "content": "write a function"},
                {"role": "assistant", "content": "here you go"},
            ],
        },
    )

    got = client.get(f"/sessions/{sid}", params={"namespace": "global"})
    assert got.status_code == 200
    body = got.json()
    assert body["message_count"] == 2
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]

    listed = client.get("/sessions", params={"namespace": "global"})
    assert listed.json()["sessions"][0]["title"] == "demo"

    found = client.get(
        "/sessions/search", params={"namespace": "global", "q": "function"}
    )
    assert found.json()["results"][0]["content"] == "write a function"


def test_session_missing_returns_404(client):
    got = client.get("/sessions/nope", params={"namespace": "global"})
    assert got.status_code == 404


def test_session_delete(client):
    sid = client.post("/sessions", json={"namespace": "global"}).json()["session_id"]
    assert client.delete(f"/sessions/{sid}", params={"namespace": "global"}).status_code == 200
    assert client.delete(f"/sessions/{sid}", params={"namespace": "global"}).status_code == 404
