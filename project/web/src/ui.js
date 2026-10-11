export function element(name, text = "", className = "") {
  const node = document.createElement(name);
  node.textContent = String(text ?? "");
  if (className) node.className = className;
  return node;
}

export function setState(node, message, kind = "") {
  node.textContent = message;
  node.className = `state-block ${kind}`.trim();
  node.hidden = !message;
}

export function safeMediaUrl(value) {
  if (typeof value !== "string" || !value.startsWith("/api/events/")) return null;
  return value;
}

export function formatTime(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "Время неизвестно" : parsed.toLocaleString("ru-RU");
}

export function button(text, className = "ghost") {
  const node = element("button", text, `button ${className}`);
  node.type = "button";
  return node;
}
