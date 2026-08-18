"""Tests for the pluggable MemoryBackend abstraction (Phase 1)."""

import pytest

from dhub.backends.json_fallback import JsonFallbackBackend
from dhub.backends.mem0_backend import Mem0Backend
from dhub.memory_models import (
    MemoryPatch,
    MemoryQuery,
    MemoryRecord,
    MemoryResult,
    MemoryScope,
)
from dhub.memory_service import MemoryService


def _json_service(tmp_path):
    """Build a MemoryService over a JsonFallbackBackend rooted in tmp_path."""
    backend = JsonFallbackBackend(path=tmp_path / "mem.json")
    return MemoryService(backends={"json": backend}, default="json"), backend


def test_json_backend_roundtrip(tmp_path):
    service, _ = _json_service(tmp_path)
    added = service.add("agents/codex", "codex", "remember alpha decision")
    assert added["status"] == "ok"
    assert added["backend"] == "json"
    found = service.search("agents/codex", "codex", "alpha decision")
    assert found["backend"] == "json"
    assert len(found["results"]) == 1
    assert "alpha decision" in found["results"][0]["content"]


def test_json_namespace_isolation(tmp_path):
    service, _ = _json_service(tmp_path)
    service.add("agents/a", "a", "secret of A")
    service.add("agents/b", "b", "secret of B")
    found = service.search("agents/a", "a", "secret")
    assert len(found["results"]) == 1
    assert "secret of A" in found["results"][0]["content"]


def test_backend_unconfigured_does_not_block_start(monkeypatch):
    # No keys set, mem0 cannot initialise -> json fallback is used by default.
    monkeypatch.delenv("NEW_API_KEY", raising=False)
    monkeypatch.delenv("DHUB_LLM_MODEL", raising=False)
    monkeypatch.delenv("DHUB_EMBED_MODEL", raising=False)
    monkeypatch.delenv("MEM0_DB_PASSWORD", raising=False)
    backend = JsonFallbackBackend()
    service = MemoryService(backends={"json": backend}, default="json")
    added = service.add("global", "shared", "bootstrap works")
    assert added["status"] == "ok"
    assert service.default_backend() is not None


def test_mem0_backend_missing_deps_reports_unhealthy():
    # In CI there is no mem0 env; backend should be constructed but report
    # unhealthy without raising.
    backend = Mem0Backend()
    health = backend.health()
    assert health.backend == "mem0"
    assert health.ok in (True, False)


def test_json_backend_health_and_protocol(tmp_path):
    backend = JsonFallbackBackend(path=tmp_path / "mem.json")
    health = backend.health()
    assert health.ok is True
    rec = MemoryRecord(content="hello world", namespace="global", agent_id="shared")
    result = backend.add(rec)
    assert isinstance(result, MemoryResult)
    assert result.status == "ok"
    hits = backend.search(
        MemoryQuery(query="hello", namespace="global", agent_id="shared")
    )
    assert len(hits) == 1
    got = backend.get(rec.id, MemoryScope(namespace="global", agent_id="shared"))
    assert got is not None and got.id == rec.id
    upd = backend.update(
        rec.id,
        MemoryPatch(content="hello universe"),
        MemoryScope(namespace="global", agent_id="shared"),
    )
    assert upd.status == "ok"
    hits2 = backend.search(
        MemoryQuery(query="universe", namespace="global", agent_id="shared")
    )
    assert len(hits2) == 1
    dele = backend.delete(rec.id, MemoryScope(namespace="global", agent_id="shared"))
    assert dele.status == "ok"
    assert (
        backend.get(rec.id, MemoryScope(namespace="global", agent_id="shared")) is None
    )


def test_dual_write_and_dual_read(tmp_path, monkeypatch):
    monkeypatch.setenv("DHUB_MEMORY_DUAL_WRITE", "true")
    monkeypatch.setenv("DHUB_MEMORY_DUAL_READ", "true")
    primary = JsonFallbackBackend(path=tmp_path / "mem.json")
    secondary = JsonFallbackBackend(path=tmp_path / "mem2.json")
    service = MemoryService(backends={"json": primary, "json2": secondary}, default="json")
    added = service.add("global", "shared", "dual content")
    assert added["status"] == "ok"
    found = service.search("global", "shared", "dual")
    assert "dual_read" in found
    assert len(found["results"]) == 1


def test_service_health_lists_all_backends(tmp_path):
    service, _ = _json_service(tmp_path)
    health = service.health()
    assert any(h.backend == "json" for h in health)
