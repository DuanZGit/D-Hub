// Memory recall: build a query from the current input + context, fetch matching
// memory from D-Hub, and produce a context block. If D-Hub is unreachable the
// plugin must not block DSH's main loop and returns an empty result.

import { request } from "./http.mjs";

const SYSTEM_PROMPT_MARKER = "dsh-dhub:recall";

function approxTokens(text) {
  return Math.ceil((text || "").length / 4);
}

export async function recall({ cfg, query, context = {} }) {
  if (!cfg.recallEnabled) return { block: "", records: [] };
  if (!cfg.token) return { block: "", records: [] };
  try {
    const payload = {
      query: query || "",
      namespace: "global",
      agent_id: cfg.agentId,
      limit: cfg.recallLimit,
    };
    const res = await request({
      url: `${cfg.dhubUrl}/memory/search`,
      token: cfg.token,
      method: "POST",
      body: payload,
    });
    const records = (res && res.results) || [];
    if (!records.length) return { block: "", records: [] };
    let lines = [];
    let used = 0;
    for (const rec of records) {
      const line = `- [${rec.memory_type || "note"}] ${rec.content}`;
      if (used + approxTokens(line) > cfg.recallTokenBudget) break;
      lines.push(line);
      used += approxTokens(line);
    }
    if (!lines.length) return { block: "", records: [] };
    const block = `\n<${SYSTEM_PROMPT_MARKER}>\n${lines.join("\n")}\n</${SYSTEM_PROMPT_MARKER}>\n`;
    return { block, records: records.slice(0, cfg.recallLimit) };
  } catch {
    // D-Hub unreachable -> degrade gracefully
    return { block: "", records: [] };
  }
}
