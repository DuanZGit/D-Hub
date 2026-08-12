import json

import pytest

from dhub.native_mcp import NativeMcpTools


class FakeMemory:
    def search(self, namespace, agent_id, query, limit):
        return {
            "namespace": namespace,
            "agent_id": agent_id,
            "query": query,
            "limit": limit,
        }

    def add(self, namespace, agent_id, content, metadata, infer):
        return {"namespace": namespace, "agent_id": agent_id, "content": content}


class FakeWiki:
    def search(self, namespace, query, limit):
        return [{"namespace": namespace, "query": query, "limit": limit}]


class FakeSkills:
    def list(self, agent_id, project):
        return [{"agent_id": agent_id, "project": project}]


class FakeFiles:
    def list(self, namespace):
        return [{"namespace": namespace}]


def native():
    return NativeMcpTools(FakeMemory(), FakeWiki(), FakeSkills(), FakeFiles())


def structured(result):
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def test_native_tools_default_to_initialized_project_context():
    result = native().call(
        "dhub_memory_search", {"query": "decision"}, "codex", "alpha"
    )
    assert structured(result) == {
        "namespace": "projects/alpha",
        "agent_id": "shared",
        "query": "decision",
        "limit": 10,
    }


def test_native_tools_can_select_agent_and_global_scope():
    agent = structured(
        native().call("dhub_files_list", {"scope": "agent"}, "codex", "alpha")
    )
    shared = structured(
        native().call(
            "dhub_memory_add",
            {"scope": "global", "content": "fact"},
            allow_global=True,
        )
    )
    assert agent == {"files": [{"namespace": "agents/codex"}]}
    assert shared["namespace"] == "global"
    assert shared["agent_id"] == "shared"


def test_native_agent_session_cannot_write_global_scope():
    with pytest.raises(PermissionError, match="admin key"):
        native().call(
            "dhub_memory_add",
            {"scope": "global", "content": "fact"},
            "codex",
            "alpha",
        )


def test_project_memory_uses_shared_project_identity():
    result = structured(
        native().call("dhub_memory_search", {"query": "decision"}, "codex", "alpha")
    )
    assert result["namespace"] == "projects/alpha"
    assert result["agent_id"] == "shared"


def test_native_project_scope_requires_project_in_mcp_url():
    with pytest.raises(ValueError, match="requires project"):
        native().call("dhub_wiki_search", {"scope": "project"}, "codex", None)


def test_native_tool_declarations_have_object_schemas():
    tools = native().list_tools()
    assert {tool["name"] for tool in tools} >= {
        "dhub_memory_search",
        "dhub_memory_add",
        "dhub_wiki_search",
        "dhub_skill_get",
        "dhub_file_read",
    }
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)
