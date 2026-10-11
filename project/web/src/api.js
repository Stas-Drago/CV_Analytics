export class ApiError extends Error {
  constructor(status, code, message, details = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, { credentials: "same-origin", ...options });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = payload?.error || {};
    const failure = new ApiError(response.status, error.code || "request_failed", error.message || "Запрос не выполнен.", error.details || []);
    if (response.status === 401) window.dispatchEvent(new CustomEvent("auth:required"));
    throw failure;
  }
  return payload;
}

export function jsonOptions(method, body) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
