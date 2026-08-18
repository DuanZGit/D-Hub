"""Offline memory retrieval evaluation.

Usage:
    python -m dhub.memory_eval --dataset <path> --backends mem0,agent_memory --k 5

Dataset format (JSON):
{
  "queries": [
    {"query": "...", "expected_keywords": ["a", "b"], "expected_ids": ["id1"]},
    ...
  ]
}

It runs the query against each configured backend and reports top-k hit rate,
reciprocal rank, latency, error rate, result character/token estimate, and
backend availability. Real remote services are NOT contacted unless configured;
unconfigured backends are reported as unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from .memory_models import MemoryQuery, MemoryScope, MemoryRecord
from .backends.json_fallback import JsonFallbackBackend
from .backends.mem0_backend import Mem0Backend


def _make_backend(name: str):
    name = name.lower()
    if name == "json":
        return JsonFallbackBackend()
    if name == "mem0":
        return Mem0Backend()
    if name == "agent_memory" or name == "tencent":
        from .backends.tencent_backend import TencentAgentMemoryBackend

        return TencentAgentMemoryBackend()
    raise ValueError(f"unknown backend: {name}")


def _hit(record: MemoryRecord, item: dict) -> bool:
    text = record.content.lower()
    if item.get("expected_ids"):
        if record.id in item["expected_ids"]:
            return True
        return False
    keywords = item.get("expected_keywords") or []
    return all(k.lower() in text for k in keywords)


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def evaluate(backend, queries, k):
    stats = {
        "backend": getattr(backend, "name", "?"),
        "queries": len(queries),
        "top_k_hits": 0,
        "reciprocal_rank_sum": 0.0,
        "latency_ms": [],
        "errors": 0,
        "chars": 0,
        "tokens": 0,
    }
    for item in queries:
        q = MemoryQuery(
            query=item.get("query", ""),
            namespace=item.get("namespace", "global"),
            agent_id=item.get("agent_id", "shared"),
            limit=k,
        )
        start = time.monotonic()
        try:
            results = backend.search(q)[:k]
        except Exception:
            stats["errors"] += 1
            continue
        stats["latency_ms"].append(round((time.monotonic() - start) * 1000, 2))
        for rank, rec in enumerate(results, start=1):
            stats["chars"] += len(rec.content)
            stats["tokens"] += _tokens(rec.content)
            if _hit(rec, item):
                stats["top_k_hits"] += 1
                stats["reciprocal_rank_sum"] += 1.0 / rank
                break
    n = stats["queries"]
    return {
        "backend": stats["backend"],
        "queries": n,
        "top_k_hit_rate": round(stats["top_k_hits"] / n, 4) if n else 0,
        "mean_reciprocal_rank": (
            round(stats["reciprocal_rank_sum"] / n, 4) if n else 0
        ),
        "mean_latency_ms": (
            round(sum(stats["latency_ms"]) / len(stats["latency_ms"]), 2)
            if stats["latency_ms"]
            else None
        ),
        "error_rate": round(stats["errors"] / n, 4) if n else 0,
        "result_chars": stats["chars"],
        "result_tokens": stats["tokens"],
        "available": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="D-Hub memory retrieval evaluation")
    parser.add_argument("--dataset", required=True, help="path to dataset JSON")
    parser.add_argument(
        "--backends",
        default="json",
        help="comma-separated backend names (mem0,agent_memory,json)",
    )
    parser.add_argument("--k", type=int, default=5, help="top-k")
    args = parser.parse_args(argv)

    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    queries = dataset.get("queries", [])

    names = [n.strip() for n in args.backends.split(",") if n.strip()]
    report = {"dataset": args.dataset, "k": args.k, "queries": len(queries), "backends": []}
    for name in names:
        try:
            backend = _make_backend(name)
        except ValueError as exc:
            print(json.dumps({"backend": name, "error": str(exc)}, ensure_ascii=False))
            continue
        health = backend.health()
        if not health.ok:
            report["backends"].append(
                {
                    "backend": getattr(backend, "name", name),
                    "available": False,
                    "detail": health.detail,
                }
            )
            continue
        report["backends"].append(evaluate(backend, queries, args.k))

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
