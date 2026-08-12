from __future__ import annotations

import json
from typing import Any


class NativeMcpTools:
    """Expose d-hub stores as MCP tools bound to the client session context."""

    def __init__(self, memory, wiki, skills, files, sessions=None, max_read_bytes: int = 262_144):
        self.memory = memory
        self.wiki = wiki
        self.skills = skills
        self.files = files
        self.sessions = sessions
        self.max_read_bytes = max_read_bytes
        self._tools = self._tool_definitions()

    def list_tools(self):
        return [dict(tool) for tool in self._tools]

    def call(self, name, arguments, agent_id=None, project=None, allow_global=False):
        arguments = arguments or {}
        scope = arguments.get("scope", "project" if project else "agent")
        if scope == "global" and not allow_global:
            raise PermissionError("global scope requires the d-hub admin key")
        namespace = self._namespace(scope, agent_id, project)
        if name == "dhub_memory_search":
            memory_agent = self._memory_agent(scope, agent_id)
            result = self.memory.search(
                namespace,
                memory_agent,
                str(arguments.get("query", "")),
                self._limit(arguments, 10, 200),
            )
        elif name == "dhub_memory_add":
            content = self._required(arguments, "content")
            memory_agent = self._memory_agent(scope, agent_id)
            result = self.memory.add(
                namespace,
                memory_agent,
                content,
                arguments.get("metadata") or {},
                bool(arguments.get("infer", True)),
            )
        elif name == "dhub_wiki_search":
            result = {
                "results": self.wiki.search(
                    namespace,
                    str(arguments.get("query", "")),
                    self._limit(arguments, 20, 100),
                )
            }
        elif name == "dhub_wiki_get":
            try:
                result = self.wiki.get(namespace, self._required(arguments, "title"))
            except FileNotFoundError as exc:
                raise KeyError("Wiki page not found") from exc
        elif name == "dhub_wiki_put":
            result = self.wiki.put(
                namespace,
                self._required(arguments, "title"),
                self._required(arguments, "content"),
                f"mcp:{agent_id or 'anonymous'}",
            )
        elif name == "dhub_skills_list":
            result = {
                "skills": self.skills.list(
                    agent_id if scope != "global" else None,
                    project if scope == "project" else None,
                )
            }
        elif name == "dhub_skill_get":
            try:
                result = self.skills.get(
                    self._required(arguments, "name"),
                    agent_id if scope != "global" else None,
                    project if scope == "project" else None,
                )
            except FileNotFoundError as exc:
                raise KeyError("Skill not found") from exc
        elif name == "dhub_files_list":
            result = {"files": self.files.list(namespace)}
        elif name == "dhub_file_read":
            file_name = self._required(arguments, "file")
            try:
                path = self.files.read(namespace, file_name)
            except FileNotFoundError as exc:
                raise KeyError("File not found") from exc
            if path.stat().st_size > self.max_read_bytes:
                raise ValueError(
                    f"file exceeds MCP read limit of {self.max_read_bytes} bytes"
                )
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("MCP can only read UTF-8 text files") from exc
            result = {"file": file_name, "content": content}
        elif name == "dhub_session_create":
            result = self.sessions.create(
                namespace,
                title=arguments.get("title"),
                cwd=arguments.get("cwd"),
                agent_id=agent_id,
                project=project,
                metadata=arguments.get("metadata") or {},
            )
        elif name == "dhub_session_list":
            result = {
                "sessions": self.sessions.list(
                    namespace, self._limit(arguments, 100, 500)
                )
            }
        elif name == "dhub_session_get":
            try:
                result = self.sessions.get(
                    namespace, self._required(arguments, "session_id")
                )
            except FileNotFoundError as exc:
                raise KeyError("Session not found") from exc
        elif name == "dhub_session_append":
            try:
                result = self.sessions.append(
                    namespace,
                    self._required(arguments, "session_id"),
                    arguments.get("messages") or [],
                    arguments.get("metadata"),
                )
            except FileNotFoundError as exc:
                raise KeyError("Session not found") from exc
        elif name == "dhub_session_search":
            result = {
                "results": self.sessions.search(
                    namespace,
                    str(arguments.get("query", "")),
                    self._limit(arguments, 20, 100),
                )
            }
        else:
            raise KeyError("MCP tool not found")
        return self._result(result)

    @staticmethod
    def _required(arguments, name):
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        return value

    @staticmethod
    def _limit(arguments, default, maximum):
        value = int(arguments.get("limit", default))
        if value < 1 or value > maximum:
            raise ValueError(f"limit must be between 1 and {maximum}")
        return value

    @staticmethod
    def _namespace(scope, agent_id, project):
        if scope == "global":
            return "global"
        if scope == "agent":
            if not agent_id:
                raise ValueError("agent scope requires agent_id in the MCP URL")
            return f"agents/{agent_id}"
        if scope == "project":
            if not project:
                raise ValueError("project scope requires project in the MCP URL")
            return f"projects/{project}"
        raise ValueError("scope must be global, agent, or project")

    @staticmethod
    def _memory_agent(scope, agent_id):
        if scope in ("global", "project"):
            return "shared"
        if not agent_id:
            raise ValueError("memory operation requires agent_id in the MCP URL")
        return agent_id

    @staticmethod
    def _result(value):
        text = json.dumps(value, ensure_ascii=False, indent=2)
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": value,
        }

    @staticmethod
    def _tool_definitions() -> list[dict[str, Any]]:
        scope = {
            "type": "string",
            "enum": ["global", "agent", "project"],
            "description": "Asset scope. Defaults to project when configured, else agent.",
        }

        def schema(properties, required=()):
            return {
                "type": "object",
                "properties": {"scope": scope, **properties},
                "required": list(required),
                "additionalProperties": False,
            }

        return [
            {
                "name": "dhub_memory_search",
                "description": "Search d-hub memory visible in one scope.",
                "inputSchema": schema(
                    {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    }
                ),
            },
            {
                "name": "dhub_memory_add",
                "description": "Store a durable fact, decision, or observation in d-hub.",
                "inputSchema": schema(
                    {
                        "content": {"type": "string", "minLength": 1},
                        "metadata": {"type": "object"},
                        "infer": {"type": "boolean", "default": True},
                    },
                    ("content",),
                ),
            },
            {
                "name": "dhub_wiki_search",
                "description": "Search durable Markdown knowledge in d-hub Wiki.",
                "inputSchema": schema(
                    {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    }
                ),
            },
            {
                "name": "dhub_wiki_get",
                "description": "Read a d-hub Wiki page.",
                "inputSchema": schema(
                    {"title": {"type": "string", "minLength": 1}}, ("title",)
                ),
            },
            {
                "name": "dhub_wiki_put",
                "description": "Create or replace a durable d-hub Wiki page.",
                "inputSchema": schema(
                    {
                        "title": {"type": "string", "minLength": 1},
                        "content": {"type": "string", "minLength": 1},
                    },
                    ("title", "content"),
                ),
            },
            {
                "name": "dhub_skills_list",
                "description": "List merged d-hub skills visible to this agent/project.",
                "inputSchema": schema({}),
            },
            {
                "name": "dhub_skill_get",
                "description": "Read one merged d-hub SKILL.md.",
                "inputSchema": schema(
                    {"name": {"type": "string", "minLength": 1}}, ("name",)
                ),
            },
            {
                "name": "dhub_files_list",
                "description": "List files stored in one d-hub scope.",
                "inputSchema": schema({}),
            },
            {
                "name": "dhub_file_read",
                "description": "Read a UTF-8 text file stored in d-hub.",
                "inputSchema": schema(
                    {"file": {"type": "string", "minLength": 1}}, ("file",)
                ),
            },
            {
                "name": "dhub_session_create",
                "description": "Create a new session transcript in d-hub (a conversation log).",
                "inputSchema": schema(
                    {
                        "title": {"type": "string"},
                        "cwd": {"type": "string"},
                        "metadata": {"type": "object"},
                    }
                ),
            },
            {
                "name": "dhub_session_list",
                "description": "List session transcripts in one d-hub scope.",
                "inputSchema": schema(
                    {"limit": {"type": "integer", "minimum": 1, "maximum": 500}}
                ),
            },
            {
                "name": "dhub_session_get",
                "description": "Read a full session transcript including its messages.",
                "inputSchema": schema(
                    {"session_id": {"type": "string", "minLength": 1}},
                    ("session_id",),
                ),
            },
            {
                "name": "dhub_session_append",
                "description": "Append message events to a session transcript.",
                "inputSchema": schema(
                    {
                        "session_id": {"type": "string", "minLength": 1},
                        "messages": {"type": "array"},
                        "metadata": {"type": "object"},
                    },
                    ("session_id", "messages"),
                ),
            },
            {
                "name": "dhub_session_search",
                "description": "Search session transcripts and messages for a query.",
                "inputSchema": schema(
                    {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    }
                ),
            },
        ]
