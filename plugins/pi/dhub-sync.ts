/**
 * Pi extension — one-way sync of the session transcript to D-Hub.
 *
 * Listens for `session_shutdown`, reads the current session JSONL file, and
 * uploads only the new messages to a cloud D-Hub via its REST API.
 *
 * Zero dependencies: uses Node built-ins (node:fs / node:http / node:https)
 * plus the ExtensionAPI types that ship with Pi itself.
 *
 * Install: copy this file to ~/.pi/agent/extensions/dhub-sync.ts
 *
 * Environment variables:
 *   DHUB_URL        D-Hub base URL            (default http://127.0.0.1:10101)
 *   DHUB_API_KEY    admin or agent API key    (sent as Authorization: Bearer)
 *   DHUB_NAMESPACE  target namespace          (default global)
 *   DHUB_AGENT_ID   agent id for the session  (default pi)
 *   DHUB_SYNC_STATE state file path           (default ~/.pi/agent/.dhub-sync.json)
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import * as http from "node:http";
import * as https from "node:https";

const DHUB_URL = (process.env.DHUB_URL || "http://127.0.0.1:10101").replace(/\/$/, "");
const DHUB_API_KEY = process.env.DHUB_API_KEY || process.env.DHUB_ADMIN_KEY || "";
const DHUB_NAMESPACE = process.env.DHUB_NAMESPACE || "global";
const DHUB_AGENT_ID = process.env.DHUB_AGENT_ID || "pi";
const STATE_PATH =
  process.env.DHUB_SYNC_STATE ||
  path.join(os.homedir(), ".pi", "agent", ".dhub-sync.json");

type SyncState = { sessions: Record<string, { session_id: string; offset: number }> };

function loadState(): SyncState {
  try {
    return JSON.parse(fs.readFileSync(STATE_PATH, "utf-8"));
  } catch {
    return { sessions: {} };
  }
}

function saveState(state: SyncState): void {
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2), "utf-8");
}

function postJson(apiPath: string, payload: unknown): Promise<Record<string, unknown>> {
  const body = JSON.stringify(payload);
  const url = new URL(apiPath, DHUB_URL);
  const lib = url.protocol === "https:" ? https : http;
  return new Promise((resolve, reject) => {
    const req = lib.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === "https:" ? 443 : 80),
        path: url.pathname + url.search,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(DHUB_API_KEY ? { Authorization: `Bearer ${DHUB_API_KEY}` } : {}),
        },
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`d-hub HTTP ${res.statusCode}: ${data}`));
            return;
          }
          try {
            resolve(data ? JSON.parse(data) : {});
          } catch {
            resolve({});
          }
        });
      },
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function sanitize(str: string): string {
  // 清洗孤立 Unicode surrogate（emoji 被截断等产生的非法字符），
  // 否则 Node 端 JSON.stringify 会输出 \udXXX 转义，Python 端 D-Hub 无法编码。
  if (typeof (str as { toWellFormed?: () => string }).toWellFormed === "function") {
    return (str as { toWellFormed: () => string }).toWellFormed();
  }
  return str.replace(
    /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g,
    "\uFFFD",
  );
}

function contentToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const block of content) {
      if (typeof block === "string") parts.push(block);
      else if (block && typeof block === "object") {
        const b = block as Record<string, unknown>;
        if (typeof b.text === "string") parts.push(b.text);
        else if (typeof b.thinking === "string") parts.push(b.thinking);
      }
    }
    return parts.join("\n");
  }
  return "";
}

function parseMessages(lines: string[]): Array<{ role: string; content: string }> {
  const messages: Array<{ role: string; content: string }> = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    let entry: Record<string, unknown>;
    try {
      entry = JSON.parse(line);
    } catch {
      continue;
    }
    if (entry.type !== "message") continue;
    const msg = entry.message as Record<string, unknown> | undefined;
    if (!msg || typeof msg !== "object") continue;
    let role = String(msg.role ?? "");
    if (role === "toolResult" || role === "bashExecution") role = "tool";
    else if (role !== "user" && role !== "assistant") role = "system";
    const content = sanitize(contentToText(msg.content));
    if (!content.trim()) continue;
    messages.push({ role, content });
  }
  return messages;
}

async function syncSession(sessionFile: string): Promise<void> {
  let lines: string[];
  try {
    lines = fs.readFileSync(sessionFile, "utf-8").split("\n");
  } catch {
    return;
  }
  if (lines.length === 0) return;

  const state = loadState();
  let record = state.sessions[sessionFile];

  // Resolve or create the remote session.
  let sessionId: string;
  if (record && record.session_id) {
    sessionId = record.session_id;
  } else {
    let cwd = "";
    try {
      const first = lines[0] ? JSON.parse(lines[0]) : null;
      if (first && typeof first.cwd === "string") cwd = first.cwd;
    } catch {
      /* ignore */
    }
    const created = await postJson("/sessions", {
      namespace: DHUB_NAMESPACE,
      title: path.basename(sessionFile),
      cwd,
      agent_id: DHUB_AGENT_ID,
      metadata: { source: "pi", path: sessionFile },
    });
    sessionId = String(created.session_id ?? "");
    if (!sessionId) throw new Error("failed to create d-hub session");
    record = { session_id: sessionId, offset: 0 };
    state.sessions[sessionFile] = record;
    // 立即持久化 session 映射：即使后续 messages 上传失败，
    // 重跑时也能复用同一个远程 session，避免重复创建。
    saveState(state);
  }

  const offset = record.offset;
  const messages = parseMessages(lines.slice(offset));
  if (messages.length === 0) {
    saveState(state);
    return;
  }

  await postJson(`/sessions/${sessionId}/messages`, {
    namespace: DHUB_NAMESPACE,
    messages,
  });
  record.offset = lines.length;
  saveState(state);
  // eslint-disable-next-line no-console
  console.log(`[dhub-sync] uploaded ${messages.length} messages from ${sessionFile}`);
}

export default function (pi: ExtensionAPI): void {
  pi.on("session_shutdown", async (_event, ctx) => {
    const sessionFile = ctx.sessionManager.getSessionFile();
    if (!sessionFile || sessionFile === "ephemeral") return;
    try {
      await syncSession(sessionFile);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(`[dhub-sync] ${err instanceof Error ? err.message : err}`);
    }
  });
}
