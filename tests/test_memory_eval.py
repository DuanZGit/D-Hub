"""Tests for the offline memory evaluation command (Phase 5)."""

import json

import pytest

from dhub.memory_eval import evaluate, _make_backend
from dhub.backends.json_fallback import JsonFallbackBackend
from dhub.memory_models import MemoryRecord


def test_evaluate_reports_hit_rate(tmp_path):
    backend = JsonFallbackBackend(path=tmp_path / "mem.json")
    backend.add(MemoryRecord(content="Use PostgreSQL for storage", namespace="global", agent_id="shared"))
    backend.add(MemoryRecord(content="Deploy via systemd", namespace="global", agent_id="shared"))
    queries = [
        {"query": "postgres", "expected_keywords": ["postgres"]},
        {"query": "deploy", "expected_keywords": ["systemd"]},
        {"query": "nothing here", "expected_keywords": ["missing"]},
    ]
    report = evaluate(backend, queries, k=5)
    assert report["backend"] == "json"
    assert report["queries"] == 3
    assert report["top_k_hit_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert report["error_rate"] == 0.0
    assert report["mean_reciprocal_rank"] > 0


def test_make_backend_unknown_raises():
    with pytest.raises(ValueError):
        _make_backend("nonexistent")


def test_eval_cli_runs(tmp_path, monkeypatch, capsys):
    dataset = tmp_path / "ds.json"
    dataset.write_text(
        json.dumps({"queries": [{"query": "x", "expected_keywords": ["x"]}]}),
        encoding="utf-8",
    )
    from dhub.memory_eval import main
    monkeypatch.setattr(
        "sys.argv",
        ["memory_eval", "--dataset", str(dataset), "--backends", "json", "--k", "1"],
    )
    main()
    out = capsys.readouterr().out
    assert '"backend": "json"' in out
