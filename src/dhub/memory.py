from __future__ import annotations

import os
import threading
import uuid

from .config import ROOT, atomic_json, mutation_lock, now, read_json


class MemoryStore:
    """Mem0 adapter with durable JSON fallback for bootstrap/degraded operation."""

    def __init__(self):
        self.path = ROOT / "data" / "memory-fallback.json"
        self.lock = threading.RLock()
        self.backend = "json"
        self.error = None
        self.memory = None
        self._init_mem0()

    def _init_mem0(self):
        if os.getenv("DHUB_MEMORY_BACKEND", "mem0").lower() == "json":
            return
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
            self.backend = "mem0"
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.error = str(exc)

    @staticmethod
    def user_id(namespace, agent_id):
        if namespace in ("global", "global/shared"):
            return "global:shared"
        tier, ident = namespace.strip("/").split("/", 1)
        if tier == "agents":
            return f"global:{ident}"
        if tier == "projects":
            return f"global:{agent_id}:{ident}"
        raise ValueError("invalid memory namespace")

    def add(self, namespace, agent_id, content, metadata=None, infer=True):
        uid = self.user_id(namespace, agent_id)
        if self.memory:
            with mutation_lock("memory"):
                out = self.memory.add(
                    content, user_id=uid, metadata=metadata or {}, infer=infer
                )
            rows = out.get("results", [])
            return {
                "status": "ok",
                "id": rows[0].get("id") if rows else None,
                "backend": self.backend,
                "results": rows,
            }
        with self.lock, mutation_lock("memory"):
            rows = read_json(self.path, []) or []
            item = {
                "id": str(uuid.uuid4()),
                "memory": content,
                "content": content,
                "user_id": uid,
                "metadata": metadata or {},
                "created_at": now(),
            }
            rows.append(item)
            atomic_json(self.path, rows)
        return {"status": "ok", "id": item["id"], "backend": self.backend}

    def search(self, namespace, agent_id, query, limit=10):
        uid = self.user_id(namespace, agent_id)
        if self.memory:
            return self.memory.search(query, top_k=limit, filters={"user_id": uid})
        terms = query.lower().split()
        rows = read_json(self.path, []) or []
        found = []
        for x in rows:
            if x.get("user_id") != uid:
                continue
            text = x.get("memory", x.get("content", "")).lower()
            score = sum(text.count(t) for t in terms)
            if not terms or score:
                y = dict(x)
                y["score"] = float(score)
                found.append(y)
        return {
            "results": sorted(
                found, key=lambda x: (x["score"], x.get("created_at", "")), reverse=True
            )[:limit],
            "backend": self.backend,
        }

    def list(self, namespace, agent_id, limit=100):
        uid = self.user_id(namespace, agent_id)
        if self.memory:
            return self.memory.get_all(filters={"user_id": uid}, top_k=limit)
        rows = [x for x in (read_json(self.path, []) or []) if x.get("user_id") == uid]
        return {"results": rows[-limit:][::-1], "backend": self.backend}

    def delete(self, memory_id):
        if self.memory:
            with mutation_lock("memory"):
                self.memory.delete(memory_id)
            return True
        with self.lock, mutation_lock("memory"):
            rows = read_json(self.path, []) or []
            new = [x for x in rows if x.get("id") != memory_id]
            atomic_json(self.path, new)
            return len(new) != len(rows)
