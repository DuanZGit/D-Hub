from __future__ import annotations

import re
import shutil
import subprocess
import threading

from whoosh import index
from whoosh.analysis import NgramAnalyzer
from whoosh.fields import ID, NUMERIC, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup, QueryParserError

from .config import ROOT, mutation_lock, namespace_parts, now


class WikiStore:
    def __init__(self):
        self.root = ROOT / "wiki"
        self.index_root = ROOT / "data" / "wiki-index"
        self.lock = threading.RLock()
        self._init_git()

    def _init_git(self):
        if (self.root / ".git").exists():
            return
        try:
            subprocess.run(["git", "init", "-q", str(self.root)], check=True)
            subprocess.run(
                ["git", "-C", str(self.root), "config", "user.name", "d-hub"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(self.root), "config", "user.email", "dhub@localhost"],
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def title_name(title):
        title = str(title or "").strip()
        if (
            not title
            or title in (".", "..")
            or "/" in title
            or "\\" in title
            or "\x00" in title
            or any(ord(char) < 32 for char in title)
        ):
            raise ValueError("invalid wiki title")
        return title.removesuffix(".md")

    def directory(self, namespace):
        tier, ident = namespace_parts(namespace)
        return self.root / tier if tier == "global" else self.root / tier / ident

    def path(self, namespace, title):
        return self.directory(namespace) / (self.title_name(title) + ".md")

    def put(self, namespace, title, content, author="api"):
        path = self.path(namespace, title)
        with self.lock, mutation_lock("wiki"):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name("." + path.name + ".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
            self._commit(
                path, f"wiki: update {namespace}/{self.title_name(title)} by {author}"
            )
            self._upsert_index(
                namespace, self.title_name(title), content, path.stat().st_mtime
            )
        return {
            "status": "ok",
            "path": f"/wiki/{namespace}/{path.name}",
            "updated_at": now(),
        }

    def get(self, namespace, title):
        path = self.path(namespace, title)
        if not path.is_file():
            raise FileNotFoundError(title)
        return {
            "namespace": namespace,
            "title": self.title_name(title),
            "content": path.read_text(encoding="utf-8"),
            "updated_at": path.stat().st_mtime,
        }

    def delete(self, namespace, title):
        path = self.path(namespace, title)
        if not path.is_file():
            return False
        with self.lock, mutation_lock("wiki"):
            path.unlink()
            self._commit(path, f"wiki: delete {namespace}/{self.title_name(title)}")
            self._delete_index(namespace, self.title_name(title))
        return True

    def list(self, namespace):
        directory = self.directory(namespace)
        return (
            [
                {
                    "title": path.stem,
                    "namespace": namespace,
                    "size": path.stat().st_size,
                    "updated_at": path.stat().st_mtime,
                }
                for path in sorted(directory.glob("*.md"))
            ]
            if directory.exists()
            else []
        )

    def search(self, namespace, query, limit=20):
        if not query.strip():
            return self.list(namespace)[:limit]
        self._ensure_index(namespace)
        parser = MultifieldParser(
            ["title", "content"], schema=self._index(namespace).schema, group=OrGroup
        )
        try:
            parsed = parser.parse(query)
        except QueryParserError:
            parsed = parser.parse(
                " OR ".join(re.findall(r"[\w\u4e00-\u9fff-]+", query))
            )
        with self._index(namespace).searcher() as searcher:
            hits = searcher.search(parsed, limit=limit)
            result = []
            for hit in hits:
                content = hit["content"]
                result.append(
                    {
                        "title": hit["title"],
                        "namespace": namespace,
                        "size": len(content.encode()),
                        "updated_at": hit["updated_at"],
                        "score": hit.score,
                        "context": hit.highlights("content", top=2) or content[:240],
                    }
                )
            return result

    def rebuild_index(self, namespace):
        with self.lock, mutation_lock("wiki"):
            return self._rebuild_index(namespace)

    def _rebuild_index(self, namespace):
        directory = self._index_dir(namespace)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
        analyzer = NgramAnalyzer(minsize=1, maxsize=4)
        schema = Schema(
            key=ID(stored=True, unique=True),
            namespace=ID(stored=True),
            title=TEXT(stored=True, analyzer=analyzer),
            content=TEXT(stored=True, analyzer=analyzer),
            updated_at=NUMERIC(stored=True, sortable=True),
        )
        ix = index.create_in(directory, schema)
        writer = ix.writer()
        for page in self.list(namespace):
            content = self.get(namespace, page["title"])["content"]
            writer.add_document(
                key=f"{namespace}/{page['title']}",
                namespace=namespace,
                title=page["title"],
                content=content,
                updated_at=page["updated_at"],
            )
        writer.commit()
        return {"status": "ok", "pages": len(self.list(namespace))}

    def history(self, namespace, title, limit=30):
        relative = str(self.path(namespace, title).relative_to(self.root))
        command = [
            "git",
            "-C",
            str(self.root),
            "log",
            f"-{limit}",
            "--format=%H%x09%aI%x09%s",
            "--",
            relative,
        ]
        try:
            output = subprocess.run(
                command, capture_output=True, text=True, check=True
            ).stdout
            return [
                {"commit": commit, "created_at": created, "message": message}
                for line in output.splitlines()
                for commit, created, message in [line.split("\t", 2)]
            ]
        except (OSError, subprocess.SubprocessError, ValueError):
            return []

    def _index_dir(self, namespace):
        tier, ident = namespace_parts(namespace)
        return self.index_root / (tier if tier == "global" else f"{tier}-{ident}")

    def _index(self, namespace):
        return index.open_dir(self._index_dir(namespace))

    def _ensure_index(self, namespace):
        directory = self._index_dir(namespace)
        if not index.exists_in(directory):
            self._rebuild_index(namespace)

    def _upsert_index(self, namespace, title, content, updated_at):
        self._ensure_index(namespace)
        writer = self._index(namespace).writer()
        writer.update_document(
            key=f"{namespace}/{title}",
            namespace=namespace,
            title=title,
            content=content,
            updated_at=updated_at,
        )
        writer.commit()

    def _delete_index(self, namespace, title):
        directory = self._index_dir(namespace)
        if index.exists_in(directory):
            writer = self._index(namespace).writer()
            writer.delete_by_term("key", f"{namespace}/{title}")
            writer.commit()

    def _commit(self, path, message):
        try:
            relative = str(path.relative_to(self.root))
            subprocess.run(
                ["git", "-C", str(self.root), "add", "-A", "--", relative],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(self.root), "commit", "-q", "-m", message],
                check=False,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError):
            pass
