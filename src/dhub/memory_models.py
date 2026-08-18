"""Internal canonical memory model used across all MemoryBackend implementations.

External backend fields must be converted inside the adapter; the public d-hub
API and MemoryService only ever deal with these canonical models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryType = Literal[
    "fact",
    "preference",
    "decision",
    "episode",
    "skill",
    "task",
    "note",
]
MemorySource = Literal[
    "user",
    "agent",
    "session",
    "wiki",
    "imported",
    "system",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryRecord(BaseModel):
    """Canonical, backend-agnostic memory record."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    content: str
    namespace: str = "global"
    agent_id: str = "shared"
    project_id: str | None = None
    session_id: str | None = None
    memory_type: MemoryType = "note"
    source: MemorySource = "agent"
    provenance: str | None = None
    confidence: float | None = None
    importance: float | None = None
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    valid_from: str | None = None
    valid_until: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    def to_public(self) -> dict[str, Any]:
        """Serialise to a JSON-safe public mapping (no internal-only fields)."""
        data = self.model_dump(exclude_none=True)
        return data


class MemoryQuery(BaseModel):
    query: str = ""
    namespace: str = "global"
    agent_id: str = "shared"
    project_id: str | None = None
    session_id: str | None = None
    memory_types: list[MemoryType] = Field(default_factory=list)
    sources: list[MemorySource] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=500)
    score_threshold: float | None = None
    created_after: str | None = None
    created_before: str | None = None
    metadata_filters: dict[str, Any] = Field(default_factory=dict)


class MemoryScope(BaseModel):
    """Which partition of memory a get/update/delete/export targets."""

    namespace: str = "global"
    agent_id: str = "shared"
    project_id: str | None = None
    session_id: str | None = None


class MemoryPatch(BaseModel):
    content: str | None = None
    memory_type: MemoryType | None = None
    source: MemorySource | None = None
    confidence: float | None = None
    importance: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MemoryResult(BaseModel):
    status: Literal["ok", "error", "degraded"] = "ok"
    id: str | None = None
    backend: str = "unknown"
    error: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    dedupe_key: str | None = None
    external_id: str | None = None
    created: bool | None = None


class BackendHealth(BaseModel):
    backend: str
    ok: bool
    detail: str | None = None
    latency_ms: float | None = None
