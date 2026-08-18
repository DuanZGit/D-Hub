// D-Hub Agent Connector client: register / heartbeat / poll / ack / send.
// This is the outbound-only data plane; DSH never opens an inbound port.

import { request } from "./http.mjs";

export class ConnectorClient {
  constructor(cfg) {
    this.cfg = cfg;
    this.registered = false;
  }

  async register() {
    // Registering creates/rotates a scoped token server-side (admin provisioned).
    const res = await request({
      url: `${this.cfg.dhubUrl}/v1/connector/register`,
      token: this.cfg.token,
      method: "POST",
      body: {
        agent_id: this.cfg.agentId,
        agent_name: this.cfg.agentId,
        project: this.cfg.project || null,
        capabilities: ["memory", "wiki", "task"],
        namespace: "global",
      },
    });
    this.registered = true;
    return res;
  }

  async heartbeat(status = "online") {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/heartbeat`,
      token: this.cfg.token,
      method: "POST",
      body: { agent_id: this.cfg.agentId, status },
    });
  }

  async poll(limit = 10) {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/poll`,
      token: this.cfg.token,
      method: "POST",
      body: { agent_id: this.cfg.agentId, project: this.cfg.project || null, limit },
    });
  }

  async ack(messageId) {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/ack`,
      token: this.cfg.token,
      method: "POST",
      body: { agent_id: this.cfg.agentId, message_id: messageId },
    });
  }

  async send(recipient, payload, opts = {}) {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/send`,
      token: this.cfg.token,
      method: "POST",
      body: {
        sender_agent_id: this.cfg.agentId,
        recipient_agent_id: recipient,
        namespace: "global",
        project_id: this.cfg.project || null,
        type: opts.type || "task",
        payload,
        idempotency_key: opts.idempotencyKey,
        requires_user_approval: true,
      },
    });
  }

  async status() {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/status?agent_id=${encodeURIComponent(
        this.cfg.agentId
      )}`,
      token: this.cfg.token,
    });
  }

  async unregister() {
    return request({
      url: `${this.cfg.dhubUrl}/v1/connector/unregister?agent_id=${encodeURIComponent(
        this.cfg.agentId
      )}`,
      token: this.cfg.token,
      method: "POST",
      body: {},
    });
  }
}
