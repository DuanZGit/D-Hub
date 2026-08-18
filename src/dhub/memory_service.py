"""MemoryService: orchestration layer above pluggable MemoryBackends.

Responsibilities:
- register and select backends by config (default stays mem0 / json path)
- expose the legacy-compatible facade API used by routes / MCP / sync
- optional dual-write / dual-read evaluation (default off)
- unified external_id / dedupe_key handling
- admin-facing backend health listing
"""

from __future__ import annotations

import os
import threading

from .backends import JsonFallbackBackend, Mem0Backend
from .memory_models import (
    BackendHealth,
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)
from .backends.base import dedupe_key, scope_identity


class MemoryService:
    def __init__(self, backends: dict | None = None, default: str | None = None):
        self.lock = threading.RLock()
        self._backends: dict[str, object] = {}
        self._default = "json"
        self.error = None
        if backends:
            # explicit injection (used mainly by tests)
            self._backends = dict(backends)
            self._default = default or next(iter(self._backends), "json")
        else:
            self._register_configured()

    # -- backend registry -------------------------------------------------
    def _register_configured(self):
        configured = os.getenv("DHUB_MEMORY_BACKENDS", "") or os.getenv(
            "DHUB_MEMORY_BACKEND", "mem0"
        )
        names = [n.strip() for n in configured.split(",") if n.strip()]
        if not names:
            names = ["mem0"]
        default = os.getenv("DHUB_MEMORY_BACKEND", "mem0").lower()
        self._default = "json"
        for name in names:
            key = name.lower()
            if key == "mem0":
                self._backends["mem0"] = Mem0Backend()
            elif key == "json":
                self._backends["json"] = JsonFallbackBackend()
            elif key == "agent_memory":
                self._register_tencent_backend()
            elif key == "tencent":
                self._register_tencent_backend()
            else:
                self.error = f"unknown memory backend: {name}"
        # choose default: prefer a configured backend that is actually usable
        if self._backends.get(default) is not None:
            candidate = default
        else:
            candidate = "mem0" if "mem0" in self._backends else "json"
        # Degraded operation: if the preferred backend is not healthy (e.g.
        # mem0 deps missing), fall back to a working backend while keeping the
        # configured name available for introspection.
        if candidate in self._backends:
            self._default = candidate
        if self._default not in self._backends:
            self._backends.setdefault("json", JsonFallbackBackend())
            self._default = "json"
        try:
            preferred = self._backends.get(self._default)
            if preferred is not None and not preferred.health().ok:
                for name, bk in self._backends.items():
                    if name == self._default:
                        continue
                    try:
                        if bk.health().ok:
                            self._default = name
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    def _register_tencent_backend(self):
        # Deferred import to avoid hard dependency at import time.
        try:
            from .backends.tencent_backend import TencentAgentMemoryBackend

            self._backends["agent_memory"] = TencentAgentMemoryBackend()
        except Exception as exc:  # pragma: no cover - defensive
            self.error = f"failed to register tencent backend: {exc}"

    def register(self, name: str, backend: object):
        with self.lock:
            self._backends[name] = backend

    def backend_names(self) -> list[str]:
        return list(self._backends.keys())

    def default_backend(self) -> object:
        with self.lock:
            return self._backends.get(self._default)

    def backend(self, name: str | None = None) -> object:
        name = name or self._default
        with self.lock:
            return self._backends.get(name)

    def health(self) -> list[BackendHealth]:
        result = []
        with self.lock:
            names = list(self._backends.keys())
        for name in names:
            bk = self._backends.get(name)
            try:
                result.append(bk.health())
            except Exception as exc:  # pragma: no cover
                result.append(
                    BackendHealth(backend=name, ok=False, detail=str(exc))
                )
        return result

    def primary_health(self) -> BackendHealth:
        bk = self.default_backend()
        if bk is None:
            return BackendHealth(backend=self._default, ok=False, detail="unavailable")
        return bk.health()

    # -- dual mode helpers ------------------------------------------------
    def _dual_write(self) -> bool:
        return os.getenv("DHUB_MEMORY_DUAL_WRITE", "false").lower() == "true"

    def _dual_read(self) -> bool:
        return os.getenv("DHUB_MEMORY_DUAL_READ", "false").lower() == "true"

    def _result_limit(self) -> int:
        try:
            return int(os.getenv("DHUB_MEMORY_RESULT_LIMIT", "10"))
        except ValueError:
            return 10

    def _max_chars(self) -> int:
        try:
            return int(os.getenv("DHUB_MEMORY_MAX_CHARS", "12000"))
        except ValueError:
            return 12000

    # -- legacy-compatible facade ----------------------------------------
    @property
    def backend_name(self) -> str:
        return self._default

    def _scope(self, namespace: str, agent_id: str) -> MemoryScope:
        return MemoryScope(namespace=namespace, agent_id=agent_id)

    def _record(self, namespace, agent_id, content, metadata=None) -> MemoryRecord:
        meta = metadata or {}
        raw_source = meta.get("source")
        valid_sources = {"user", "agent", "session", "wiki", "imported", "system"}
        source = raw_source if raw_source in valid_sources else "agent"
        return MemoryRecord(
            content=content,
            namespace=namespace,
            agent_id=agent_id,
            metadata=meta,
            source=source,
            provenance=meta.get("provenance"),
        )

    # -- public ops (mirror original MemoryStore API) --------------------
    def add(self, namespace, agent_id, content, metadata=None, infer=True):
        record = self._record(namespace, agent_id, content, metadata)
        scope = self._scope(namespace, agent_id)
        primary = self.default_backend()
        result = self._add_to(primary, record, infer)
        if self._dual_write():
            for name, bk in self._backends.items():
                if bk is primary:
                    continue
                self._add_to(bk, record, infer)
        return self._result_map(result, dedupe=dedupe_key(record), scope=scope)

    def _add_to(self, backend, record, infer):
        try:
            return backend.add(record, infer=infer)
        except Exception as exc:
            return MemoryResult(
                status="error", backend=getattr(backend, "name", "unknown"),
                error=str(exc)
            )

    def search(self, namespace, agent_id, query, limit=10):
        q = MemoryQuery(
            query=query, namespace=namespace, agent_id=agent_id, limit=limit
        )
        primary = self.default_backend()
        results = self._search_to(primary, q)
        if self._dual_read():
            report = {}
            for name, bk in self._backends.items():
                if bk is primary:
                    continue
                report[name] = [r.model_dump(exclude_none=True)
                                for r in self._search_to(bk, q)]
            return {
                "results": [r.model_dump(exclude_none=True) for r in results],
                "backend": getattr(primary, "name", self._default),
                "dual_read": report,
            }
        return {
            "results": [r.model_dump(exclude_none=True) for r in results],
            "backend": getattr(primary, "name", self._default),
        }

    def _search_to(self, backend, q):
        try:
            return backend.search(q)
        except Exception as exc:
            # degraded operation: log and return empty
            self.error = str(exc)
            return []

    def list(self, namespace, agent_id, limit=100):
        scope = self._scope(namespace, agent_id)
        backend = self.default_backend()
        if hasattr(backend, "list"):
            try:
                records = backend.list(scope, limit)
                return {
                    "results": [r.model_dump(exclude_none=True) for r in records],
                    "backend": getattr(backend, "name", self._default),
                }
            except Exception as exc:
                self.error = str(exc)
        # fall back to export
        records = list(self._export_to(backend, scope))[-limit:][::-1]
        return {
            "results": [r.model_dump(exclude_none=True) for r in records],
            "backend": getattr(backend, "name", self._default),
        }

    def get(self, namespace, agent_id, memory_id):
        scope = self._scope(namespace, agent_id)
        backend = self.default_backend()
        rec = backend.get(memory_id, scope)
        return rec.model_dump(exclude_none=True) if rec else None

    def update(self, namespace, agent_id, memory_id, patch: dict):
        scope = self._scope(namespace, agent_id)
        backend = self.default_backend()
        result = backend.update(memory_id, MemoryPatch(**patch), scope)
        return {
            "status": result.status,
            "id": result.id,
            "backend": result.backend,
            "error": result.error,
        }

    def delete(self, memory_id):
        # legacy delete resolves scope per row; try across backends
        backend = self.default_backend()
        scope = MemoryScope(namespace="global", agent_id="shared")
        result = backend.delete(memory_id, scope)
        return result.status == "ok"

    def export(self, namespace, agent_id):
        scope = self._scope(namespace, agent_id)
        return [
            r.model_dump(exclude_none=True)
            for r in self._export_to(self.default_backend(), scope)
        ]

    def _export_to(self, backend, scope):
        try:
            return list(backend.export(scope))
        except Exception as exc:
            self.error = str(exc)
            return []

    @staticmethod
    def _result_map(result: MemoryResult, dedupe=None, scope=None):
        payload = {
            "status": result.status,
            "id": result.id,
            "backend": result.backend,
            "results": result.results,
        }
        if result.error:
            payload["error"] = result.error
        if dedupe:
            payload["dedupe_key"] = dedupe
        if result.external_id:
            payload["external_id"] = result.external_id
        return payload
