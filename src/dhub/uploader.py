"""Single-direction auto-uploader: local agent assets -> cloud D-Hub.

Direction is strictly ONE-WAY (push only). Download is intentionally left to
the agent itself, which pulls memories/sessions on demand via the native MCP
tools (dhub_session_get, dhub_memory_search, ...).

Supported sources (--source):
  claude   ~/.claude/projects/<encoded>/<session>.jsonl  (transcripts)
  codex    ~/.codex/sessions/<hash>/rollout-*.jsonl      (transcripts)
  minis    /var/minis/memory/*.md                        (memory log)
  generic  any directory of *.jsonl / *.md (--dir)

Run modes:
  --once      scan once and exit (cron friendly)
  --watch     poll continuously (default, --interval seconds)

Incremental strategy:
  * session transcripts append only new lines past the recorded offset.
  * memories re-upload only when their content hash changes.
  A local state file maps source keys -> remote session ids / hashes so that a
  restart resumes without duplicates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from .agent_sync import HubClient

DEFAULT_STATE = Path(
    os.getenv("DHUB_UPLOADER_STATE", str(Path.home() / ".dhub-uploader-state.json"))
)


def content_to_text(content) -> str:
    """Normalize message content (str or multimodal list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def extract_role_content(obj):
    """Best-effort extraction of role + content from a nested event object.

    Claude Code and Codex wrap messages differently, so we walk the tree and
    take the first `role` and `content` fields we find.
    """
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


def parse_jsonl_line(line: str):
    """Parse one JSONL line into a normalized message event or None."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    role, content = extract_role_content(obj)
    if not content:
        return None
    text = content_to_text(content)
    if not text.strip():
        return None
    if role not in ("user", "assistant", "tool", "system"):
        role = "assistant"
    event = {"role": role, "content": text}
    # keep useful top-level metadata if present
    if isinstance(obj, dict):
        for key in ("timestamp", "created_at", "session_id", "cwd"):
            if isinstance(obj.get(key), (str, int, float)):
                event["metadata"] = {**event.get("metadata", {}), key: obj[key]}
    return event


def session_key(source: str, path: Path) -> str:
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:16]
    return f"{source}:{digest}"


class Source:
    """Base class for asset sources. scan() yields normalized items."""

    name = "generic"

    def scan(self) -> list[dict]:
        raise NotImplementedError


class JsonlSource(Source):
    """Scan a directory (recursive) of JSONL transcript files."""

    def __init__(self, root: Path, source_name: str):
        self.root = root
        self.name = source_name

    def scan(self):
        items = []
        if not self.root.is_dir():
            return items
        for path in sorted(self.root.rglob("*.jsonl")):
            events = []
            try:
                with path.open(encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        event = parse_jsonl_line(line)
                        if event:
                            events.append(event)
            except OSError:
                continue
            if not events:
                continue
            items.append(
                {
                    "kind": "session",
                    "key": session_key(self.name, path),
                    "events": events,
                    "meta": {
                        "source": self.name,
                        "path": str(path),
                        "filename": path.name,
                        "agent_id": os.getenv("DHUB_AGENT_ID", ""),
                    },
                }
            )
        return items


class MinisSource(Source):
    """Upload Minis daily memory logs (*.md) as memories, GLOBAL.md as a wiki page."""

    name = "minis"

    def __init__(self, root: Path):
        self.root = root

    def scan(self):
        items = []
        if not self.root.is_dir():
            return items
        for path in sorted(self.root.glob("*.md")):
            if path.name == "SOUL.md":
                continue  # personality file, not a memory log
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not content.strip():
                continue
            if path.name == "GLOBAL.md":
                items.append(
                    {
                        "kind": "wiki",
                        "key": "minis:global",
                        "title": "minis-global-config",
                        "content": content,
                        "meta": {"source": "minis"},
                    }
                )
            else:
                items.append(
                    {
                        "kind": "memory",
                        "key": f"minis:{path.stem}",
                        "content": content,
                        "meta": {"source": "minis", "file": path.name},
                    }
                )
        return items


class GenericSource(Source):
    """Scan an arbitrary directory of *.jsonl (sessions) and *.md (memories)."""

    name = "generic"

    def __init__(self, root: Path):
        self.root = root

    def scan(self):
        jsonl = JsonlSource(self.root, "generic").scan()
        minis = MinisSource(self.root).scan()
        return jsonl + minis


class SyncState:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"sessions": {}, "memories": {}, "wiki": {}}

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


class Uploader:
    def __init__(self, client: HubClient, state_path: Path, namespace: str):
        self.client = client
        self.namespace = namespace
        self.state = SyncState(state_path)
        self.data = self.state.load()

    def run(self, items):
        uploaded = {"sessions": 0, "messages": 0, "memories": 0, "wiki": 0}
        for item in items:
            kind = item["kind"]
            if kind == "session":
                self._sync_session(item, uploaded)
            elif kind == "memory":
                self._sync_memory(item, uploaded)
            elif kind == "wiki":
                self._sync_wiki(item, uploaded)
        self.state.save(self.data)
        return uploaded

    def _ensure_session(self, key, meta):
        session = self.data["sessions"].get(key)
        if session:
            return session
        payload = {
            "namespace": self.namespace,
            "title": meta.get("filename") or meta.get("path") or key,
            "cwd": meta.get("path", ""),
            "agent_id": meta.get("agent_id") or "",
            "metadata": meta,
        }
        result = self.client.json("POST", "/sessions", payload)
        session = {"session_id": result.get("session_id"), "offset": 0}
        self.data["sessions"][key] = session
        return session

    def _sync_session(self, item, uploaded):
        key = item["key"]
        session = self._ensure_session(key, item["meta"])
        events = item["events"]
        offset = session.get("offset", 0)
        new_events = events[offset:]
        if not new_events:
            return
        self.client.json(
            "POST",
            f"/sessions/{session['session_id']}/messages",
            {"namespace": self.namespace, "messages": new_events},
        )
        session["offset"] = len(events)
        if offset == 0:
            uploaded["sessions"] += 1
        uploaded["messages"] += len(new_events)

    def _sync_memory(self, item, uploaded):
        key = item["key"]
        digest = hashlib.sha256(item["content"].encode()).hexdigest()
        if self.data["memories"].get(key) == digest:
            return
        self.client.json(
            "POST",
            "/memory/add",
            {
                "namespace": self.namespace,
                "agent_id": item["meta"].get("agent_id") or "shared",
                "content": item["content"],
                "metadata": item["meta"],
                "infer": False,
            },
        )
        self.data["memories"][key] = digest
        uploaded["memories"] += 1

    def _sync_wiki(self, item, uploaded):
        key = item["key"]
        digest = hashlib.sha256(item["content"].encode()).hexdigest()
        if self.data["wiki"].get(key) == digest:
            return
        self.client.json(
            "POST",
            "/wiki/page",
            {
                "namespace": self.namespace,
                "title": item["title"],
                "content": item["content"],
                "author": f"uploader:{item['meta'].get('source', 'generic')}",
            },
        )
        self.data["wiki"][key] = digest
        uploaded["wiki"] += 1


def build_source(args) -> Source:
    home = Path.home()
    if args.source == "claude":
        return JsonlSource(home / ".claude" / "projects", "claude")
    if args.source == "codex":
        return JsonlSource(home / ".codex" / "sessions", "codex")
    if args.source == "minis":
        return MinisSource(Path("/var/minis/memory"))
    if args.source == "generic":
        if not args.dir:
            raise SystemExit("--source generic requires --dir")
        return GenericSource(Path(args.dir))
    raise SystemExit(f"unknown source: {args.source}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="One-way auto-uploader: local agent assets -> cloud D-Hub."
    )
    parser.add_argument(
        "--source",
        default=os.getenv("DHUB_SOURCE", "minis"),
        choices=["claude", "codex", "minis", "generic"],
    )
    parser.add_argument("--dir", help="directory to scan for --source generic")
    parser.add_argument(
        "--url", default=os.getenv("DHUB_URL", "http://127.0.0.1:10101")
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("DHUB_ADMIN_KEY") or os.getenv("DHUB_API_KEY"),
    )
    parser.add_argument("--namespace", default=os.getenv("DHUB_NAMESPACE", "global"))
    parser.add_argument("--agent-id", default=os.getenv("DHUB_AGENT_ID", ""))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument(
        "--mode", default="watch", choices=["once", "watch"]
    )
    parser.add_argument("--interval", type=int, default=int(os.getenv("DHUB_UPLOADER_INTERVAL", "60")))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = HubClient(args.url, args.api_key)
    source = build_source(args)
    uploader = Uploader(client, Path(args.state), args.namespace)
    os.environ.setdefault("DHUB_AGENT_ID", args.agent_id)
    try:
        while True:
            items = source.scan()
            try:
                result = uploader.run(items)
            except RuntimeError as exc:
                print(f"dhub-uploader: upload failed: {exc}", file=sys.stderr)
                if args.mode == "once":
                    return 1
                time.sleep(args.interval)
                continue
            print(
                json.dumps({"status": "ok", **result}, ensure_ascii=False)
            )
            if args.mode == "once":
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
