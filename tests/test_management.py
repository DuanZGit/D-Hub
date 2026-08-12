import importlib
import io
import os
import sys
import tarfile
import time
import threading
from pathlib import Path

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
    client.post(
        "/wiki/page",
        json={"namespace": "global", "title": "newer", "content": "remove me"},
    )
    restored = client.post(f"/backup/{backup_name}/restore")
    assert restored.status_code == 200
    assert (
        client.get(
            "/wiki/page", params={"namespace": "global", "title": "durable"}
        ).json()["content"]
        == "before"
    )
    assert (
        client.get(
            "/wiki/page", params={"namespace": "global", "title": "newer"}
        ).status_code
        == 404
    )


def test_restore_rejects_link_members(client, tmp_path):
    backup_dir = tmp_path / "backups" / "unsafe"
    backup_dir.mkdir(parents=True)
    with tarfile.open(backup_dir / "data.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("files/global/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        archive.addfile(member, io.BytesIO())
    response = client.post("/backup/unsafe/restore")
    assert response.status_code == 400
    assert response.json()["detail"] == "unsafe backup archive"


def test_replace_roots_rolls_back_after_post_replace_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    for name in list(sys.modules):
        if name == "dhub" or name.startswith("dhub."):
            del sys.modules[name]
    services = importlib.import_module("dhub.services")

    staging = tmp_path / "backups" / "work" / "staging"
    for name in ("config", "data"):
        current = tmp_path / name
        source = staging / name
        current.mkdir(parents=True)
        source.mkdir(parents=True)
        (current / "value.txt").write_text("before", encoding="utf-8")
        (source / "value.txt").write_text("after", encoding="utf-8")

    def fail_after_replace():
        raise RuntimeError("database restore failed")

    with pytest.raises(RuntimeError, match="database restore failed"):
        services._replace_roots(staging, {"config", "data"}, fail_after_replace)

    for name in ("config", "data"):
        assert (Path(tmp_path) / name / "value.txt").read_text() == "before"


def test_backup_retention_removes_only_expired_backups(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    monkeypatch.setenv("DHUB_BACKUP_RETENTION_DAYS", "7")
    for name in list(sys.modules):
        if name == "dhub" or name.startswith("dhub."):
            del sys.modules[name]
    services = importlib.import_module("dhub.services")

    backups = tmp_path / "backups"
    expired = backups / "expired"
    recent = backups / "recent"
    current = backups / "current"
    for path in (expired, recent, current):
        path.mkdir(parents=True)
    old = time.time() - 8 * 86400
    os.utime(expired, (old, old))

    services._prune_backups(current)

    assert not expired.exists()
    assert recent.exists()
    assert current.exists()


def test_asset_mutation_waits_for_backup_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_ROOT", str(tmp_path))
    monkeypatch.setenv("DHUB_MEMORY_BACKEND", "json")
    for name in list(sys.modules):
        if name == "dhub" or name.startswith("dhub."):
            del sys.modules[name]
    config = importlib.import_module("dhub.config")

    entered = threading.Event()
    finished = threading.Event()

    def mutate():
        entered.set()
        with config.mutation_lock("files"):
            finished.set()

    with config.file_lock("assets"):
        worker = threading.Thread(target=mutate)
        worker.start()
        assert entered.wait(1)
        assert not finished.wait(0.05)

    worker.join(1)
    assert finished.is_set()


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
