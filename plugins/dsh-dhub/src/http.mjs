// HTTP helper for talking to D-Hub. Uses Node's global fetch (Node >= 18).
// All requests carry the scoped token; timeouts are bounded; failures are
// wrapped so DSH's main loop is never blocked.

export class HttpError extends Error {
  constructor(status, body) {
    super(`D-Hub returned HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function request({ url, token, method = "GET", body = null, timeoutMs = 10000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (body !== null) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  try {
    const res = await fetch(url, {
      method,
      headers,
      body: payload,
      signal: controller.signal,
    });
    if (!res.ok) {
      let text = "";
      try {
        text = await res.text();
      } catch {
        /* ignore */
      }
      throw new HttpError(res.status, text);
    }
    const text = await res.text();
    return text ? JSON.parse(text) : null;
  } finally {
    clearTimeout(timer);
  }
}
