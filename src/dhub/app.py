from __future__ import annotations

import hmac
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field

from .config import (
    ROOT,
    VERSION,
    atomic_json,
    ensure_layout,
    mutation_lock,
    namespace_parts,
    safe_part,
)
from .files import NamespaceFiles, SkillStore
from .mcp import McpRouter
from .memory import MemoryStore
from .native_mcp import NativeMcpTools
from .services import AppState, SemanticSync, backup, restore
from .wiki import WikiStore

ensure_layout()
state, memory, wiki = AppState(), MemoryStore(), WikiStore()
files, skills = NamespaceFiles(), SkillStore()
mcp = McpRouter(native=NativeMcpTools(memory, wiki, skills, files))
sync = SemanticSync(memory, wiki)
app = FastAPI(
    title="d-hub", version=VERSION, description="Multi-agent coordination layer"
)
MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_TTL_SECONDS = int(os.getenv("DHUB_MCP_SESSION_TTL_SECONDS", "86400"))
mcp_sessions: dict[str, tuple[float, str | None, str | None, bool]] = {}
mcp_sessions_lock = threading.Lock()
ADMIN_KEY = os.getenv("DHUB_ADMIN_KEY") or os.getenv("DHUB_API_KEY")


class RegisterIn(BaseModel):
    agent_id: str
    host: str | None = None
    url: str | None = None
    tools: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    enabled: bool = True


class MemoryAdd(BaseModel):
    namespace: str = "global"
    agent_id: str = "shared"
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    infer: bool = True


class MemorySearch(BaseModel):
    namespace: str = "global"
    agent_id: str = "shared"
    query: str = ""
    limit: int = Field(10, ge=1, le=200)


class WikiPut(BaseModel):
    namespace: str = "global"
    title: str
    content: str
    author: str = "api"


class SkillPut(BaseModel):
    namespace: str = "global"
    name: str
    content: str


class McpList(BaseModel):
    agent_id: str | None = None
    project: str | None = None


class McpCall(McpList):
    name: str
    arguments: dict = Field(default_factory=dict)


class McpConfigPut(BaseModel):
    namespace: str = "global"
    server_id: str
    config: dict


