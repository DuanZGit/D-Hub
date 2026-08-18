import test from "node:test";
import assert from "node:assert/strict";

import { loadConfig } from "../src/config.mjs";
import { buildUploadMessages } from "../src/capture.mjs";
import { redact, readStateFile, writeStateFile } from "../src/capture.mjs";
import { recall } from "../src/recall.mjs";
import { callTool, toolDefinitions } from "../src/tools.mjs";
import { createPlugin } from "../src/index.mjs";
import { ConnectorClient } from "../src/connector.mjs";

test("loadConfig uses placeholders and env token", () => {
  process.env.DHUB_AGENT_TOKEN = "t-123";
  const cfg = loadConfig({
    dhubUrl: "https://example.invalid/dhub",
    agentId: "example-agent",
    tokenEnv: "DHUB_AGENT_TOKEN",
  });
  assert.equal(cfg.dhubUrl, "https://example.invalid/dhub");
  assert.equal(cfg.agentId, "example-agent");
  assert.equal(cfg.token, "t-123");
  delete process.env.DHUB_AGENT_TOKEN;
});

test("buildUploadMessages only uploads allowed roles and redacts secrets", () => {
  const cfg = loadConfig({
    captureInclude: ["user", "assistant", "tool-summary"],
    uploadMaxBytes: 20000,
  });
  const messages = buildUploadMessages(
    [
      { role: "user", content: "hello" },
      { role: "assistant", content: "the api key is sk-abc1234567890xyz" },
      { role: "tool", content: "summary here" },
      { role: "reasoning", content: "secret thinking" },
    ],
    cfg
  );
  const roles = messages.map((m) => m.role);
  assert.deepEqual(roles, ["user", "assistant", "tool"]);
  assert.ok(!messages[1].content.includes("sk-abc1234567890xyz"));
  assert.ok(!messages.some((m) => m.content.includes("secret thinking")));
});

test("redact removes obvious credentials", () => {
  const out = redact("password=super, bearer sk-abcdefghij123456");
  assert.ok(!out.includes("super"));
  assert.ok(out.includes("[REDACTED]"));
});

test("state file roundtrip", (t) => {
  const file = t.mock ? "/tmp/dsh-test-state.json" : "/tmp/dsh-test-state.json";
  writeStateFile(file, { "s1": 5 });
  const state = readStateFile(file);
  assert.equal(state["s1"], 5);
});

test("recall returns empty when D-Hub unreachable", async () => {
  const cfg = loadConfig({
    dhubUrl: "http://127.0.0.1:1", // unreachable
    token: "x",
    recallEnabled: true,
  });
  const result = await recall({ cfg, query: "anything" });
  assert.equal(result.block, "");
  assert.deepEqual(result.records, []);
});

test("tool definitions include the six required tools", () => {
  const names = toolDefinitions().map((t) => t.name).sort();
  assert.deepEqual(names, [
    "dhub_agent_send",
    "dhub_agent_status",
    "dhub_memory_remember",
    "dhub_memory_search",
    "dhub_wiki_read",
    "dhub_wiki_search",
  ]);
});

test("dhub_agent_send requires recipient and payload", async () => {
  const plugin = createPlugin({ dhubUrl: "http://127.0.0.1:1", token: "x" });
  await assert.rejects(
    () => plugin.tools.call("dhub_agent_send", {}),
    /requires/
  );
});

test("createPlugin exposes lifecycle and tools", () => {
  const plugin = createPlugin({ agentId: "example-agent" });
  assert.equal(typeof plugin.lifecycle.sessionStart, "function");
  assert.equal(typeof plugin.lifecycle.preStep, "function");
  assert.equal(typeof plugin.lifecycle.turnEnd, "function");
  assert.equal(typeof plugin.lifecycle.shutdown, "function");
  assert.equal(typeof plugin.tools.call, "function");
});

test("connector methods build correct URLs", () => {
  const cfg = loadConfig({ dhubUrl: "http://dhub:10101", agentId: "a", token: "t" });
  const c = new ConnectorClient(cfg);
  assert.equal(c.cfg.dhubUrl, "http://dhub:10101");
  assert.equal(c.cfg.agentId, "a");
});
