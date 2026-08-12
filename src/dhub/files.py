from __future__ import annotations

import mimetypes

from .config import (
    ROOT,
    atomic_bytes,
    atomic_text,
    file_lock,
    namespace_parts,
    safe_part,
    tier_paths,
)


class NamespaceFiles:
    def __init__(self):
        self.root = ROOT / "files"

    def directory(self, namespace):
        tier, ident = namespace_parts(namespace)
        return self.root / tier if tier == "global" else self.root / tier / ident

    def list(self, namespace):
        directory = self.directory(namespace)
        return [
            {
                "file": str(path.relative_to(directory)),
                "size": path.stat().st_size,
                "content_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "updated_at": path.stat().st_mtime,
            }
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        ]

    def safe_path(self, namespace, file):
        directory = self.directory(namespace)
        path = (directory / str(file)).resolve()
        if directory.resolve() != path and directory.resolve() not in path.parents:
            raise ValueError("invalid file path")
        return path

    def write(self, namespace, file, data):
        path = self.safe_path(namespace, file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock("files"):
            atomic_bytes(path, data)
        return {"file": str(file), "size": len(data)}

    def read(self, namespace, file):
        path = self.safe_path(namespace, file)
        if not path.is_file():
            raise FileNotFoundError(file)
        return path

    def delete(self, namespace, file):
        path = self.safe_path(namespace, file)
        if not path.is_file():
            return False
        with file_lock("files"):
            path.unlink()
        return True


class SkillStore:
    def __init__(self):
        self.root = ROOT / "skills"

    def directory(self, namespace):
        tier, ident = namespace_parts(namespace)
        return self.root / tier if tier == "global" else self.root / tier / ident

    @staticmethod
    def parts(name):
        parts = [safe_part(part) for part in str(name).strip("/").split("/") if part]
        if not parts:
            raise ValueError("invalid skill name")
        return parts

    def list(self, agent_id=None, project=None):
        merged, sources = {}, {}
        for tier, directory in tier_paths("skills", agent_id, project):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("SKILL.md")):
                key = str(path.parent.relative_to(directory))
                merged[key] = path.read_text(encoding="utf-8")
                sources[key] = tier
        return [
            {"name": name, "content": content, "source": sources[name]}
            for name, content in sorted(merged.items())
        ]

    def get(self, name, agent_id=None, project=None):
        for tier, directory in reversed(tier_paths("skills", agent_id, project)):
            path = directory.joinpath(*self.parts(name), "SKILL.md")
            if path.is_file():
                return {
                    "name": name,
                    "content": path.read_text(encoding="utf-8"),
                    "source": tier,
                }
        raise FileNotFoundError(name)

    def put(self, namespace, name, content):
        path = self.directory(namespace).joinpath(*self.parts(name), "SKILL.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock("skills"):
            atomic_text(path, content)
        return {"status": "ok", "name": name, "namespace": namespace}

    def delete(self, namespace, name):
        path = self.directory(namespace).joinpath(*self.parts(name), "SKILL.md")
        if not path.is_file():
            return False
        with file_lock("skills"):
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        return True
