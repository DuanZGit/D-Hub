import json

import pytest

from dhub.agent_sync import AgentAssetSync


class FakeClient:
    def __init__(self):
        self.requests = []

    def json(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        return {"status": "ok"}

    def upload(self, path, field_name, file_name, data, content_type):
        self.requests.append(
            ("UPLOAD", path, field_name, file_name, data, content_type)
        )
        return {"status": "ok"}


def write_manifest(tmp_path, manifest):
    path = tmp_path / "dhub-agent.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_registers_and_synchronizes_all_asset_types(tmp_path):
    (tmp_path / "skill.md").write_text("Use {literal} braces", encoding="utf-8")
    (tmp_path / "wiki.md").write_text("# Context", encoding="utf-8")
    (tmp_path / "file.txt").write_text("shared", encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "projects": ["alpha"],
            "assets": {
                "mcp": [
                    {
                        "namespace": "agents/{agent_id}",
                        "server_id": "tools",
                        "config": {"url": "http://agent/mcp", "options": {}},
                    }
                ],
                "skills": [
                    {
                        "namespace": "agents/{agent_id}",
                        "name": "workflow",
                        "path": "skill.md",
                    }
                ],
                "prompts": [
                    {
                        "namespace": "projects/{project}",
                        "target": "wiki",
                        "title": "context",
                        "path": "wiki.md",
                    }
                ],
                "files": [
                    {
                        "namespace": "projects/{project}",
                        "path": "file.txt",
                    }
                ],
            },
        },
    )
    client = FakeClient()

    result = AgentAssetSync(manifest, client).run()

    assert result["status"] == "ok"
    assert result["warning"] == "remote writes are ordered but not transactional"
    assert result["actions"] == [
        "register",
        "mcp:agents/codex/tools",
        "skill:agents/codex/workflow",
        "wiki:projects/alpha/context",
        "file:projects/alpha/file.txt",
    ]
    skill_payload = next(row[2] for row in client.requests if row[1] == "/skills")
    assert skill_payload["content"] == "Use {literal} braces"
    assert client.requests[-1][1] == "/files/upload?namespace=projects%2Falpha"


def test_dry_run_validates_files_without_sending_requests(tmp_path):
    (tmp_path / "skill.md").write_text("workflow", encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "assets": {
                "skills": [
                    {
                        "namespace": "agents/{agent_id}",
                        "name": "workflow",
                        "path": "skill.md",
                    }
                ]
            },
        },
    )
    client = FakeClient()

    result = AgentAssetSync(manifest, client, dry_run=True).run()

    assert result == {
        "status": "dry-run",
        "actions": ["register", "skill:agents/codex/workflow"],
    }
    assert client.requests == []


def test_live_sync_validates_every_asset_before_registration(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "assets": {
                "skills": [
                    {
                        "namespace": "agents/codex",
                        "name": "missing",
                        "path": "missing.md",
                    }
                ]
            },
        },
    )
    client = FakeClient()

    with pytest.raises(ValueError, match="not found"):
        AgentAssetSync(manifest, client).run()

    assert client.requests == []


def test_manifest_cannot_read_assets_outside_its_directory(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "assets": {
                "skills": [
                    {
                        "namespace": "agents/codex",
                        "name": "secret",
                        "path": "../secret.txt",
                    }
                ]
            },
        },
    )

    with pytest.raises(ValueError, match="stay inside"):
        AgentAssetSync(manifest, FakeClient(), dry_run=True).run()


def test_dry_run_rejects_invalid_namespace_before_sending_requests(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "assets": {
                "mcp": [
                    {
                        "namespace": "projects/../secret",
                        "server_id": "tools",
                        "config": {"url": "http://agent/mcp"},
                    }
                ]
            },
        },
    )
    client = FakeClient()

    with pytest.raises(ValueError, match="namespace must be"):
        AgentAssetSync(manifest, client, dry_run=True).run()

    assert client.requests == []


def test_manifest_cannot_publish_into_another_agents_namespace(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "agent_id": "codex",
            "assets": {
                "mcp": [
                    {
                        "namespace": "agents/other",
                        "server_id": "tools",
                        "config": {"url": "http://agent/mcp"},
                    }
                ]
            },
        },
    )

    with pytest.raises(ValueError, match="must match"):
        AgentAssetSync(manifest, FakeClient(), dry_run=True).run()
