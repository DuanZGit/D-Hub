// Configuration for the dsh-dhub plugin.
// All values come from the Cordis config (config.example.yaml) or env vars.
// No real secrets are ever embedded; the token comes from an env var.

import os from "node:os";
import path from "node:path";

function bool(value, fallback = false) {
  if (value === undefined || value === null) return fallback;
  if (typeof value === "boolean") return value;
  return String(value).toLowerCase() === "true";
}

export function loadConfig(raw = {}) {
  const tokenEnv = raw.tokenEnv || "DHUB_AGENT_TOKEN";
  return {
    dhubUrl: (raw.dhubUrl || process.env.DHUB_URL || "http://127.0.0.1:10101").replace(/\/+$/, ""),
    agentId: raw.agentId || process.env.DHUB_AGENT_ID || "dsh",
    project: raw.project || process.env.DHUB_PROJECT || null,
    token: process.env[tokenEnv] || raw.token || "",
    recallEnabled: bool(raw.recallEnabled, true),
    recallTokenBudget: Number(raw.recallTokenBudget || 1800),
    recallLimit: Number(raw.recallLimit || 10),
    captureEnabled: bool(raw.captureEnabled, true),
    uploadMaxBytes: Number(raw.uploadMaxBytes || 20000),
    captureInclude: raw.captureInclude || ["user", "assistant", "tool-summary"],
    connectorEnabled: bool(raw.connectorEnabled, true),
    heartbeatIntervalSec: Number(raw.heartbeatIntervalSec || 30),
    pollIntervalSec: Number(raw.pollIntervalSec || 5),
    stateFile: raw.stateFile || path.join(os.homedir(), ".dsh-dhub", "state.json"),
  };
}
