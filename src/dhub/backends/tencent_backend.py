"""TencentDB Agent Memory adapter (v3 data-plane protocol).

Protocol confirmed against the public TencentCloud/TencentDB-Agent-Memory
repository (MemoryCore gateway + python sdk/memory-core):
  - Base path: /v3/...
  - Auth: Authorization: Bearer <api_key> + x-tdai-service-id: <service_id>
  - Response envelope: {"code":0,"message","data","request_id"};
    code != 0 -> error (carries request_id, header x-qcloud-transaction-id)
  - Isolation fields team_id / agent_id / user_id (and optional session_id)
    are required in request bodies.
  - add:      POST /v3/conversation/add   {messages, session_id}
  - search:   POST /v3/conversation/search {query, limit, session_id}
  - query:    POST /v3/conversation/query  {limit, offset, session_id}
              -> {messages:[{id,role,content,timestamp,...}], total}
  - delete:   POST /v3/conversation/delete {message_ids, session_ids}
  - update:   POST /v3/atomic/update       {id, content}

All network I/O is bounded (timeout), uses bounded retry + exponential backoff,
a simple circuit breaker, and never logs secrets. The external protocol is
mapped to d-hub canonical MemoryRecord inside this adapter only.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Iterable

import httpx

from ..memory_models import (
    BackendHealth,
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)
from .base import scope_identity

logger = logging.getLogger("dhub.memory.tencent")

API_VERSION = "v3"


class _CircuitBreaker:
    """Minimal circuit breaker: opens after N consecutive failures for cooldown."""

    def __init__(self, max_failures=3, cooldown_s=30):
        self.max_failures = max_failures
        self.cooldown_s = cooldown_s
        self.failures = 0
        self.open_until = 0.0
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            if time.monotonic() >= self.open_until:
                return True
            return False

    def record_failure(self):
        with self.lock:
            self.failures += 1
            if self.failures >= self.max_failures:
                self.open_until = time.monotonic() + self.cooldown_s

    def record_success(self):
        with self.lock:
            self.failures = 0
            self.open_until = 0.0


class TencentAgentMemoryBackend:
    name = "agent_memory"

    def __init__(self, transport=None):
        self.endpoint = os.getenv("DHUB_AGENT_MEMORY_URL", "").rstrip("/")
        self.api_key = os.getenv("DHUB_AGENT_MEMORY_API_KEY", "")
        self.service_id = os.getenv("DHUB_AGENT_MEMORY_SERVICE_ID", "")
        self.api_version = os.getenv("DHUB_AGENT_MEMORY_API_VERSION", API_VERSION)
        self.namespace = os.getenv("DHUB_AGENT_MEMORY_NAMESPACE", "")
        self.timeout = self._env_ms("DHUB_AGENT_MEMORY_TIMEOUT_MS", 5000) / 1000.0
        try:
            self.retries = int(os.getenv("DHUB_AGENT_MEMORY_RETRIES", "2"))
        except ValueError:
            self.retries = 2
        self.team_id = os.getenv("DHUB_AGENT_MEMORY_TEAM_ID", "")
        self.user_id = os.getenv("DHUB_AGENT_MEMORY_USER_ID", "")
        self._transport = transport
        self._circuit = _CircuitBreaker()
        self.error = None
        self.lock = threading.RLock()
        if not (self.endpoint and self.api_key):
            self.error = "DHUB_AGENT_MEMORY_URL / DHUB_AGENT_MEMORY_API_KEY not configured"

    @staticmethod
    def _env_ms(name, default):
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    # -- low level transport ----------------------------------------------
    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.service_id:
            headers["x-tdai-service-id"] = self.service_id
        return headers

    def _isolation(self, scope: MemoryScope) -> dict:
        """Map a d-hub namespace to Tencent isolation fields + session_id."""
        agent_id = scope.agent_id or "shared"
        return {
            "team_id": self.team_id or "default",
            "agent_id": agent_id,
            "user_id": self.user_id or "shared",
            "session_id": self.namespace or scope.namespace,
        }

    def _post(self, path: str, body: dict, *, retry_auth: bool = True):
        if not self.endpoint or not self.api_key:
            return MemoryResult(
                status="error", backend=self.name,
                error=self.error or "agent memory not configured"
            )
        if not self._circuit.allow():
            return MemoryResult(
                status="error", backend=self.name,
                error="circuit breaker open; external memory service degraded"
            )
        url = self.endpoint + path
        attempt = 0
        while True:
            attempt += 1
            retryable = False
            try:
                with httpx.Client(timeout=self.timeout, verify=True, transport=self._transport) as client:
                    resp = client.post(url, json=body, headers=self._headers())
                status = resp.status_code
                if status in (401, 403):
                    # auth failures are not retried
                    self._circuit.record_failure()
                    return MemoryResult(
                        status="error", backend=self.name,
                        error=f"authentication failed (HTTP {status})"
                    )
                if status == 429 or status >= 500:
                    retryable = True
                    error = f"HTTP {status}"
                elif status >= 400:
                    return self._decode(resp)
                else:
                    self._circuit.record_success()
                    return self._decode(resp)
            except httpx.TimeoutException as exc:
                error = f"timeout after {self.timeout:.1f}s"
                retryable = True
            except (httpx.HTTPError, OSError) as exc:
                error = f"network error: {type(exc).__name__}"
                retryable = True
            if not retryable or attempt > self.retries:
                self._circuit.record_failure()
                return MemoryResult(
                    status="error", backend=self.name, error=error
                )
            time.sleep(0.2 * (2 ** (attempt - 1)))  # exponential backoff

    def _decode(self, resp: httpx.Response) -> MemoryResult | dict:
        request_id = (
            resp.headers.get("x-qcloud-transaction-id")
            or resp.headers.get("x-trace-id")
            or ""
        )
        try:
            data = resp.json()
        except ValueError:
            return MemoryResult(
                status="error", backend=self.name,
                error="malformed response from agent memory service"
            )
        if not isinstance(data, dict) or data.get("code") != 0:
            return MemoryResult(
                status="error", backend=self.name,
                error=str(data.get("message") or "unknown error"),
            )
        payload = data.get("data") or {}
        if isinstance(payload, dict):
            payload["_request_id"] = request_id
        return payload

    # -- MemoryBackend protocol ------------------------------------------
    def health(self) -> BackendHealth:
        if not self.endpoint or not self.api_key:
            return BackendHealth(
                backend=self.name, ok=False,
                detail="not configured (DHUB_AGENT_MEMORY_URL/API_KEY missing)"
            )
        # A light query is used to probe availability. Count is cheap.
        body = {
            "team_id": self.team_id or "default",
            "agent_id": "health",
            "user_id": "health",
            "limit": 1,
        }
        result = self._post(f"/{self.api_version}/conversation/query", body)
        if isinstance(result, MemoryResult):
            return BackendHealth(
                backend=self.name, ok=False, detail=result.error
            )
        return BackendHealth(backend=self.name, ok=True)

    def add(self, record: MemoryRecord, *, infer: bool = True) -> MemoryResult:
        scope = MemoryScope(
            namespace=record.namespace, agent_id=record.agent_id
        )
        body = {
            **self._isolation(scope),
            "messages": [
                {
                    "role": "assistant",
                    "content": record.content,
                    "metadata": {
                        "memory_type": record.memory_type,
                        "source": record.source,
                        "provenance": record.provenance,
                    },
                }
            ],
            "request_id": str(uuid.uuid4()),
        }
        result = self._post(f"/{self.api_version}/conversation/add", body)
        if isinstance(result, MemoryResult):
            return result
        ids = result.get("accepted_ids") or result.get("ids") or []
        rid = ids[0] if ids else None
        return MemoryResult(
            status="ok",
            id=rid or record.id,
            backend=self.name,
            created=True,
            external_id=rid or record.id,
            results=[result],
        )

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        scope = MemoryScope(namespace=query.namespace, agent_id=query.agent_id)
        body = {
            **self._isolation(scope),
            "query": query.query,
            "limit": query.limit,
        }
        result = self._post(f"/{self.api_version}/conversation/search", body)
        if isinstance(result, MemoryResult):
            self.error = result.error
            return []
        records = []
        for row in (result.get("results") or [])[: query.limit]:
            records.append(self._record_from_row(row, query.namespace))
        return records

    def get(self, memory_id: str, scope: MemoryScope) -> MemoryRecord | None:
        body = {
            **self._isolation(scope),
            "limit": 100,
        }
        result = self._post(f"/{self.api_version}/conversation/query", body)
        if isinstance(result, MemoryResult):
            return None
        for row in (result.get("messages") or []):
            if str(row.get("id")) == str(memory_id):
                return self._record_from_row(row, scope.namespace)
        return None

    def update(self, memory_id: str, patch: MemoryPatch, scope: MemoryScope) -> MemoryResult:
        body = {
            **self._isolation(scope),
            "id": memory_id,
            "content": patch.content or "",
        }
        result = self._post(f"/{self.api_version}/atomic/update", body)
        if isinstance(result, MemoryResult):
            return result
        return MemoryResult(status="ok", id=memory_id, backend=self.name)

    def delete(self, memory_id: str, scope: MemoryScope) -> MemoryResult:
        body = {
            **self._isolation(scope),
            "message_ids": [memory_id],
        }
        result = self._post(f"/{self.api_version}/conversation/delete", body)
        if isinstance(result, MemoryResult):
            return result
        return MemoryResult(status="ok", id=memory_id, backend=self.name)

    def export(self, scope: MemoryScope) -> Iterable[MemoryRecord]:
        offset = 0
        limit = 50
        while True:
            body = {
                **self._isolation(scope),
                "limit": limit,
                "offset": offset,
            }
            result = self._post(f"/{self.api_version}/conversation/query", body)
            if isinstance(result, MemoryResult):
                return
            rows = result.get("messages") or []
            if not rows:
                return
            for row in rows:
                yield self._record_from_row(row, scope.namespace)
            if len(rows) < limit:
                return
            offset += limit

    @staticmethod
    def _record_from_row(row: dict, namespace: str) -> MemoryRecord:
        metadata = row.get("metadata") or {}
        return MemoryRecord(
            id=str(row.get("id", "")),
            content=row.get("content", ""),
            namespace=namespace,
            agent_id=str(row.get("agent_id", "shared")),
            memory_type=metadata.get("memory_type", "note"),
            source=metadata.get("source", "agent"),
            provenance=metadata.get("provenance"),
            metadata=metadata,
            created_at=row.get("timestamp") or row.get("recorded_at"),
            updated_at=row.get("recorded_at"),
        )
