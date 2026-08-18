// Session capture: incrementally upload a filtered/summarised view of a session
// to D-Hub. Only uploads user messages, the assistant final body, and truncated
// tool summaries. Never uploads reasoning, raw credentials, env values, keys,
// or unrelated local file contents. D-Hub being unreachable must not block DSH.

import fs from "node:fs";
import path from "node:path";
import { request } from "./http.mjs";

const SENSITIVE = [
  "password",
  "token",
  "secret",
  "api_key",
  "apikey",
  "authorization",
  "cookie",
  "private key",
  "begin rsa",
];

export function redact(text) {
  let out = String(text || "");
  for (const word of SENSITIVE) {
    const esc = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // redact the key and the value after an assignment
    out = out.replace(new RegExp(`(${esc})\\s*[:=]\\s*\\S+`, "gi"), "[REDACTED]");
    out = out.replace(new RegExp(`(${esc})`, "gi"), "[REDACTED]");
  }
  // redact obvious long keys
  out = out.replace(/\b(sk-[A-Za-z0-9_-]{8,})\b/g, "[REDACTED]");
  return out;
}

function isAllowed(role, cfg) {
  if (role === "user") return cfg.captureInclude.includes("user");
  if (role === "assistant") return cfg.captureInclude.includes("assistant");
  if (role === "tool") return cfg.captureInclude.includes("tool-summary");
  return false;
}

export function buildUploadMessages(events, cfg) {
  const messages = [];
  for (const ev of events || []) {
    const role = ev.role;
    if (!isAllowed(role, cfg)) continue;
    let content = redact(ev.content);
    // truncate tool summaries
    if (role === "tool" && content.length > 2000) {
      content = content.slice(0, 2000) + "…[truncated tool summary]";
    }
    const bytes = Buffer.byteLength(content, "utf8");
    if (bytes > cfg.uploadMaxBytes) {
      content = content.slice(0, cfg.uploadMaxBytes) + "…[truncated]";
    }
    messages.push({ role, content });
  }
  return messages;
}

export function readStateFile(stateFile) {
  try {
    return JSON.parse(fs.readFileSync(stateFile, "utf8"));
  } catch {
    return {};
  }
}

export function writeStateFile(stateFile, state) {
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify(state, null, 2));
}

export async function captureSession({ cfg, sessionId, events, stateFile }) {
  if (!cfg.captureEnabled) return { uploaded: 0, reason: "disabled" };
  if (!cfg.token) return { uploaded: 0, reason: "no-token" };
  const state = readStateFile(stateFile);
  const key = sessionId || "default";
  const seen = state[key] || 0;
  const newEvents = (events || []).slice(seen);
  const messages = buildUploadMessages(newEvents, cfg);
  if (!messages.length) return { uploaded: 0, reason: "no-new-messages" };
  try {
    // ensure the session exists
    const meta = await request({
      url: `${cfg.dhubUrl}/sessions`,
      token: cfg.token,
      method: "POST",
      body: {
        namespace: "global",
        title: `dsh-${cfg.agentId}`,
        agent_id: cfg.agentId,
        project: cfg.project || null,
      },
    });
    const sid = meta.session_id;
    await request({
      url: `${cfg.dhubUrl}/sessions/${sid}/messages`,
      token: cfg.token,
      method: "POST",
      body: { namespace: "global", messages },
    });
    state[key] = (events || []).length;
    writeStateFile(stateFile, state);
    return { uploaded: messages.length, sessionId: sid };
  } catch {
    return { uploaded: 0, reason: "unreachable" };
  }
}
