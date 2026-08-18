"""MemoryBackend protocol and shared resilience helpers.

Adapters implement the MemoryBackend protocol. External HTTP adapters perform
their I/O via httpx with bounded timeouts/retries; never block the FastAPI event
loop with unbounded calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Iterable, Protocol, runtime_checkable

from ..memory_models import (
    BackendHealth,
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)

logger = logging.getLogger("dhub.memory")


@runtime_checkable
class MemoryBackend(Protocol):
    """Interface every memory backend must satisfy."""

    def health(self) -> BackendHealth: ...

    def add(
        self, record: MemoryRecord, *, infer: bool = True
    ) -> MemoryResult: ...

    def search(self, query: MemoryQuery) -> list[MemoryRecord]: ...

    def get(self, memory_id: str, scope: MemoryScope) -> MemoryRecord | None: ...

    def update(
        self, memory_id: str, patch: MemoryPatch, scope: MemoryScope
    ) -> MemoryResult: ...

    def delete(self, memory_id: str, scope: MemoryScope) -> MemoryResult: ...

    def export(self, scope: MemoryScope) -> Iterable[MemoryRecord]: ...


def dedupe_key(record: MemoryRecord) -> str:
    """Stable idempotency key derived from content + namespace scope."""
    seed = json.dumps(
        {
            "content": record.content,
            "namespace": record.namespace,
            "agent_id": record.agent_id,
            "session_id": record.session_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def scope_identity(scope: MemoryScope) -> str:
    """A stable string identity for a memory scope partition."""
    if scope.namespace in ("global", "global/shared"):
        return "global:shared"
    tier, ident = scope.namespace.strip("/").split("/", 1)
    if tier == "agents":
        return f"global:{ident}"
    if tier == "projects":
        return f"global:project:{ident}"
    return scope.namespace


def monotonic_ms() -> float:
    return round(time.monotonic() * 1000, 2)
