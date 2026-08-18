"""Legacy-compatible MemoryStore facade backed by MemoryService.

The original MemoryStore talked to mem0 directly with a JSON fallback. To keep
all existing routes / MCP tools / sync code working while introducing pluggable
backends, this module exposes the same class and method signatures, delegating
to MemoryService under the hood.
"""

from __future__ import annotations

import os
import threading

from .memory_service import MemoryService
from .memory_models import MemoryScope


class MemoryStore:
    """Facade over MemoryService preserving the original MemoryStore API."""

    def __init__(self):
        self.service = MemoryService()
        self.lock = threading.RLock()
        self.backend = self.service.backend_name
        self.error = self.service.error
        # kept for back-compat with code/tests that read .path or .memory
        self.path = None
        self.memory = None

    @staticmethod
    def user_id(namespace, agent_id):
        if namespace in ("global", "global/shared"):
            return "global:shared"
        tier, ident = namespace.strip("/").split("/", 1)
        if tier == "agents":
            return f"global:{ident}"
        if tier == "projects":
            return f"global:project:{ident}"
        raise ValueError("invalid memory namespace")

    def add(self, namespace, agent_id, content, metadata=None, infer=True):
        result = self.service.add(namespace, agent_id, content, metadata, infer)
        self.backend = self.service.backend_name
        self.error = self.service.error
        return result

    def search(self, namespace, agent_id, query, limit=10):
        result = self.service.search(namespace, agent_id, query, limit)
        self.backend = self.service.backend_name
        self.error = self.service.error
        return result

    def list(self, namespace, agent_id, limit=100):
        result = self.service.list(namespace, agent_id, limit)
        self.backend = self.service.backend_name
        self.error = self.service.error
        return result

    def get(self, namespace, agent_id, memory_id):
        return self.service.get(namespace, agent_id, memory_id)

    def update(self, namespace, agent_id, memory_id, patch):
        return self.service.update(namespace, agent_id, memory_id, patch)

    def delete(self, memory_id, namespace="global", agent_id="shared"):
        return self.service.delete(memory_id, namespace, agent_id)

    def export(self, namespace, agent_id):
        return self.service.export(namespace, agent_id)
