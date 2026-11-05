/** Reference client for the existing ordinary Console steering endpoints.
 * Browser (secure context) or Node.js 22+, no third-party dependencies.
 * No task creation, task cancellation, automatic retargeting or automatic retry.
 */

export class SteerHttpError extends Error {
  constructor(status, body) {
    const detail = body?.detail;
    super(
      typeof detail === "string" ? detail : detail?.message || `HTTP ${status}`,
    );
    this.name = "SteerHttpError";
    this.status = status;
    this.code = detail?.code || null;
    this.body = body;
  }
}

export class SteerTransportError extends Error {
  constructor(cause) {
    super("请求或响应读取失败；POST 是否已接收可能未知，请保留原操作重试。", {
      cause,
    });
    this.name = "SteerTransportError";
  }
}

export class SteerUnavailableError extends Error {
  constructor(state) {
    super(
      state.exists ? "任务存在，但当前不支持 steer。" : "当前没有活动任务。",
    );
    this.name = "SteerUnavailableError";
    this.state = state;
  }
}

export function createSteerClient({
  baseUrl,
  agentId,
  getToken = () => "",
  timeoutMs = 10000,
  fetchImpl = globalThis.fetch,
}) {
  if (
    typeof baseUrl !== "string" ||
    !baseUrl.trim() ||
    typeof agentId !== "string" ||
    !agentId.trim()
  ) {
    throw new TypeError("baseUrl 和 agentId 必须显式提供。");
  }
  const root = baseUrl.replace(/\/+$/, "");
  const inFlight = new Map();

  async function requestJson(
    path,
    { method = "GET", body, targetAgent = agentId } = {},
  ) {
    const headers = { "X-Agent-Id": targetAgent };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      let response;
      let raw;
      try {
        response = await fetchImpl(`${root}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });
        raw = await response.text();
      } catch (cause) {
        throw new SteerTransportError(cause);
      }
      let payload;
      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch (cause) {
        if (response.ok) throw new SteerTransportError(cause);
        payload = { detail: raw };
      }
      if (!response.ok) throw new SteerHttpError(response.status, payload);
      if (!payload) throw new SteerTransportError(new Error("Empty response"));
      return payload;
    } finally {
      clearTimeout(timer);
    }
  }

  function getStatus(chatId) {
    return requestJson(
      `/api/console/chat/status?chat_id=${encodeURIComponent(chatId)}`,
    );
  }

  async function prepareSteer(chatId, text) {
    if (typeof text !== "string" || !text.trim())
      throw new Error("引导文本不能为空。");
    const state = await getStatus(chatId);
    if (!state.exists || !state.can_steer || !state.run_id) {
      throw new SteerUnavailableError(state);
    }
    // Persist this object before the first POST. New guidance needs a new object.
    return Object.freeze({
      agent_id: state.agent_id,
      chat_id: state.chat_id,
      run_id: state.run_id,
      message_id: globalThis.crypto.randomUUID(),
      text,
    });
  }

  function submitSteer(operation) {
    // Copy at entry, so later changes in UI selection or a mutable restored
    // draft cannot change an in-flight request. Never query a new run here.
    const targetAgent = operation.agent_id;
    const body = {
      chat_id: operation.chat_id,
      run_id: operation.run_id,
      message_id: operation.message_id,
      text: operation.text,
    };
    if (
      [targetAgent, ...Object.values(body)].some(
        (value) => typeof value !== "string" || !value.trim(),
      )
    ) {
      return Promise.reject(
        new Error("操作缺少 agent_id/chat_id/run_id/message_id/text。"),
      );
    }
    const key = JSON.stringify([targetAgent, body]);
    const existing = inFlight.get(key);
    if (existing) return existing;
    const pending = requestJson("/api/console/chat/steer", {
      method: "POST",
      body,
      targetAgent,
    }).finally(() => inFlight.delete(key));
    inFlight.set(key, pending);
    return pending;
  }

  return { getStatus, prepareSteer, submitSteer };
}
