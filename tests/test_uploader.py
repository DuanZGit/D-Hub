from dhub.uploader import (
    JsonlSource,
    MinisSource,
    Uploader,
    content_to_text,
    extract_role_content,
    parse_jsonl_line,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.next_session_id = 0

    def json(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/sessions":
            self.next_session_id += 1
            return {"session_id": f"sid-{self.next_session_id}"}
        return {"status": "ok"}


def test_extract_role_content_from_claude_code():
    event = {
        "type": "user",
        "message": {"role": "user", "content": "hello world"},
        "timestamp": "2026-08-13T00:00:00Z",
    }
    role, content = extract_role_content(event)
    assert role == "user"
    assert content == "hello world"


def test_extract_role_content_from_codex():
    event = {
        "type": "event_msg",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "here is the code"}],
        },
    }
    role, content = extract_role_content(event)
    assert role == "assistant"
    assert content_to_text(content) == "here is the code"


def test_parse_jsonl_line_skips_non_messages():
    assert parse_jsonl_line('{"type":"session_meta","id":"abc"}') is None
    assert parse_jsonl_line("not json") is None


def test_jsonl_source_scans_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"one"}}\n'
        '{"type":"assistant","message":{"role":"assistant","content":"two"}}\n',
        encoding="utf-8",
    )
    items = JsonlSource(tmp_path, "claude").scan()
    assert len(items) == 1
    assert items[0]["kind"] == "session"
    assert [e["content"] for e in items[0]["events"]] == ["one", "two"]
    assert items[0]["meta"]["source"] == "claude"


def test_uploader_incremental_append(tmp_path):
    client = FakeClient()
    state_path = tmp_path / "state.json"
    uploader = Uploader(client, state_path, "agents/test")

    item = {
        "kind": "session",
        "key": "claude:abc",
        "events": [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
        ],
        "meta": {"source": "claude", "filename": "s.jsonl"},
    }

    # first run uploads everything
    result = uploader.run([item])
    assert result["sessions"] == 1
    assert result["messages"] == 2
    assert len(client.calls) == 2  # create + append

    # second run with 1 new event uploads only the new one
    item["events"].append({"role": "user", "content": "three"})
    client.calls.clear()
    result = uploader.run([item])
    assert result["messages"] == 1
    assert result["sessions"] == 0
    assert len(client.calls) == 1  # only append, no create
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1].endswith("/messages")
    assert len(client.calls[0][2]["messages"]) == 1
    assert client.calls[0][2]["messages"][0]["content"] == "three"


def test_uploader_memory_hash_dedup(tmp_path):
    client = FakeClient()
    uploader = Uploader(client, tmp_path / "state.json", "agents/test")

    memory = {
        "kind": "memory",
        "key": "minis:today",
        "content": "## note\nsome fact",
        "meta": {"source": "minis"},
    }

    uploader.run([memory])
    assert client.calls[-1][1] == "/memory/add"

    client.calls.clear()
    uploader.run([memory])  # unchanged -> no upload
    assert client.calls == []

    memory["content"] = "## note\nchanged"
    client.calls.clear()
    uploader.run([memory])  # changed -> re-upload
    assert client.calls[-1][1] == "/memory/add"


def test_minis_source_separates_global_and_logs(tmp_path):
    (tmp_path / "2026-08-13.md").write_text("## log\nhello", encoding="utf-8")
    (tmp_path / "GLOBAL.md").write_text("# Global\nprefs", encoding="utf-8")
    items = MinisSource(tmp_path).scan()
    kinds = {item["kind"] for item in items}
    assert kinds == {"memory", "wiki"}
    memory = next(i for i in items if i["kind"] == "memory")
    wiki = next(i for i in items if i["kind"] == "wiki")
    assert memory["meta"]["file"] == "2026-08-13.md"
    assert wiki["title"] == "minis-global-config"


def test_state_persists_across_restart(tmp_path):
    state_path = tmp_path / "state.json"
    item = {
        "kind": "session",
        "key": "codex:xyz",
        "events": [{"role": "user", "content": "a"}],
        "meta": {"source": "codex", "filename": "r.jsonl"},
    }
    first = Uploader(FakeClient(), state_path, "agents/test")
    first.run([item])

    # fresh uploader instance reading the same state file
    client2 = FakeClient()
    second = Uploader(client2, state_path, "agents/test")
    result = second.run([item])
    assert result["messages"] == 0  # nothing new to upload
    assert client2.calls == []