class AgentCall(BaseModel):
    method: str
    params: dict = Field(default_factory=dict)


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    state.requests += 1
    public = (
        request.url.path in {"/", "/health", "/docs", "/redoc", "/openapi.json"}
        or request.url.path == "/ui"
        or request.url.path.startswith("/ui/")
    )
    authorization = request.headers.get("Authorization", "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    supplied_key = bearer or request.headers.get("X-API-Key", "")
    mcp_request = request.url.path == "/mcp"
    if (
        ADMIN_KEY
        and not public
        and not mcp_request
        and not hmac.compare_digest(supplied_key, ADMIN_KEY)
    ):
        state.audit.write(
            "http",
            False,
            method=request.method,
            path=request.url.path,
            status=401,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "valid API key required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        response = await call_next(request)
        if request.method != "GET":
            state.audit.write(
                "http",
                response.status_code < 400,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
        return response
    except Exception as exc:
        state.audit.write(
            "http",
            False,
            method=request.method,
            path=request.url.path,
            error=type(exc).__name__,
        )
        raise


@app.exception_handler(ValueError)
async def value_error(_, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui")


@app.get("/health")
def health():
    return {
        **state.health(),
        "memory_backend": memory.backend,
        "memory_error": memory.error,
        "authentication": "enabled" if ADMIN_KEY else "disabled",
    }


@app.post("/register")
def register(body: RegisterIn):
    return {"status": "ok", **state.registry.register(body.model_dump())}


@app.get("/agents")
def agents():
    return {
        "agents": [state.registry.public(item) for item in state.registry.all().values()]
    }


@app.delete("/agents/{agent_id}")
def agent_delete(agent_id: str):
    if not state.registry.delete(agent_id):
        raise HTTPException(404, "agent not found")
    return {"status": "ok"}


@app.post("/mcp/tools/list")
async def mcp_list(body: McpList):
    return await mcp.list_tools(body.agent_id, body.project)


@app.post("/mcp/tools/call")
async def mcp_call(body: McpCall):
    try:
        return {
            "result": await mcp.call(
                body.name, body.arguments, body.agent_id, body.project
            )
        }
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        raise HTTPException(502, f"MCP upstream failed: {exc}") from exc


def mcp_response(request_id, *, result=None, error=None, headers=None):
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        payload["result"] = result if result is not None else {}
    else:
        payload["error"] = error
    return JSONResponse(payload, headers=headers)


def mcp_session_get(session_id: str | None):
    now = time.monotonic()
    with mcp_sessions_lock:
        expired = [
            existing
            for existing, (last_seen, _, _, _) in mcp_sessions.items()
            if now - last_seen > MCP_SESSION_TTL_SECONDS
        ]
        for existing in expired:
            mcp_sessions.pop(existing, None)
        if not session_id or session_id not in mcp_sessions:
            return None
        _, agent_id, project, is_admin = mcp_sessions[session_id]
        if not is_admin:
            try:
                agent = state.registry.get(agent_id)
            except KeyError:
                mcp_sessions.pop(session_id, None)
                return None
            if not state.registry.context_allowed(agent, project):
                mcp_sessions.pop(session_id, None)
                return None
        mcp_sessions[session_id] = (now, agent_id, project, is_admin)
        return agent_id, project, is_admin


@app.post("/mcp", include_in_schema=False)
async def streamable_mcp(
    request: Request, agent_id: str | None = None, project: str | None = None
):
    try:
        payload = await request.json()
    except ValueError:
        return mcp_response(
            None, error={"code": -32700, "message": "Parse error"}, headers=None
        )
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return mcp_response(None, error={"code": -32600, "message": "Invalid Request"})

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        return mcp_response(
            request_id, error={"code": -32600, "message": "Invalid Request"}
        )
    if method == "initialize":
        if request_id is None:
            return mcp_response(
                None, error={"code": -32600, "message": "Invalid Request"}
            )
        authorization = request.headers.get("Authorization", "")
        bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        supplied_key = bearer or request.headers.get("X-API-Key", "")
        is_admin = bool(ADMIN_KEY and hmac.compare_digest(supplied_key, ADMIN_KEY))
        if ADMIN_KEY and not is_admin and not state.registry.authenticate(
            agent_id, supplied_key, project
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "valid agent or admin key required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        session_id = uuid.uuid4().hex
        with mcp_sessions_lock:
            mcp_sessions[session_id] = (
                time.monotonic(),
                agent_id,
                project,
                is_admin,
            )
        requested_version = params.get("protocolVersion")
        protocol_version = (
            MCP_PROTOCOL_VERSION
            if requested_version != MCP_PROTOCOL_VERSION
            else requested_version
        )
        return mcp_response(
            request_id,
            result={
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "d-hub", "version": VERSION},
            },
            headers={"Mcp-Session-Id": session_id},
        )

    session_id = request.headers.get("Mcp-Session-Id")
    context = mcp_session_get(session_id)
    if context is None:
        if request_id is None:
            return Response(status_code=404)
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": "Invalid or missing MCP session"},
            },
            status_code=404,
        )
    agent_id, project, is_admin = context
    if request_id is None:
        return Response(status_code=202)
    try:
        if method == "ping":
            result = {}
        elif method == "tools/list":
            result = await mcp.list_tools(agent_id, project)
        elif method == "tools/call":
            result = await mcp.call(
                params.get("name", ""),
                params.get("arguments") or {},
                agent_id,
                project,
                allow_global=is_admin,
            )
        else:
            return mcp_response(
                request_id, error={"code": -32601, "message": "Method not found"}
            )
    except (KeyError, ValueError) as exc:
        return mcp_response(
            request_id, error={"code": -32602, "message": str(exc).strip("'")}
        )
    except PermissionError as exc:
        return mcp_response(
            request_id, error={"code": -32003, "message": str(exc)}
        )
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        return mcp_response(
            request_id, error={"code": -32000, "message": f"MCP upstream failed: {exc}"}
        )
    return mcp_response(request_id, result=result)


@app.delete("/mcp", include_in_schema=False)
def close_mcp_session(request: Request):
    session_id = request.headers.get("Mcp-Session-Id")
    if mcp_session_get(session_id) is None:
        raise HTTPException(404, "MCP session not found")
    with mcp_sessions_lock:
        mcp_sessions.pop(session_id, None)
    return Response(status_code=204)


@app.get("/mcp/configs")
def mcp_configs(agent_id: str | None = None, project: str | None = None):
    return {"configs": mcp.configs(agent_id, project)}


@app.put("/mcp/configs")
def mcp_config_put(body: McpConfigPut):
    tier, ident = namespace_parts(body.namespace)
    directory = ROOT / "mcp" / tier if tier == "global" else ROOT / "mcp" / tier / ident
    with mutation_lock("mcp"):
        atomic_json(directory / (safe_part(body.server_id) + ".json"), body.config)
        mcp.clear()
    return {"status": "ok", "server_id": body.server_id, "namespace": body.namespace}


@app.delete("/mcp/configs")
def mcp_config_delete(namespace: str, server_id: str):
    tier, ident = namespace_parts(namespace)
    directory = ROOT / "mcp" / tier if tier == "global" else ROOT / "mcp" / tier / ident
    path = directory / (safe_part(server_id) + ".json")
    with mutation_lock("mcp"):
        if not path.is_file():
            raise HTTPException(404, "MCP config not found")
        path.unlink()
        mcp.clear()
    return {"status": "ok"}


@app.post("/memory/add")
def memory_add(body: MemoryAdd):
    return memory.add(**body.model_dump())


@app.post("/memory/search")
def memory_search(body: MemorySearch):
    return memory.search(**body.model_dump())


@app.get("/memory")
def memory_list(namespace: str = "global", agent_id: str = "shared", limit: int = 100):
    return memory.list(namespace, agent_id, limit)


@app.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    if not memory.delete(memory_id):
        raise HTTPException(404, "memory not found")
    return {"status": "ok"}


@app.post("/wiki/page")
def wiki_put(body: WikiPut):
    return wiki.put(**body.model_dump())


@app.get("/wiki/page")
def wiki_get(namespace: str, title: str):
    try:
        return wiki.get(namespace, title)
    except FileNotFoundError as exc:
        raise HTTPException(404, "wiki page not found") from exc


@app.delete("/wiki/page")
def wiki_delete(namespace: str, title: str):
    if not wiki.delete(namespace, title):
        raise HTTPException(404, "wiki page not found")
    return {"status": "ok"}


@app.get("/wiki/pages")
def wiki_pages(namespace: str = "global"):
    return {"pages": wiki.list(namespace)}


@app.get("/wiki/search")
def wiki_search(namespace: str = "global", q: str = "", limit: int = 20):
    return {"results": wiki.search(namespace, q, limit)}


@app.get("/wiki/history")
def wiki_history(namespace: str, title: str):
    return {"history": wiki.history(namespace, title)}


@app.post("/wiki/reindex")
def wiki_reindex(namespace: str = "global"):
    return wiki.rebuild_index(namespace)


@app.get("/skills")
def skills_list(agent_id: str | None = None, project: str | None = None):
    return {"skills": skills.list(agent_id, project)}


@app.put("/skills")
def skill_put(body: SkillPut):
    return skills.put(**body.model_dump())


@app.delete("/skills")
def skill_delete(namespace: str, name: str):
    if not skills.delete(namespace, name):
        raise HTTPException(404, "skill not found")
    return {"status": "ok"}


@app.get("/skills/{name:path}")
def skill_get(name: str, agent_id: str | None = None, project: str | None = None):
    try:
        return skills.get(name, agent_id, project)
    except FileNotFoundError as exc:
        raise HTTPException(404, "skill not found") from exc


@app.get("/files/list")
def file_list(namespace: str = "global"):
    return {"files": files.list(namespace)}


MAX_UPLOAD_BYTES = int(os.getenv("DHUB_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))


@app.post("/files/upload")
async def file_upload(file: UploadFile, namespace: str = "global"):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"upload exceeds {MAX_UPLOAD_BYTES} bytes")
    return {
        "status": "ok",
        **files.write(namespace, file.filename or "upload", data),
    }


@app.get("/files/download")
def file_download(namespace: str, file: str):
    try:
        return FileResponse(files.read(namespace, file), filename=Path(file).name)
    except FileNotFoundError as exc:
        raise HTTPException(404, "file not found") from exc


@app.delete("/files")
def file_delete(namespace: str, file: str):
    if not files.delete(namespace, file):
        raise HTTPException(404, "file not found")
    return {"status": "ok"}


@app.post("/agent/{agent_id}/call")
async def agent_call(agent_id: str, body: AgentCall):
    try:
        agent = state.registry.get(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    if not agent.get("enabled", True):
        raise HTTPException(403, "agent disabled")
    if not agent.get("url"):
        raise HTTPException(409, "agent has no callback url")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(agent["url"], json=body.model_dump())
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"agent call failed: {exc}") from exc
    return {"result": response.json(), "source_agent": agent_id}


@app.post("/sync/trigger")
def sync_trigger():
    try:
        return sync.run()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"semantic sync failed: {exc}") from exc


@app.get("/sync/history")
def sync_history():
    return {"history": sync.history()}


@app.post("/backup")
def run_backup():
    try:
        return backup()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/backup/{name}/restore")
def run_restore(name: str):
    try:
        result = restore(name)
        mcp.clear()
        return result
    except FileNotFoundError as exc:
        raise HTTPException(404, "backup not found") from exc
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/backups")
def list_backups():
    return {
        "backups": [
            {
                "name": path.name,
                "size": sum(
                    item.stat().st_size for item in path.rglob("*") if item.is_file()
                ),
            }
            for path in sorted((ROOT / "backups").glob("*"), reverse=True)
            if path.is_dir()
        ]
    }


@app.get("/logs")
def logs():
    return {
        "audit": state.audit.list(),
        "files": [
            {"name": path.name, "size": path.stat().st_size}
            for path in (ROOT / "logs").glob("*")
            if path.is_file()
        ],
    }


@app.get("/config")
def config_view():
    return {
        "root": str(ROOT),
        "version": VERSION,
        "memory_backend": memory.backend,
        "env": {
            "NEW_API_BASE_URL": os.getenv(
                "NEW_API_BASE_URL", "http://127.0.0.1:3000/v1"
            ),
            "DHUB_LLM_MODEL": os.getenv("DHUB_LLM_MODEL"),
            "DHUB_EMBED_MODEL": os.getenv("DHUB_EMBED_MODEL"),
            "DHUB_EMBED_DIMS": os.getenv("DHUB_EMBED_DIMS", "1536"),
        },
    }


@app.get("/dashboard/{module}")
def dashboard_data(module: str):
    providers = {
        "overview": health,
        "agents": agents,
        "mcp": lambda: {"configs": mcp.configs()},
        "memory": lambda: memory.list("global", "shared", 100),
        "wiki": lambda: {"pages": wiki.list("global")},
        "skills": lambda: {"skills": skills.list()},
        "files": lambda: {"files": files.list("global")},
        "sync": lambda: {
            "history": sync.history(),
            "ready": bool(os.getenv("NEW_API_KEY") and os.getenv("DHUB_LLM_MODEL")),
        },
        "logs": logs,
        "config": config_view,
        "backup": list_backups,
    }
    if module not in providers:
        raise HTTPException(404, "dashboard module not found")
    return providers[module]()


@app.get("/ui", response_class=HTMLResponse)
@app.get("/ui/{path:path}")
def ui(path: str = ""):
    return HTMLResponse(
        (Path(__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    )
