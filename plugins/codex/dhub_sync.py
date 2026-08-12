#!/usr/bin/env python3
"""Codex SessionEnd hook — one-way sync of the session transcript to D-Hub.

Runs as a Codex `SessionEnd` hook (async, in the background). Reads the
transcript path passed on stdin, parses the JSONL event stream, and uploads
only the new messages to a cloud D-Hub via its REST API.

Zero dependencies: Python standard library only.

Environment variables:
  DHUB_URL        D-Hub base URL            (default http://127.0.0.1:10101)
  DHUB_API_KEY    admin or agent API key    (sent as Authorization: Bearer)
  DHUB_NAMESPACE  target namespace          (default global)
  DHUB_AGENT_ID   agent id for the session  (default codex)
  DHUB_SYNC_STATE state file path           (default ~/.codex/.dhub-sync.json)

Incremental: the state file records, per transcript path, the remote session
id and the number of already-uploaded lines. Re-runs resume without duplicates.
"""

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DHUB_URL = os.getenv("DHUB_URL", "http://127.0.0.1:10101").rstrip("/")
DHUB_API_KEY = os.getenv("DHUB_API_KEY") or os.getenv("DHUB_ADMIN_KEY")
DHUB_NAMESPACE = os.getenv("DHUB_NAMESPACE", "global")
DHUB_AGENT_ID = os.getenv("DHUB_AGENT_ID", "codex")
STATE_PATH = Path(
    os.getenv("DHUB_SYNC_STATE", str(Path.home() / ".codex" / ".dhub-sync.json"))
)

ROLES = {"user", "assistant", "tool", "system"}


def http(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if DHUB_API_KEY:
        headers["Authorization"] = "Bearer " + DHUB_API_KEY
    request = Request(DHUB_URL + path, data=body, headers=headers, method=method)
    with urlopen(request, timeout=60) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"transcripts": {}}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize(text):
    """Remove/replace lone Unicode surrogates so json.dumps never emits \\udXXX
    escapes that the Python-side D-Hub cannot UTF-8 encode."""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def content_to_text(content):
    """Normalize string or multimodal content blocks to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("output_text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def extract_role_content(obj):
    """Recursively find the first role + content in a nested Codex event."""
    role = None
    content = None

    def walk(node):
        nonlocal role, content
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "role" and role is None and isinstance(value, str):
                    role = value
                elif key == "content" and content is None:
                    content = value
                if role is not None and content is not None:
                    return
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
                if role is not None and content is not None:
                    return

    walk(obj)
    return role, content


def parse_events(lines):
    """Yield normalized {role, content, timestamp} events from Codex JSONL."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        role, content = extract_role_content(obj)
        text = sanitize(content_to_text(content))
        if not text.strip():
            continue
        if role not in ROLES:
            role = "assistant"
        yield {"role": role, "content": text}


def read_transcript(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except ValueError:
        hook_input = {}

    transcript = hook_input.get("transcript_path")
    if not transcript:
        # Fall back to a recent session dir if the field is missing.
        sessions = Path.home() / ".codex" / "sessions"
        candidates = sorted(sessions.glob("*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        transcript = str(candidates[0]) if candidates else None
    if not transcript:
        print("dhub-sync: no transcript found", file=sys.stderr)
        return 0

    lines = read_transcript(transcript)
    if not lines:
        return 0

    state = load_state()
    record = state.get("transcripts", {}).get(transcript)

    # Resolve or create the remote session.
    if record and record.get("session_id"):
        session_id = record["session_id"]
    else:
        title = Path(transcript).name
        cwd = hook_input.get("cwd", "")
        created = http(
            "POST",
            "/sessions",
            {
                "namespace": DHUB_NAMESPACE,
                "title": title,
                "cwd": cwd,
                "agent_id": DHUB_AGENT_ID,
                "metadata": {"source": "codex", "path": transcript},
            },
        )
        session_id = created.get("session_id")
        if not session_id:
            print("dhub-sync: failed to create session", file=sys.stderr)
            return 1
        record = {"session_id": session_id, "offset": 0}
        state.setdefault("transcripts", {})[transcript] = record
        # 立即持久化 session 映射：即使后续 messages 上传失败，
        # 重跑时也能复用同一个远程 session，避免重复创建。
        save_state(state)

    offset = record.get("offset", 0)
    events = list(parse_events(lines[offset:]))
    if not events:
        save_state(state)
        return 0

    http(
        "POST",
        f"/sessions/{session_id}/messages",
        {"namespace": DHUB_NAMESPACE, "messages": events},
    )
    record["offset"] = len(lines)
    save_state(state)
    print(f"dhub-sync: uploaded {len(events)} messages from {transcript}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, OSError) as exc:
        print(f"dhub-sync: {exc}", file=sys.stderr)
        raise SystemExit(1)
