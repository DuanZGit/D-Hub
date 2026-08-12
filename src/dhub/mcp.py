from __future__ import annotations

import asyncio
import json
import os
import shlex
import threading
import time
from typing import Any

import httpx

from .config import VERSION, merged_json


class McpRouter:
    """Resolve tiered MCP configs and proxy JSON-RPC calls."""

    def __init__(self, cache_ttl: float = 120, session_ttl: float = 3600, native=None):
        self.cache_ttl = cache_ttl
        self.session_ttl = session_ttl
        self.cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self.http_sessions: dict[str, tuple[float, str | None]] = {}
        self.http_session_locks: dict[str, asyncio.Lock] = {}
        self._session_generation = 0
        self._session_state_lock = threading.Lock()
        self.native = native

    def clear(self):
        self.cache.clear()
        with self._session_state_lock:
            self._session_generation += 1
            self.http_sessions.clear()
            self.http_session_locks = {
                key: lock
                for key, lock in self.http_session_locks.items()
                if lock.locked()
            }

    def _prune_http_sessions(self):
        cutoff = time.monotonic() - self.session_ttl
        with self._session_state_lock:
            expired = [
                key
                for key, (last_used, _) in self.http_sessions.items()
                if last_used < cutoff
            ]
            for key in expired:
                self.http_sessions.pop(key, None)
            self.http_session_locks = {
                key: lock
                for key, lock in self.http_session_locks.items()
                if lock.locked() or key in self.http_sessions
            }

    def configs(self, agent_id: str | None = None, project: str | None = None):
        return merged_json("mcp", agent_id, project)[0]

    async def list_tools(self, agent_id=None, project=None):
        tools: list[dict[str, Any]] = (
            self.native.list_tools() if self.native is not None else []
        )
        for server_id, config in self.configs(agent_id, project).items():
            if config.get("enabled", True) is False:
                continue
            declared = config.get("tools") or []
            if declared:
                remote_tools = declared
            else:
                cache_key = json.dumps([server_id, config], sort_keys=True)
                cached = self.cache.get(cache_key)
                if cached and cached[0] > time.monotonic():
                    remote_tools = cached[1]
                else:
                    try:
                        response = await self._rpc(config, "tools/list", {})
                        remote_tools = response.get("tools", [])
                        self.cache[cache_key] = (
                            time.monotonic() + self.cache_ttl,
                            remote_tools,
                        )
                    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                        tools.append(
                            {
                                "name": f"rmcp__{server_id}__unavailable",
                                "description": str(exc),
                                "server": server_id,
                                "isError": True,
                            }
                        )
                        continue
            for tool in remote_tools:
                item = dict(tool)
                raw_name = item.get("name", "")
                item["name"] = (
                    raw_name
                    if raw_name.startswith("rmcp__")
                    else f"rmcp__{server_id}__{raw_name}"
                )
                item.setdefault("inputSchema", {"type": "object", "properties": {}})
                item["server"] = server_id
                tools.append(item)
        return {"tools": tools}

    async def call(
        self,
        name,
        arguments=None,
        agent_id=None,
        project=None,
        allow_global=True,
    ):
        if name.startswith("dhub_"):
            if self.native is None:
                raise KeyError("MCP tool not found")
            return await asyncio.to_thread(
                self.native.call,
                name,
                arguments,
                agent_id,
                project,
                allow_global,
            )
        parts = name.split("__", 2)
        if len(parts) != 3 or parts[0] != "rmcp":
            raise ValueError("MCP tool must use rmcp__server__tool name")
        server_id, tool_name = parts[1:]
        config = self.configs(agent_id, project).get(server_id)
        if not config or config.get("enabled", True) is False:
            raise KeyError("MCP server not found")
        return await self._rpc(
            config, "tools/call", {"name": tool_name, "arguments": arguments or {}}
        )

    async def _rpc(self, config, method, params):
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1_000_000_000,
            "method": method,
            "params": params,
        }
        headers = self._headers(config.get("headers") or {})
        if config.get("transport", "http") == "stdio":
            return await self._stdio_rpc(config, payload)
        data = await self._http_rpc(config, payload, headers)
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data.get("result", data)

    async def _http_rpc(self, config, payload, headers):
        url = config.get("url")
        if not url:
            raise ValueError("HTTP MCP config requires url")
        session_key = json.dumps([url, headers], sort_keys=True)
        self._prune_http_sessions()
        with self._session_state_lock:
            generation = self._session_generation
            lock = self.http_session_locks.setdefault(session_key, asyncio.Lock())
        async with (
            lock,
            httpx.AsyncClient(timeout=float(config.get("timeout", 30))) as client,
        ):
            with self._session_state_lock:
                existing = self.http_sessions.get(session_key)
            session_id = existing[1] if existing else None
            if existing is None:
                session_id = await self._initialize_http_session(client, url, headers)
            response = await self._http_post(
                client,
                url,
                payload,
                headers,
                session_id,
            )
            if response.status_code == 404:
                with self._session_state_lock:
                    self.http_sessions.pop(session_key, None)
                session_id = await self._initialize_http_session(client, url, headers)
                response = await self._http_post(
                    client,
                    url,
                    payload,
                    headers,
                    session_id,
                )
            response.raise_for_status()
            with self._session_state_lock:
                if generation == self._session_generation:
                    self.http_sessions[session_key] = (
                        time.monotonic(),
                        session_id,
                    )
            return self._decode_http_response(response, payload.get("id"))

    async def _initialize_http_session(self, client, url, headers):
        initialize = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1_000_000_000,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "d-hub", "version": VERSION},
            },
        }
        response = await self._http_post(client, url, initialize, headers, None)
        response.raise_for_status()
        data = self._decode_http_response(response, initialize["id"])
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        session_id = response.headers.get("Mcp-Session-Id")
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        notified = await self._http_post(client, url, notification, headers, session_id)
        notified.raise_for_status()
        return session_id

    @staticmethod
    async def _http_post(client, url, payload, headers, session_id):
        request_headers = {
            "Accept": "application/json, text/event-stream",
            **headers,
        }
        if session_id:
            request_headers["Mcp-Session-Id"] = session_id
        return await client.post(url, json=payload, headers=request_headers)

    @staticmethod
    def _decode_http_response(response, request_id):
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" not in content_type:
            return response.json()
        events = []
        data_lines = []
        for line in response.text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif not line and data_lines:
                events.append(json.loads("\n".join(data_lines)))
                data_lines = []
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
        for event in events:
            if event.get("id") == request_id:
                return event
        if events:
            return events[-1]
        raise ValueError("HTTP MCP returned no JSON-RPC response")

    @staticmethod
    def _headers(headers):
        resolved = {}
        for key, value in headers.items():
            if isinstance(value, str) and value.startswith("$"):
                env_name = value[1:]
                if env_name not in os.environ:
                    raise ValueError(f"missing environment variable: {env_name}")
                value = os.environ[env_name]
            resolved[key] = value
        return resolved

    @staticmethod
    async def _stdio_rpc(config, payload):
        command = config.get("command")
        if not command:
            raise ValueError("stdio MCP config requires command")
        process = await asyncio.create_subprocess_exec(
            *shlex.split(command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate((json.dumps(payload) + "\n").encode()),
                timeout=float(config.get("timeout", 30)),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("stdio MCP request timed out") from None
        if process.returncode not in (0, None) and not stdout:
            raise RuntimeError(stderr.decode(errors="replace").strip())
        line = stdout.splitlines()[0] if stdout else b""
        if not line:
            raise RuntimeError("stdio MCP returned no JSON-RPC response")
        data = json.loads(line)
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data.get("result", data)
