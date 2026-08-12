from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

import httpx

from .config import (
    ROOT,
    VERSION,
    atomic_json,
    file_lock,
    mutation_lock,
    now,
    read_json,
    safe_part,
)


class AgentRegistry:
    def __init__(self):
        self.path = ROOT / "config" / "agents.json"

    def all(self):
        return read_json(self.path, {}) or {}

    def register(self, data):
        agent_id = safe_part(data.get("agent_id"))
        with mutation_lock("agents"):
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
        agent_id = safe_part(agent_id)
        with mutation_lock("agents"):
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
            "version": VERSION,
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
    with file_lock("backup"), file_lock("assets"):
        return _backup()


def _backup():
    retention_days = _backup_retention_days()
    stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000:06d}"
    destination = ROOT / "backups" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(0o700)
    try:
        archive = destination / "data.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name in ("mcp", "skills", "wiki", "files", "config", "data"):
                bundle.add(ROOT / name, arcname=name)
        archive.chmod(0o600)
        memory_backend = os.getenv("DHUB_MEMORY_BACKEND", "mem0").lower()
        database_status = "not-required"
        if memory_backend == "mem0":
            if not os.getenv("MEM0_DB_PASSWORD"):
                raise RuntimeError("MEM0_DB_PASSWORD is required for a mem0 backup")
            if not shutil_which("pg_dump"):
                raise RuntimeError("pg_dump is required for a mem0 backup")
            dump = destination / "mem0.dump"
            command = [
                "pg_dump",
                "--format=custom",
                "--file",
                str(dump),
                "-h",
                os.getenv("MEM0_DB_HOST", "127.0.0.1"),
                "-U",
                os.getenv("MEM0_DB_USER", "mem0"),
                os.getenv("MEM0_DB_NAME", "mem0"),
            ]
            environment = dict(os.environ, PGPASSWORD=os.environ["MEM0_DB_PASSWORD"])
            subprocess.run(command, check=True, env=environment)
            dump.chmod(0o600)
            database_status = "ok"
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    _prune_backups(destination, retention_days)
    return {
        "status": "ok",
        "path": str(destination),
        "archive": str(archive),
        "database": database_status,
    }


def _backup_retention_days():
    retention_days = int(os.getenv("DHUB_BACKUP_RETENTION_DAYS", "7"))
    if retention_days < 1:
        raise ValueError("DHUB_BACKUP_RETENTION_DAYS must be at least 1")
    return retention_days


def _prune_backups(current, retention_days=None):
    retention_days = retention_days or _backup_retention_days()
    cutoff = time.time() - retention_days * 86400
    for candidate in (ROOT / "backups").iterdir():
        if (
            candidate != current
            and candidate.is_dir()
            and not candidate.name.startswith(".restore-")
            and candidate.stat().st_mtime < cutoff
        ):
            shutil.rmtree(candidate)


def restore(name):
    with file_lock("backup"), file_lock("assets"):
        return _restore(name)


def _restore(name):
    safe_name = safe_part(name)
    archive = ROOT / "backups" / safe_name / "data.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(name)
    allowed_roots = {"mcp", "skills", "wiki", "files", "config", "data"}
    with tarfile.open(archive, "r:gz") as bundle:
        root = ROOT.resolve()
        members = bundle.getmembers()
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not relative.parts
                or relative.parts[0] not in allowed_roots
                or member.issym()
                or member.islnk()
                or member.isdev()
                or member.isfifo()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("unsafe backup archive")
            target = (ROOT / member.name).resolve()
            if root != target and root not in target.parents:
                raise ValueError("unsafe backup archive")
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=ROOT / "backups") as tmp:
            staging = Path(tmp) / "staging"
            staging.mkdir()
            bundle.extractall(staging, members=members)
            database_status = _replace_roots(
                staging, allowed_roots, lambda: _restore_database(archive.parent)
            )
    return {"status": "ok", "restored": safe_name, "database": database_status}


def _restore_database(backup_dir):
    dump = backup_dir / "mem0.dump"
    if not dump.is_file():
        return "not-required"
    if not os.getenv("MEM0_DB_PASSWORD"):
        raise RuntimeError("MEM0_DB_PASSWORD is required to restore mem0.dump")
    if not shutil_which("pg_restore"):
        raise RuntimeError("pg_restore is required to restore mem0.dump")
    environment = dict(os.environ, PGPASSWORD=os.environ["MEM0_DB_PASSWORD"])
    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--single-transaction",
        "-h",
        os.getenv("MEM0_DB_HOST", "127.0.0.1"),
        "-U",
        os.getenv("MEM0_DB_USER", "mem0"),
        "-d",
        os.getenv("MEM0_DB_NAME", "mem0"),
        str(dump),
    ]
    subprocess.run(command, check=True, env=environment)
    return "ok"


def _replace_roots(staging, names, after_replace=lambda: None):
    rollback = staging.parent / "rollback"
    rollback.mkdir()
    moved = []
    try:
        for name in sorted(names):
            source = staging / name
            if not source.is_dir():
                raise ValueError(f"backup archive is missing {name}")
            current = ROOT / name
            previous = rollback / name
            if current.exists():
                current.replace(previous)
            moved.append(name)
            source.replace(current)
        result = after_replace()
    except Exception:
        for name in reversed(moved):
            current = ROOT / name
            previous = rollback / name
            if current.exists():
                shutil.rmtree(current)
            if previous.exists():
                previous.replace(current)
        raise
    return result


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
        with mutation_lock("sync-state"):
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
