// dsh-dhub Cordis plugin entry.
//
// This plugin connects DSH to a D-Hub: shared memory recall, session capture,
// and the cross-device Agent Connector. DSH only makes outbound HTTPS calls to
// D-Hub; no inbound port is opened.
//
// Lifecycle mapping (per the DSH profiles/Cordis model):
//   - session-start: register/recover the connector
//   - pre-step (or equivalent context build): recall relevant memory
//   - session event / turn end: incrementally capture session results
//   - shutdown: flush pending queue and unregister/mark offline
//
// The exact DSH hook names depend on the DSH runtime version. This package
// exposes plain functions plus a `createPlugin()` factory so a host runtime
// can bind them to its real lifecycle. We do NOT fabricate hook names that
// may not exist; the README documents how to bind.

import { loadConfig } from "./config.mjs";
import { ConnectorClient } from "./connector.mjs";
import { recall } from "./recall.mjs";
import { captureSession } from "./capture.mjs";
import { callTool, toolDefinitions } from "./tools.mjs";

export { loadConfig, ConnectorClient, recall, captureSession, callTool, toolDefinitions };

export function createPlugin(rawConfig = {}) {
  const cfg = loadConfig(rawConfig);
  const connector = new ConnectorClient(cfg);
  const state = {
    sessionId: null,
    events: [],
    timers: [],
  };

  async function onSessionStart(info = {}) {
    state.sessionId = info.sessionId || `dsh-${cfg.agentId}-${Date.now()}`;
    state.events = [];
    if (cfg.connectorEnabled && cfg.token) {
      try {
        await connector.register();
        await connector.heartbeat("online");
        // periodic heartbeat + poll
        const hb = setInterval(
          () => connector.heartbeat("online").catch(() => {}),
          cfg.heartbeatIntervalSec * 1000
        );
        const pl = setInterval(
          () => pollAndAck(),
          cfg.pollIntervalSec * 1000
        );
        state.timers.push(hb, pl);
      } catch {
        // degrade: D-Hub unreachable
      }
    }
    return { sessionId: state.sessionId };
  }

  async function onPreStep(input = {}) {
    if (!cfg.recallEnabled) return { context: "" };
    const result = await recall({
      cfg,
      query: input.query || input.prompt || "",
      context: input,
    });
    return { context: result.block, records: result.records };
  }

  async function onTurnEnd(event = {}) {
    if (event.role && event.content) {
      state.events.push({ role: event.role, content: event.content });
    }
    if (!cfg.captureEnabled) return { uploaded: 0 };
    const result = await captureSession({
      cfg,
      sessionId: state.sessionId,
      events: state.events,
      stateFile: cfg.stateFile,
    });
    return result;
  }

  async function onShutdown() {
    for (const t of state.timers) clearInterval(t);
    state.timers = [];
    if (cfg.connectorEnabled && cfg.token) {
      try {
        await connector.heartbeat("offline");
      } catch {
        /* ignore */
      }
    }
    return { flushed: true };
  }

  async function pollAndAck() {
    if (!cfg.token) return;
    try {
      const res = await connector.poll(10);
      for (const msg of res.messages || []) {
        await connector.ack(msg.id);
      }
    } catch {
      /* ignore */
    }
  }

  return {
    config: cfg,
    connector,
    lifecycle: {
      sessionStart: onSessionStart,
      preStep: onPreStep,
      turnEnd: onTurnEnd,
      shutdown: onShutdown,
    },
    tools: {
      definitions: toolDefinitions(),
      call: (name, args) => callTool(cfg, connector, name, args),
    },
  };
}
