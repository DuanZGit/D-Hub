from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import time

import httpx

from .config import ROOT, atomic_json, file_lock, now, read_json, safe_part


class AgentRegistry:
    def __init__(self):
        self.path = ROOT / "config" / "agents.json"

    def all(self):
        return read_json(self.path, {}) or {}

    def register(self, data):
        agent_id = safe_part(data.get("agent_id"))
        agents = self.all()
        previous = agents.get(agent_id, {})
        item = {
            **previous,
            **data,
            "agent_id": agent_id,
            "enabled": data.get("enabled", previous.get("enabled", True)),
            "registered_at": previous.get("registered_at", now()),
            "last_seen": now(),
        }
        agents[agent_id] = item
        atomic_json(self.path, agents)
        return item

    def get(self, agent_id):
        item = self.all().get(agent_id)
        if not item:
            raise KeyError(agent_id)
        return item

    def delete(self, agent_id):
        agents = self.all()
        if agent_id not in agents:
            return False
        del agents[agent_id]
        atomic_json(self.path, agents)
        return True


class AuditLog:
    def __init__(self):
        self.path = ROOT / "logs" / "audit.jsonl"

    def write(self, action, success=True, **detail):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"created_at": now(), "action": action, "success": success, **detail}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list(self, limit=200):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        result = []
        for line in lines[-limit:][::-1]:
            try:
                result.append(json.loads(line))
            except ValueError:
                continue
        return result


class AppState:
    def __init__(self):
        self.started = time.monotonic()
        self.requests = 0
        self.registry = AgentRegistry()
        self.audit = AuditLog()

    def health(self):
        return {
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": round(time.monotonic() - self.started, 2),
            "requests": self.requests,
            "modules": [
                "mcp",
                "memory",
                "wiki",
                "skills",
                "files",
                "registry",
                "sync",
                "dashboard",
            ],
        }


def backup():
    with file_lock("backup"):
        return _backup()


def _backup():
    stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000:06d}"
    destination = ROOT / "backups" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "data.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in ("mcp", "skills", "wiki", "files", "config", "data"):
            bundle.add(ROOT / name, arcname=name)
    database_status = "skipped"
    if os.getenv("MEM0_DB_PASSWORD") and shutil_which("pg_dump"):
        dump = destination / "mem0.sql"
        command = [
            "pg_dump",
            "-h",
            os.getenv("MEM0_DB_HOST", "127.0.0.1"),
            "-U",
            os.getenv("MEM0_DB_USER", "mem0"),
            os.getenv("MEM0_DB_NAME", "mem0"),
        ]
        environment = dict(os.environ)
        if os.getenv("MEM0_DB_PASSWORD"):
            environment["PGPASSWORD"] = os.environ["MEM0_DB_PASSWORD"]
        with dump.open("wb") as output:
            subprocess.run(command, stdout=output, check=True, env=environment)
        database_status = "ok"
    return {
        "status": "ok",
        "path": str(destination),
        "archive": str(archive),
        "database": database_status,
    }


def restore(name):
    with file_lock("backup"):
        return _restore(name)


def _restore(name):
    safe_name = safe_part(name)
    archive = ROOT / "backups" / safe_name / "data.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(name)
    with tarfile.open(archive, "r:gz") as bundle:
        root = ROOT.resolve()
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if root != target and root not in target.parents:
                raise ValueError("unsafe backup archive")
        bundle.extractall(ROOT, filter="data")
    return {"status": "ok", "restored": safe_name}


def shutil_which(command):
    from shutil import which

    return which(command)


class SemanticSync:
    PROMPT = """你是知识语义编译器。将记忆转换成适合长期维护的 Markdown Wiki。保留事实和技术细节，不改变原意，不添加不存在的信息。输出 Markdown，包含标题、事实、决策、来源记忆 ID。"""

    def __init__(self, memory, wiki):
        self.memory = memory
        self.wiki = wiki
        self.history_path = ROOT / "logs" / "sync.jsonl"
        self.state_path = ROOT / "data" / "sync-state.json"

    def history(self, limit=100):
        if not self.history_path.exists():
            return []
        rows = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines()[-limit:][
            ::-1
        ]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def run(self):
        with file_lock("sync"):
            return self._run()

    def _run(self):
        model = os.getenv("DHUB_LLM_MODEL")
        key = os.getenv("NEW_API_KEY")
        if not model or not key:
            memories = self.memory.list("global", "shared", 200).get("results", [])
            return self._record(
                "blocked", len(memories), "NEW_API_KEY or DHUB_LLM_MODEL is missing"
            )
        ingested = self._wiki_to_memory()
        memories = self.memory.list("global", "shared", 200).get("results", [])
        if not memories:
            return self._record(
                "ok", 0, f"no global memories; ingested {ingested} wiki pages"
            )
        facts = [
            {
                "id": x.get("id"),
                "memory": x.get("memory", x.get("content", "")),
                "metadata": x.get("metadata", {}),
            }
            for x in memories
        ]
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": self.PROMPT},
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
            ],
        }
        response = httpx.post(
            os.getenv("NEW_API_BASE_URL", "http://127.0.0.1:3000/v1")
            + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        self.wiki.put("global", "memory-consensus", content, "semantic-sync")
        return self._record(
            "ok",
            len(memories),
            f"updated global/memory-consensus; ingested {ingested} wiki pages",
        )

    def _wiki_to_memory(self):
        state = read_json(self.state_path, {}) or {}
        ingested = 0
        for page in self.wiki.list("global"):
            if page["title"] == "memory-consensus":
                continue
            content = self.wiki.get("global", page["title"])["content"]
            digest = hashlib.sha256(content.encode()).hexdigest()
            key = f"global/{page['title']}"
            if state.get(key) == digest:
                continue
            self.memory.add(
                "global",
                "shared",
                content,
                metadata={"source": "wiki", "title": page["title"], "sha256": digest},
                infer=True,
            )
            state[key] = digest
            ingested += 1
        atomic_json(self.state_path, state)
        return ingested

    def _record(self, status, count, message):
        record = {
            "created_at": now(),
            "status": status,
            "memory_count": count,
            "message": message,
        }
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
