"""Durable JSON fallback backend (degraded / bootstrap operation).

Preserves the exact behaviour of the original d-hub JSON fallback so that
existing installations and tests keep working when no vector backend is
configured.
"""

from __future__ import annotations

import threading
import uuid
from typing import Iterable

from ..config import ROOT, atomic_json, mutation_lock, now, read_json
from ..memory_models import (
    BackendHealth,
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)
from .base import scope_identity


class JsonFallbackBackend:
    name = "json"

    def __init__(self, path=None):
        self.path = path or (ROOT / "data" / "memory-fallback.json")
        self.lock = threading.RLock()

    def _rows(self):
        return read_json(self.path, []) or []

    def _write(self, rows):
        atomic_json(self.path, rows)

    def health(self) -> BackendHealth:
        return BackendHealth(backend=self.name, ok=True, detail="json fallback")

    def add(
        self, record: MemoryRecord, *, infer: bool = True
    ) -> MemoryResult:
        uid = scope_identity(
            MemoryScope(namespace=record.namespace, agent_id=record.agent_id)
        )
        item = {
            "id": record.id or uuid.uuid4().hex,
            "memory": record.content,
            "content": record.content,
            "user_id": uid,
            "namespace": record.namespace,
            "agent_id": record.agent_id,
            "memory_type": record.memory_type,
            "source": record.source,
            "provenance": record.provenance,
            "metadata": record.metadata or {},
            "created_at": record.created_at or now(),
            "updated_at": record.updated_at or now(),
        }
        with self.lock, mutation_lock("memory"):
            rows = self._rows()
            rows.append(item)
            self._write(rows)
        return MemoryResult(
            status="ok",
            id=item["id"],
            backend=self.name,
            created=True,
            results=[item],
        )

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        uid = scope_identity(
            MemoryScope(namespace=query.namespace, agent_id=query.agent_id)
        )
        terms = [t for t in query.query.lower().split() if t]
        rows = self._rows()
        found = []
        for x in rows:
            if x.get("user_id") != uid:
                continue
            text = x.get("memory", x.get("content", "")).lower()
            score = sum(text.count(t) for t in terms)
            if not terms or score:
                found.append((x, float(score)))
        found.sort(key=lambda pair: (pair[1], pair[0].get("created_at", "")), reverse=True)
        results = []
        for x, score in found[: query.limit]:
            rec = self._record_from_row(x)
            rec.metadata = {**rec.metadata, "score": score}
            results.append(rec)
        return results

    def get(self, memory_id: str, scope: MemoryScope) -> MemoryRecord | None:
        uid = scope_identity(scope)
        for x in self._rows():
            if x.get("id") == memory_id and x.get("user_id") == uid:
                return self._record_from_row(x)
        return None

    def update(
        self, memory_id: str, patch: MemoryPatch, scope: MemoryScope
    ) -> MemoryResult:
        uid = scope_identity(scope)
        with self.lock, mutation_lock("memory"):
            rows = self._rows()
            for x in rows:
                if x.get("id") != memory_id or x.get("user_id") != uid:
                    continue
                if patch.content is not None:
                    x["memory"] = patch.content
                    x["content"] = patch.content
                if patch.memory_type is not None:
                    x["memory_type"] = patch.memory_type
                if patch.source is not None:
                    x["source"] = patch.source
                if patch.metadata is not None:
                    x["metadata"] = {**x.get("metadata", {}), **patch.metadata}
                x["updated_at"] = now()
                self._write(rows)
                return MemoryResult(
                    status="ok", id=memory_id, backend=self.name, results=[x]
                )
        return MemoryResult(status="error", id=memory_id, backend=self.name,
                            error="memory not found")

    def delete(self, memory_id: str, scope: MemoryScope) -> MemoryResult:
        uid = scope_identity(scope)
        with self.lock, mutation_lock("memory"):
            rows = self._rows()
            new = [
                x for x in rows
                if not (x.get("id") == memory_id and x.get("user_id") == uid)
            ]
            if len(new) == len(rows):
                return MemoryResult(
                    status="error", id=memory_id, backend=self.name,
                    error="memory not found"
                )
            self._write(new)
        return MemoryResult(status="ok", id=memory_id, backend=self.name)

    def export(self, scope: MemoryScope) -> Iterable[MemoryRecord]:
        uid = scope_identity(scope)
        for x in self._rows():
            if x.get("user_id") == uid:
                yield self._record_from_row(x)

    def list(self, scope: MemoryScope, limit: int = 100) -> list[MemoryRecord]:
        uid = scope_identity(scope)
        rows = [x for x in self._rows() if x.get("user_id") == uid]
        return [self._record_from_row(x) for x in rows[-limit:][::-1]]

    @staticmethod
    def _record_from_row(x: dict) -> MemoryRecord:
        return MemoryRecord(
            id=x.get("id"),
            content=x.get("memory", x.get("content", "")),
            namespace=x.get("namespace", "global"),
            agent_id=x.get("agent_id", "shared"),
            memory_type=x.get("memory_type", "note"),
            source=x.get("source", "agent"),
            provenance=x.get("provenance"),
            metadata=x.get("metadata", {}),
            created_at=x.get("created_at"),
            updated_at=x.get("updated_at"),
        )
