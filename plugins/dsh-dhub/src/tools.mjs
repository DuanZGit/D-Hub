// DSH tools exposed by the plugin. Deleting memory and sending cross-agent
// messages always require explicit user approval. No tool can execute an
// arbitrary command.

import { request } from "./http.mjs";

export function toolDefinitions() {
  return [
    {
      name: "dhub_memory_search",
      description: "Search D-Hub memory visible to the current agent/scope.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string" },
          limit: { type: "integer", minimum: 1, maximum: 200 },
        },
        required: ["query"],
      },
    },
    {
      name: "dhub_memory_remember",
      description: "Store a durable fact, decision, or observation in D-Hub.",
      inputSchema: {
        type: "object",
        properties: {
          content: { type: "string", minLength: 1 },
          metadata: { type: "object" },
        },
        required: ["content"],
      },
    },
    {
      name: "dhub_wiki_search",
      description: "Search durable Markdown knowledge in D-Hub Wiki.",
      inputSchema: {
        type: "object",
        properties: { query: { type: "string" }, limit: { type: "integer" } },
        required: ["query"],
      },
    },
    {
      name: "dhub_wiki_read",
      description: "Read a D-Hub Wiki page.",
      inputSchema: {
        type: "object",
        properties: { title: { type: "string", minLength: 1 } },
        required: ["title"],
      },
    },
    {
      name: "dhub_agent_send",
      description:
        "Send a structured message/task to another agent. Requires explicit user approval.",
      inputSchema: {
        type: "object",
        properties: {
          recipient_agent_id: { type: "string" },
          payload: { type: "object" },
        },
        required: ["recipient_agent_id", "payload"],
      },
    },
    {
      name: "dhub_agent_status",
      description: "Query the D-Hub connector status for agents.",
      inputSchema: { type: "object", properties: {} },
    },
  ];
}

function authHeaders(cfg) {
  const h = { Accept: "application/json" };
  if (cfg.token) h.Authorization = `Bearer ${cfg.token}`;
  return h;
}

export async function callTool(cfg, connector, name, args = {}) {
  switch (name) {
    case "dhub_memory_search": {
      const res = await request({
        url: `${cfg.dhubUrl}/memory/search`,
        token: cfg.token,
        method: "POST",
        body: {
          query: args.query,
          namespace: "global",
          agent_id: cfg.agentId,
          limit: args.limit || 10,
        },
      });
      return res;
    }
    case "dhub_memory_remember": {
      const res = await request({
        url: `${cfg.dhubUrl}/memory/add`,
        token: cfg.token,
        method: "POST",
        body: {
          namespace: "global",
          agent_id: cfg.agentId,
          content: args.content,
          metadata: args.metadata || {},
        },
      });
      return res;
    }
    case "dhub_wiki_search": {
      const q = new URLSearchParams({
        namespace: "global",
        q: args.query,
        limit: String(args.limit || 20),
      });
      const res = await request({
        url: `${cfg.dhubUrl}/wiki/search?${q}`,
        token: cfg.token,
      });
      return res;
    }
    case "dhub_wiki_read": {
      const q = new URLSearchParams({ namespace: "global", title: args.title });
      const res = await request({
        url: `${cfg.dhubUrl}/wiki/page?${q}`,
        token: cfg.token,
      });
      return res;
    }
    case "dhub_agent_send": {
      if (!args.recipient_agent_id || !args.payload) {
        throw new Error("dhub_agent_send requires recipient_agent_id and payload");
      }
      // Requires user approval by design (see README security section)
      return connector.send(args.recipient_agent_id, args.payload);
    }
    case "dhub_agent_status": {
      return connector.status();
    }
    default:
      throw new Error(`unknown tool: ${name}`);
  }
}
