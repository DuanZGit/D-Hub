from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
from typing import Any

import httpx

from .config import merged_json


class McpRouter:
    """Resolve tiered MCP configs and proxy JSON-RPC calls."""

    def __init__(self, cache_ttl: float = 120):
        self.cache_ttl = cache_ttl
        self.cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def configs(self, agent_id: str | None = None, project: str | None = None):
        return merged_json("mcp", agent_id, project)[0]

    async def list_tools(self, agent_id=None, project=None):
        tools: list[dict[str, Any]] = []
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
                item["server"] = server_id
                tools.append(item)
        return {"tools": tools}

    async def call(self, name, arguments=None, agent_id=None, project=None):
        parts = name.split("__", 2)
        if len(parts) != 3 or parts[0] != "rmcp":
            raise ValueError("MCP tool must use rmcp__server__tool name")
        server_id, tool_name = parts[1:]
        config = self.configs(agent_id, project).get(server_id)
        if not config:
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
        async with httpx.AsyncClient(
            timeout=float(config.get("timeout", 30))
        ) as client:
            response = await client.post(config["url"], json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data.get("result", data)

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
