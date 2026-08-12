from __future__ import annotations

import json
import re
import uuid

from .config import ROOT, atomic_json, mutation_lock, namespace_parts, now, safe_part


class SessionStore:
    """Durable session transcripts (conversation event streams) per namespace.

    Layout (mirrors Claude Code / Codex CLI event-stream style):
        ROOT/sessions/<tier>/[ident]/<session_id>.json    -> metadata
        ROOT/sessions/<tier>/[ident]/<session_id>.jsonl   -> message events
    Namespaces follow the same three tiers as wiki/files:
        global, agents/<id>, projects/<id>.
    """

    def __init__(self):
        self.root = ROOT / "sessions"
        (self.root / "global").mkdir(parents=True, exist_ok=True)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _dir(namespace: str):
        tier, ident = namespace_parts(namespace)
        if tier == "global":
            return ROOT / "sessions" / "global"
        return ROOT / "sessions" / tier / ident

    @staticmethod
    def _meta_path(directory, session_id: str):
        return directory / f"{safe_part(session_id)}.json"

    @staticmethod
    def _events_path(directory, session_id: str):
        return directory / f"{safe_part(session_id)}.jsonl"

    def _read_meta(self, directory, session_id: str):
        path = self._meta_path(directory, session_id)
        if not path.is_file():
            raise FileNotFoundError(session_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_events(self, directory, session_id: str):
        path = self._events_path(directory, session_id)
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events

    # -- public API ------------------------------------------------------
    def create(
        self,
        namespace,
        title=None,
        cwd=None,
        agent_id=None,
        project=None,
        metadata=None,
    ):
        session_id = uuid.uuid4().hex
        directory = self._dir(namespace)
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "session_id": session_id,
            "namespace": namespace,
            "title": title or "",
            "cwd": cwd or "",
            "agent_id": agent_id or "",
            "project": project or "",
            "created_at": now(),
            "updated_at": now(),
            "message_count": 0,
            "metadata": metadata or {},
        }
        with mutation_lock("sessions"):
            atomic_json(self._meta_path(directory, session_id), record)
            self._events_path(directory, session_id).write_text("", encoding="utf-8")
        return record

    def list(self, namespace="global", limit=100):
        directory = self._dir(namespace)
        if not directory.is_dir():
            return []
        rows = []
        for path in sorted(directory.glob("*.json"), reverse=True):
            if path.name.startswith("."):
                continue
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return rows[:limit]

    def get(self, namespace, session_id, include_messages=True):
        directory = self._dir(namespace)
        record = self._read_meta(directory, session_id)
        if include_messages:
            record = dict(record)
            record["messages"] = self._read_events(directory, session_id)
        return record

    def append(self, namespace, session_id, messages, metadata=None):
        """Append one or more message events. Each message: {role, content, ...}."""
        directory = self._dir(namespace)
        record = self._read_meta(directory, session_id)
        if isinstance(messages, dict):
            messages = [messages]
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list of objects")
        stamp = now()
        lines = []
        for message in messages:
            if not isinstance(message, dict):
                raise TypeError("each message must be an object")
            role = message.get("role", "unknown")
            if role not in ("user", "assistant", "tool", "system"):
                role = "unknown"
            event = {
                "role": role,
                "content": str(message.get("content", "")),
                "timestamp": message.get("timestamp", stamp),
            }
            extra = message.get("metadata")
            if isinstance(extra, dict) and extra:
                event["metadata"] = extra
            lines.append(json.dumps(event, ensure_ascii=False))
        with mutation_lock("sessions"):
            events_path = self._events_path(directory, session_id)
            existing = events_path.read_text(encoding="utf-8", errors="replace")
            if existing and not existing.endswith("\n"):
                existing += "\n"
            events_path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
            record["message_count"] = record.get("message_count", 0) + len(messages)
            record["updated_at"] = stamp
            if metadata and isinstance(metadata, dict):
                record["metadata"] = {**record.get("metadata", {}), **metadata}
            atomic_json(self._meta_path(directory, session_id), record)
        return {"status": "ok", "appended": len(messages), "session_id": session_id}

    def update(self, namespace, session_id, **fields):
        directory = self._dir(namespace)
        record = self._read_meta(directory, session_id)
        allowed = {"title", "cwd", "agent_id", "project", "metadata"}
        with mutation_lock("sessions"):
            for key, value in fields.items():
                if key in allowed:
                    record[key] = value
            record["updated_at"] = now()
            atomic_json(self._meta_path(directory, session_id), record)
        return record

    def delete(self, namespace, session_id):
        directory = self._dir(namespace)
        meta = self._meta_path(directory, session_id)
        events = self._events_path(directory, session_id)
        with mutation_lock("sessions"):
            existed = meta.is_file()
            meta.unlink(missing_ok=True)
            events.unlink(missing_ok=True)
        return existed

    def search(self, namespace, query, limit=20):
        directory = self._dir(namespace)
        if not directory.is_dir():
            return []
        terms = [t.lower() for t in re.split(r"\s+", query or "") if t]
        results = []
        for meta_path in sorted(directory.glob("*.json"), reverse=True):
            if meta_path.name.startswith("."):
                continue
            session_id = meta_path.stem
            try:
                record = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            events = self._read_events(directory, session_id)
            for event in events:
                text = event.get("content", "").lower()
                if not terms or all(term in text for term in terms):
                    results.append(
                        {
                            "session_id": session_id,
                            "title": record.get("title", ""),
                            "role": event.get("role"),
                            "content": event.get("content", "")[:500],
                            "timestamp": event.get("timestamp"),
                        }
                    )
                    if len(results) >= limit:
                        return results
        return results
