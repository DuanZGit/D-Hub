"""d-hub configuration and safe filesystem primitives."""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.getenv("DHUB_ROOT", "/opt/d-hub"))
PORT = int(os.getenv("DHUB_PORT", "10101"))
VERSION = "0.1.0"
TIERS = ("global", "agents", "projects")
TYPES = ("mcp", "skills", "wiki", "files")


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
        root / "scripts",
        root / "ui",
    ):
        d.mkdir(parents=True, exist_ok=True)


class file_lock:
    def __init__(self, name: str):
        self.path = ROOT / "data" / "locks" / (safe_part(name) + ".lock")
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+")
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


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
