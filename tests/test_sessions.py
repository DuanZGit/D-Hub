import json

import pytest

from dhub.native_mcp import NativeMcpTools


class FakeMemory:
    def search(self, namespace, agent_id, query, limit):
        return {"namespace": namespace, "query": query}


class FakeWiki:
    def search(self, namespace, query, limit):
        return []


class FakeSkills:
    def list(self, agent_id, project):
        return []


class FakeFiles:
    def list(self, namespace):
        return []


class FakeSessions:
    def __init__(self):
        self.created = []
        self.appended = []
        self.storage = {}

    def create(self, namespace, **kwargs):
        sid = "s1"
        self.created.append((namespace, kwargs))
        return {"session_id": sid, "namespace": namespace, **kwargs}

    def list(self, namespace, limit):
        return [{"session_id": "s1", "namespace": namespace}]

    def get(self, namespace, session_id):
        return {"session_id": session_id, "namespace": namespace, "messages": []}

    def append(self, namespace, session_id, messages, metadata):
        self.appended.append((namespace, session_id, messages))
        return {"appended": len(messages)}

    def search(self, namespace, query, limit):
        return [{"session_id": "s1", "content": query}]


def native():
    return NativeMcpTools(
        FakeMemory(), FakeWiki(), FakeSkills(), FakeFiles(), FakeSessions()
    )


def structured(result):
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def test_session_tools_are_declared():
    tools = {t["name"] for t in native().list_tools()}
    assert {
        "dhub_session_create",
        "dhub_session_list",
        "dhub_session_get",
        "dhub_session_append",
        "dhub_session_search",
    } <= tools


def test_session_create_routes_to_agent_namespace():
    result = structured(
        native().call(
            "dhub_session_create",
            {"title": "hello", "cwd": "/repo"},
            "codex",
            "alpha",
        )
    )
    assert result["namespace"] == "projects/alpha"
    assert result["title"] == "hello"


def test_session_append_requires_session_id():
    with pytest.raises(ValueError, match="session_id"):
        native().call("dhub_session_append", {"messages": []}, "codex", None)


def test_session_scope_global_needs_admin():
    with pytest.raises(PermissionError, match="admin key"):
        native().call(
            "dhub_session_create", {"scope": "global", "title": "x"}, "codex", None
        )
