"""d-hub configuration and safe filesystem primitives."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

ROOT = Path(os.getenv("DHUB_ROOT", "/opt/d-hub"))
PORT = int(os.getenv("DHUB_PORT", "10101"))
try:
    VERSION = version("d-hub")
except PackageNotFoundError:
    VERSION = "0.2.0"
TIERS = ("global", "agents", "projects")
TYPES = ("mcp", "skills", "wiki", "files", "sessions")
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_part(value: str) -> str:
    value = str(value or "").strip()
    if not value or value in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError("invalid namespace component")
    return value


def namespace_parts(namespace: str):
    bits = [safe_part(x) for x in str(namespace or "global").strip("/").split("/")]
    if bits == ["global"]:
        return ("global", None)
    if len(bits) == 2 and bits[0] in ("agents", "projects"):
        return (bits[0], bits[1])
    raise ValueError("namespace must be global, agents/<id>, or projects/<id>")


def ensure_layout(root=ROOT):
    for typ in TYPES:
        for tier in TIERS:
            (root / typ / tier).mkdir(parents=True, exist_ok=True)
    for d in (
        root / "config",
        root / "data",
        root / "logs",
        root / "backups",
        root / ".locks",
        root / "scripts",
        root / "ui",
    ):
        d.mkdir(parents=True, exist_ok=True)


class file_lock:
    def __init__(self, name: str):
        self.path = ROOT / ".locks" / (safe_part(name) + ".lock")
        self.stream = None
        with _LOCAL_LOCKS_GUARD:
            self.local_lock = _LOCAL_LOCKS.setdefault(str(self.path), threading.RLock())

    def __enter__(self):
        self.local_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.stream = self.path.open("a+b")
            if fcntl is not None:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                self.stream.seek(0, os.SEEK_END)
                if self.stream.tell() == 0:
                    self.stream.write(b"\0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_LOCK, 1)
            return self
        except Exception:
            if self.stream is not None:
                self.stream.close()
            self.local_lock.release()
            raise

    def __exit__(self, *_):
        try:
            if fcntl is not None:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
        finally:
            self.local_lock.release()


@contextmanager
def mutation_lock(name: str):
    """Serialize persisted-data mutations with backup and restore snapshots."""
    with file_lock("assets"), file_lock(name):
        yield


def atomic_bytes(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_text(path: Path, value: str):
    atomic_bytes(path, value.encode("utf-8"))


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def tier_paths(typ, agent_id=None, project=None):
    result = [("global", ROOT / typ / "global")]
    if agent_id:
        result.append(("agent", ROOT / typ / "agents" / safe_part(agent_id)))
    if project:
        result.append(("project", ROOT / typ / "projects" / safe_part(project)))
    return result


def merged_json(typ, agent_id=None, project=None):
    result = {}
    sources = {}
    for tier, directory in tier_paths(typ, agent_id, project):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            data = read_json(path)
            if isinstance(data, dict):
                result[path.stem] = data
                sources[path.stem] = tier
    return result, sources
