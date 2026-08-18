"""Cross-device Agent Connector (server side).

DSH plugins on different machines connect outbound to d-hub. The connector:

- registers a connector (agent_id + scoped token)
- accepts heartbeat / poll / ack / send
- keeps a persistent message queue with TTL, idempotency, dead-letter
- enforces ACL by scoped token (namespace / project / capability)
- records audit events

Scoped tokens are shown once at creation; the server only stores a hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field

from .config import ROOT, atomic_json, mutation_lock, now, read_json, safe_part

CONNECTOR_DIR = ROOT / "data" / "connector"
MAX_PAYLOAD_BYTES = int(os.getenv("DHUB_CONNECTOR_MAX_PAYLOAD", str(64 * 1024)))
DEFAULT_TTL_SECONDS = int(os.getenv("DHUB_CONNECTOR_MESSAGE_TTL", str(86400)))


@dataclass
class ConnectorAgent:
    agent_id: str
    agent_name: str
    owner: str
    namespace: str
    project: str | None
    capabilities: list
    status: str = "registered"  # registered | online | offline
    last_seen: str = ""
    created_at: str = field(default_factory=now)
    token_hash: str = ""


@dataclass
class ConnectorMessage:
    id: str
    type: str
    sender_agent_id: str
    recipient_agent_id: str | None
    recipient_scope: str | None
    namespace: str
    project_id: str | None
    session_id: str | None
    created_at: str
    expires_at: str | None
    idempotency_key: str
    payload: dict
    required_capability: str | None
    requires_user_approval: bool
    status: str = "pending"  # pending | delivered | acked | dead
    attempts: int = 0


def _message_id():
    return uuid.uuid4().hex


def _expires(ttl: int | None = None) -> str:
    ttl = ttl if ttl is not None else DEFAULT_TTL_SECONDS
    return str(time.time() + ttl)


class ConnectorStore:
    def __init__(self, root=None):
        self.root = root or CONNECTOR_DIR
        self.lock = threading.RLock()
        self._ensure()

    def _ensure(self):
        (self.root / "agents").mkdir(parents=True, exist_ok=True)
        (self.root / "messages").mkdir(parents=True, exist_ok=True)
        (self.root / "dead").mkdir(parents=True, exist_ok=True)

    # -- agents -----------------------------------------------------------
    def _agent_path(self, agent_id):
        return self.root / "agents" / (safe_part(agent_id) + ".json")

    def _read_agent(self, agent_id):
        return read_json(self._agent_path(agent_id))

    def register(self, data) -> dict:
        """Create or refresh a connector agent. Returns the one-time token on create."""
        agent_id = safe_part(data.get("agent_id") or "")
        if not agent_id:
            raise ValueError("agent_id is required")
        existing = self._read_agent(agent_id)
        issued_token = None
        with mutation_lock("connector-agents"):
            if existing:
                item = {
                    **existing,
                    **data,
                    "agent_id": agent_id,
                    "last_seen": now(),
                }
            else:
                issued_token = secrets.token_urlsafe(32)
                item = {
                    "agent_id": agent_id,
                    "agent_name": data.get("agent_name") or agent_id,
                    "owner": data.get("owner") or "unknown",
                    "namespace": data.get("namespace") or "global",
                    "project": data.get("project"),
                    "capabilities": data.get("capabilities") or [],
                    "status": "registered",
                    "last_seen": now(),
                    "created_at": now(),
                    "token_hash": self._hash(issued_token),
                }
            atomic_json(self._agent_path(agent_id), item)
        public = {k: v for k, v in item.items() if k != "token_hash"}
        if issued_token:
            public["token"] = issued_token
        return public

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(str(token).encode()).hexdigest()

    def get_agent(self, agent_id) -> dict:
        item = self._read_agent(agent_id)
        if not item:
            raise KeyError(agent_id)
        return item

    def authenticate(self, agent_id, token, project=None) -> bool:
        item = self._read_agent(agent_id)
        if not item:
            return False
        expected = item.get("token_hash", "")
        supplied = self._hash(token or "")
        if not expected or not secrets.compare_digest(expected, supplied):
            return False
        # project scope binding
        if project and item.get("project") and project != item.get("project"):
            return False
        return item.get("status") != "disabled"

    def set_status(self, agent_id, status):
        with mutation_lock("connector-agents"):
            item = self._read_agent(agent_id)
            if not item:
                return False
            item["status"] = status
            item["last_seen"] = now()
            atomic_json(self._agent_path(agent_id), item)
        return True

    def unregister(self, agent_id) -> bool:
        path = self._agent_path(agent_id)
        with mutation_lock("connector-agents"):
            if not path.is_file():
                return False
            path.unlink()
        return True

    def list_agents(self):
        agents = []
        for path in sorted((self.root / "agents").glob("*.json")):
            item = read_json(path)
            if item:
                agents.append({k: v for k, v in item.items() if k != "token_hash"})
        return agents

    # -- messages ---------------------------------------------------------
    def _msg_path(self, mid):
        return self.root / "messages" / (safe_part(mid) + ".json")

    def _dead_path(self, mid):
        return self.root / "dead" / (safe_part(mid) + ".json")

    def _write_msg(self, msg: ConnectorMessage, dead=False):
        target = self._dead_path(msg.id) if dead else self._msg_path(msg.id)
        atomic_json(target, {
            "id": msg.id,
            "type": msg.type,
            "sender_agent_id": msg.sender_agent_id,
            "recipient_agent_id": msg.recipient_agent_id,
            "recipient_scope": msg.recipient_scope,
            "namespace": msg.namespace,
            "project_id": msg.project_id,
            "session_id": msg.session_id,
            "created_at": msg.created_at,
            "expires_at": msg.expires_at,
            "idempotency_key": msg.idempotency_key,
            "payload": msg.payload,
            "required_capability": msg.required_capability,
            "requires_user_approval": msg.requires_user_approval,
            "status": msg.status,
            "attempts": msg.attempts,
        })

    def _read_msg(self, mid):
        data = read_json(self._msg_path(mid))
        if not data:
            data = read_json(self._dead_path(mid))
        return data

    def enqueue(self, data: dict) -> dict:
        """Persist a message with idempotency-key dedup."""
        sender = safe_part(data.get("sender_agent_id") or "")
        recipient = data.get("recipient_agent_id")
        if recipient:
            recipient = safe_part(recipient)
        idem = data.get("idempotency_key") or uuid.uuid4().hex
        # idempotency: same key from same sender is not duplicated
        existing = self._find_by_idem(sender, idem)
        if existing:
            return {"status": "ok", "id": existing["id"], "duplicate": True}
        msg = ConnectorMessage(
            id=_message_id(),
            type=data.get("type", "task"),
            sender_agent_id=sender,
            recipient_agent_id=recipient,
            recipient_scope=data.get("recipient_scope"),
            namespace=data.get("namespace") or "global",
            project_id=data.get("project_id"),
            session_id=data.get("session_id"),
            created_at=now(),
            expires_at=data.get("expires_at") or _expires(),
            idempotency_key=idem,
            payload=data.get("payload") or {},
            required_capability=data.get("required_capability"),
            requires_user_approval=bool(data.get("requires_user_approval", False)),
        )
        if len(json.dumps(msg.payload).encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        with mutation_lock("connector-messages"):
            self._write_msg(msg)
        return {"status": "ok", "id": msg.id, "duplicate": False}

    def _find_by_idem(self, sender, idem):
        for path in (self.root / "messages").glob("*.json"):
            data = read_json(path)
            if (
                data
                and data.get("sender_agent_id") == sender
                and data.get("idempotency_key") == idem
            ):
                return data
        return None

    def poll(self, agent_id, project=None, limit=10) -> list[dict]:
        """Return pending messages addressed to this agent (not yet acked)."""
        now_ts = time.time()
        result = []
        for path in sorted((self.root / "messages").glob("*.json")):
            data = read_json(path)
            if not data:
                continue
            if data.get("status") != "pending":
                continue
            if data.get("expires_at") and float(data["expires_at"]) < now_ts:
                self._dead_letter(data["id"])
                continue
            recipient = data.get("recipient_agent_id")
            scope = data.get("recipient_scope")
            if recipient and recipient != agent_id:
                continue
            if not recipient and scope:
                # Scope-addressed: deliver only to agents whose namespace matches
                agent_ns = f"agents/{agent_id}"
                if scope == "agents/<self>":
                    if data.get("namespace") != agent_ns:
                        continue
                elif scope == "global":
                    pass
                elif scope != agent_ns:
                    continue
            if project and data.get("project_id") and data["project_id"] != project:
                continue
            result.append(data)
            if len(result) >= limit:
                break
        return result

    def ack(self, agent_id, message_id) -> bool:
        path = self._msg_path(message_id)
        with mutation_lock("connector-messages"):
            data = read_json(path)
            if not data:
                return False
            if data.get("recipient_agent_id") and data.get("recipient_agent_id") != agent_id:
                return False
            data["status"] = "acked"
            data["acked_at"] = now()
            atomic_json(path, data)
        return True

    def _dead_letter(self, message_id):
        path = self._msg_path(message_id)
        data = read_json(path)
        if not data:
            return
        with mutation_lock("connector-messages"):
            data["status"] = "dead"
            atomic_json(self._dead_path(message_id), data)
            path.unlink(missing_ok=True)

    def status(self, agent_id=None):
        now_ts = time.time()
        agents = self.list_agents()
        if agent_id:
            agents = [a for a in agents if a["agent_id"] == agent_id]
        # mark stale as offline
        for a in agents:
            try:
                last = float(a.get("last_seen") or 0)
            except (TypeError, ValueError):
                last = 0
            if a["status"] == "online" and time.time() - last > 60:
                a["status"] = "offline"
        pending = 0
        dead = 0
        for path in (self.root / "messages").glob("*.json"):
            data = read_json(path)
            if data and data.get("status") == "pending":
                # expiry check
                if data.get("expires_at") and float(data["expires_at"]) < now_ts:
                    dead += 1
                else:
                    pending += 1
        dead += len(list((self.root / "dead").glob("*.json")))
        return {"agents": agents, "pending": pending, "dead": dead}

    def get_message(self, message_id):
        return self._read_msg(message_id)
