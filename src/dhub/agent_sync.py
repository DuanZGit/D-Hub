from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class HubClient:
    def __init__(self, base_url, api_key=None, timeout=60):
        self.base_url = str(base_url).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def json(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        return self._request(method, path, body, headers)

    def upload(self, path, field_name, file_name, data, content_type):
        boundary = "dhub-" + uuid.uuid4().hex
        disposition = (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{Path(file_name).name}"\r\n'
        ).encode()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                disposition,
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                data,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        return self._request(
            "POST",
            path,
            body,
            {
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

    def _request(self, method, path, body, headers):
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"d-hub returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach d-hub: {exc.reason}") from exc
        return json.loads(raw) if raw else {}


class AgentAssetSync:
    """Synchronize one declarative agent manifest through the d-hub REST interface."""

    def __init__(self, manifest_path, client, dry_run=False):
        self.manifest_path = Path(manifest_path).resolve()
        self.base_dir = self.manifest_path.parent
        self.client = client
        self.dry_run = dry_run
        self.agent_id = None
        self.projects = set()
        self._text_assets = {}
        self._binary_assets = {}

    def run(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        agent_id = self._required(manifest, "agent_id")
        self.agent_id = agent_id
        projects = manifest.get("projects") or []
        if not isinstance(projects, list) or not all(
            isinstance(item, str) and item for item in projects
        ):
            raise ValueError("projects must be a list of non-empty strings")
        self._safe_part(agent_id, "agent_id")
        for project in projects:
            self._safe_part(project, "project")
        self.projects = set(projects)
        variables = {
            "agent_id": agent_id,
            "project": projects[0] if projects else "",
        }
        manifest = self._expand(manifest, variables)
        assets = manifest.get("assets") or {}
        if not isinstance(assets, dict):
            raise TypeError("assets must be an object")
        original_dry_run = self.dry_run
        self.dry_run = True
        validation_actions = []
        self._apply(manifest, assets, validation_actions)
        if original_dry_run:
            return {"status": "dry-run", "actions": validation_actions}
        self.dry_run = False
        actions = []
        registration = self._apply(manifest, assets, actions)
        result = {
            "status": "ok",
            "actions": actions,
            "warning": "remote writes are ordered but not transactional",
        }
        if registration.get("api_key"):
            result["agent_api_key"] = registration["api_key"]
        return result

    def _apply(self, manifest, assets, actions):
        registration = self._sync_registration(manifest, actions)
        for item in self._items(assets, "mcp"):
            self._sync_mcp(item, actions)
        for item in self._items(assets, "skills"):
            self._sync_skill(item, actions)
        for item in self._items(assets, "wiki"):
            self._sync_wiki(item, actions)
        for item in self._items(assets, "prompts"):
            self._sync_prompt(item, actions)
        for item in self._items(assets, "files"):
            self._sync_file(item, actions)
        return registration

    def _sync_registration(self, manifest, actions):
        payload = {
            "agent_id": manifest["agent_id"],
            "host": manifest.get("host"),
            "url": manifest.get("callback_url"),
            "tools": manifest.get("tools")
            or [
                "memory",
                "wiki",
                "mcp",
                "skills",
                "files",
            ],
            "projects": manifest.get("projects") or [],
            "enabled": manifest.get("enabled", True),
        }
        return self._json_action("register", "POST", "/register", payload, actions)

    def _sync_mcp(self, item, actions):
        namespace = self._namespace(item)
        server_id = self._safe_part(self._required(item, "server_id"), "server_id")
        config = self._json_source(item)
        self._json_action(
            f"mcp:{namespace}/{server_id}",
            "PUT",
            "/mcp/configs",
            {"namespace": namespace, "server_id": server_id, "config": config},
            actions,
        )

    def _sync_skill(self, item, actions):
        namespace = self._namespace(item)
        name = self._required(item, "name")
        for part in name.strip("/").split("/"):
            self._safe_part(part, "skill name")
        content = self._text_source(item)
        self._json_action(
            f"skill:{namespace}/{name}",
            "PUT",
            "/skills",
            {"namespace": namespace, "name": name, "content": content},
            actions,
        )

    def _sync_wiki(self, item, actions):
        namespace = self._namespace(item)
        title = self._required(item, "title")
        if title in (".", "..") or any(char in title for char in "/\\\x00\r\n"):
            raise ValueError("wiki title must be a plain page name")
        content = self._text_source(item)
        self._json_action(
            f"wiki:{namespace}/{title}",
            "POST",
            "/wiki/page",
            {
                "namespace": namespace,
                "title": title,
                "content": content,
                "author": f"agent-sync:{self._agent_id}",
            },
            actions,
        )

    def _sync_prompt(self, item, actions):
        target = item.get("target", "skill")
        if target == "skill":
            mapped = {**item, "name": item.get("name") or item.get("title")}
            self._sync_skill(mapped, actions)
        elif target == "wiki":
            mapped = {**item, "title": item.get("title") or item.get("name")}
            self._sync_wiki(mapped, actions)
        else:
            raise ValueError("prompt target must be skill or wiki")

    def _sync_file(self, item, actions):
        namespace = self._namespace(item)
        source_name = self._required(item, "path")
        source = self._source_path(source_name)
        data = self._read_bytes(source_name)
        target = item.get("target") or source.name
        if (
            target != Path(target).name
            or "/" in target
            or "\\" in target
            or any(char in target for char in '\r\n"')
        ):
            raise ValueError("file target must be a plain file name")
        label = f"file:{namespace}/{target}"
        if not self.dry_run:
            query = urllib.parse.urlencode({"namespace": namespace})
            content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
            self.client.upload(
                f"/files/upload?{query}",
                "file",
                target,
                data,
                content_type,
            )
        actions.append(label)

    def _json_action(self, label, method, path, payload, actions):
        result = {}
        if not self.dry_run:
            result = self.client.json(method, path, payload)
        actions.append(label)
        return result

    def _json_source(self, item):
        if "config" in item:
            value = item["config"]
        else:
            value = json.loads(self._read_text(self._required(item, "path")))
        if not isinstance(value, dict):
            raise TypeError("MCP config must be a JSON object")
        return value

    def _text_source(self, item):
        if "content" in item:
            value = item["content"]
            if not isinstance(value, str):
                raise ValueError("content must be a string")
            return value
        return self._read_text(self._required(item, "path"))

    def _source_path(self, value):
        path = (self.base_dir / value).resolve()
        if self.base_dir != path and self.base_dir not in path.parents:
            raise ValueError("asset path must stay inside the manifest directory")
        if not path.is_file():
            raise ValueError(f"asset file not found: {value}")
        return path

    def _read_text(self, value):
        if value not in self._text_assets:
            self._text_assets[value] = self._source_path(value).read_text(
                encoding="utf-8"
            )
        return self._text_assets[value]

    def _read_bytes(self, value):
        if value not in self._binary_assets:
            self._binary_assets[value] = self._source_path(value).read_bytes()
        return self._binary_assets[value]

    def _namespace(self, item):
        namespace = self._required(item, "namespace")
        parts = namespace.strip("/").split("/")
        if parts == ["global"]:
            return namespace
        if len(parts) == 2 and parts[0] in ("agents", "projects"):
            self._safe_part(parts[1], "namespace")
            if parts[0] == "agents" and parts[1] != self.agent_id:
                raise ValueError("agent namespace must match manifest agent_id")
            if parts[0] == "projects" and parts[1] not in self.projects:
                raise ValueError("project namespace must be declared in projects")
            return namespace
        raise ValueError("namespace must be global, agents/<id>, or projects/<id>")

    @property
    def _agent_id(self):
        return self.agent_id

    @staticmethod
    def _required(value, name):
        result = value.get(name) if isinstance(value, dict) else None
        if not isinstance(result, str) or not result.strip():
            raise ValueError(f"{name} is required")
        return result

    @staticmethod
    def _safe_part(value, label):
        if value in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError(f"invalid {label}: {value}")
        return value

    @staticmethod
    def _items(assets, name):
        result = assets.get(name) or []
        if not isinstance(result, list) or not all(isinstance(x, dict) for x in result):
            raise ValueError(f"assets.{name} must be a list of objects")
        return result

    @staticmethod
    def _expand(value, variables):
        if isinstance(value, str):
            return value.replace("{agent_id}", variables["agent_id"]).replace(
                "{project}", variables["project"]
            )
        if isinstance(value, list):
            return [AgentAssetSync._expand(item, variables) for item in value]
        if isinstance(value, dict):
            return {
                key: AgentAssetSync._expand(item, variables)
                for key, item in value.items()
            }
        return value


def build_parser():
    parser = argparse.ArgumentParser(
        description="Register an agent and synchronize its declared assets to d-hub."
    )
    parser.add_argument("manifest", nargs="?", default="dhub-agent.json")
    parser.add_argument(
        "--url", default=os.getenv("DHUB_URL", "http://127.0.0.1:10101")
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("DHUB_ADMIN_KEY") or os.getenv("DHUB_API_KEY"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = AgentAssetSync(
            args.manifest,
            HubClient(args.url, args.api_key),
            dry_run=args.dry_run,
        ).run()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"dhub-agent-sync: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
