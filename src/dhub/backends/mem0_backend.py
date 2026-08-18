"""Mem0 backend wrapping the mem0ai library.

Preserves the existing Mem0 + pgvector behaviour used by d-hub. The route layer
never talks to mem0 directly; it goes through MemoryService -> Mem0Backend.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Iterable

from ..config import ROOT, mutation_lock
from ..memory_models import (
    BackendHealth,
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)
from .base import scope_identity


class Mem0Backend:
    name = "mem0"

    def __init__(self):
        self.lock = threading.RLock()
        self.memory = None
        self.error = None
        self._init_mem0()

    def _init_mem0(self):
        needed = (
            "NEW_API_KEY",
            "DHUB_LLM_MODEL",
            "DHUB_EMBED_MODEL",
            "MEM0_DB_PASSWORD",
        )
        missing = [x for x in needed if not os.getenv(x)]
        if missing:
            self.error = "missing " + ", ".join(missing)
            return
        try:
            from mem0 import Memory

            dims = int(os.getenv("DHUB_EMBED_DIMS", "1536"))
            base = os.getenv("NEW_API_BASE_URL", "http://127.0.0.1:3000/v1")
            key = os.environ["NEW_API_KEY"]
            config = {
                "vector_store": {
                    "provider": "pgvector",
                    "config": {
                        "dbname": os.getenv("MEM0_DB_NAME", "mem0"),
                        "collection_name": "mem0",
                        "embedding_model_dims": dims,
                        "user": os.getenv("MEM0_DB_USER", "mem0"),
                        "password": os.environ["MEM0_DB_PASSWORD"],
                        "host": os.getenv("MEM0_DB_HOST", "127.0.0.1"),
                        "port": int(os.getenv("MEM0_DB_PORT", "5432")),
                        "hnsw": True,
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": os.environ["DHUB_LLM_MODEL"],
                        "temperature": 0.1,
                        "api_key": key,
                        "openai_base_url": base,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": os.environ["DHUB_EMBED_MODEL"],
                        "embedding_dims": dims,
                        "api_key": key,
                        "openai_base_url": base,
                    },
                },
                "history_db_path": str(ROOT / "data" / "mem0-history.db"),
            }
            self.memory = Memory.from_config(config)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.error = str(exc)

    def health(self) -> BackendHealth:
        ok = self.memory is not None
        return BackendHealth(
            backend=self.name,
            ok=ok,
            detail=None if ok else (self.error or "mem0 not initialised"),
        )

    def _uid(self, scope: MemoryScope) -> str:
        return scope_identity(scope)

    def add(
        self, record: MemoryRecord, *, infer: bool = True
    ) -> MemoryResult:
        uid = self._uid(
            MemoryScope(namespace=record.namespace, agent_id=record.agent_id)
        )
        if not self.memory:
            return MemoryResult(
                status="error", backend=self.name,
                error=self.error or "mem0 backend unavailable"
            )
        metadata = dict(record.metadata or {})
        metadata.setdefault("namespace", record.namespace)
        metadata.setdefault("agent_id", record.agent_id)
        metadata.setdefault("memory_type", record.memory_type)
        metadata.setdefault("source", record.source)
        metadata.setdefault("provenance", record.provenance)
        with mutation_lock("memory"):
            out = self.memory.add(
                record.content, user_id=uid, metadata=metadata, infer=infer
            )
        rows = out.get("results", [])
        rid = rows[0].get("id") if rows else None
        return MemoryResult(
            status="ok",
            id=rid,
            backend=self.name,
            created=True,
            external_id=rid,
            results=rows,
        )

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        if not self.memory:
            return []
        uid = self._uid(
            MemoryScope(namespace=query.namespace, agent_id=query.agent_id)
        )
        result = self.memory.search(
            query.query, top_k=query.limit, filters={"user_id": uid}
        )
        records = []
        for row in (result.get("results", []) if isinstance(result, dict) else result):
            records.append(self._record_from_mem0(row))
        return records

    def get(self, memory_id: str, scope: MemoryScope) -> MemoryRecord | None:
        if not self.memory:
            return None
        uid = self._uid(scope)
        result = self.memory.get_all(filters={"user_id": uid})
        rows = result.get("results", []) if isinstance(result, dict) else result
        for row in rows:
            if str(row.get("id")) == str(memory_id):
                return self._record_from_mem0(row)
        return None

    def update(
        self, memory_id: str, patch: MemoryPatch, scope: MemoryScope
    ) -> MemoryResult:
        if not self.memory:
            return MemoryResult(
                status="error", id=memory_id, backend=self.name,
                error=self.error or "mem0 backend unavailable"
            )
        try:
            with mutation_lock("memory"):
                self.memory.update(memory_id, data=patch.content)
            return MemoryResult(status="ok", id=memory_id, backend=self.name)
        except Exception as exc:  # mem0 raises varied exceptions
            return MemoryResult(
                status="error", id=memory_id, backend=self.name, error=str(exc)
            )

    def delete(self, memory_id: str, scope: MemoryScope) -> MemoryResult:
        if not self.memory:
            return MemoryResult(
                status="error", id=memory_id, backend=self.name,
                error=self.error or "mem0 backend unavailable"
            )
        with mutation_lock("memory"):
            self.memory.delete(memory_id)
        return MemoryResult(status="ok", id=memory_id, backend=self.name)

    def export(self, scope: MemoryScope) -> Iterable[MemoryRecord]:
        if not self.memory:
            return
        uid = self._uid(scope)
        result = self.memory.get_all(filters={"user_id": uid})
        rows = result.get("results", []) if isinstance(result, dict) else result
        for row in rows:
            yield self._record_from_mem0(row)

    def list(self, scope: MemoryScope, limit: int = 100) -> list[MemoryRecord]:
        if not self.memory:
            return []
        uid = self._uid(scope)
        result = self.memory.get_all(filters={"user_id": uid}, top_k=limit)
        rows = result.get("results", []) if isinstance(result, dict) else result
        return [self._record_from_mem0(row) for row in rows]

    @staticmethod
    def _record_from_mem0(row) -> MemoryRecord:
        metadata = row.get("metadata") or {}
        return MemoryRecord(
            id=str(row.get("id", "")),
            content=row.get("memory", row.get("content", "")),
            namespace=metadata.get("namespace", "global"),
            agent_id=metadata.get("agent_id", "shared"),
            memory_type=metadata.get("memory_type", "note"),
            source=metadata.get("source", "agent"),
            provenance=metadata.get("provenance"),
            metadata=metadata,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
