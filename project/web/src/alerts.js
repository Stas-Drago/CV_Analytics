import { api, jsonOptions } from "./api.js?v=stage7-2";
import { button, element, formatTime, setState } from "./ui.js?v=stage7-2";

const seenTaskIds = new Set();
let initialLoad = true;
let refreshCallback = null;
let pendingDecision = null;

function notifyNew(tasks) {
  const newTasks = tasks.filter((item) => item.shadow_task && !seenTaskIds.has(item.shadow_task.id));
  for (const item of tasks) if (item.shadow_task) seenTaskIds.add(item.shadow_task.id);
  if (initialLoad) { initialLoad = false; return; }
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  for (const item of newTasks) {
    new Notification("Новое наблюдение требует проверки", { body: `${item.object_type} · ${formatTime(item.occurred_at)}`, tag: `shadow-${item.shadow_task.id}` });
  }
}

function openDecision(event, action) {
  pendingDecision = { eventId: event.event_id, action };
  const confirmed = action === "confirm";
  document.querySelector("#decision-title").textContent = confirmed ? "Подтвердить наблюдение" : "Отклонить наблюдение";
  document.querySelector("#decision-description").textContent = `${event.object_type} · ${formatTime(event.occurred_at)}. Это решение не объявляет инцидент и не запускает внешних действий.`;
  document.querySelector("#decision-note").value = "";
  document.querySelector("#decision-error").hidden = true;
  const submit = document.querySelector("#decision-submit");
  submit.textContent = confirmed ? "Подтвердить наблюдение" : "Отклонить наблюдение";
  submit.className = `button ${confirmed ? "confirm" : "reject"}`;
  document.querySelector("#decision-dialog").showModal();
}

function highCard(event) {
  const card = element("article", "", "high-card");
  const header = document.createElement("header");
  header.append(element("strong", event.object_type || "Объект"), element("span", formatTime(event.occurred_at), "event-meta"));
  card.append(header, element("p", event.description || "Описание ещё не готово."));
  const confidence = Number(event.risk?.probabilities?.high || 0);
  card.append(element("p", `Вероятность high: ${(confidence * 100).toFixed(1)}% · ${event.camera_id}`, "event-meta"));
  const actions = element("div", "", "high-actions");
  const confirm = button("Подтвердить", "confirm"); confirm.addEventListener("click", () => openDecision(event, "confirm"));
  const reject = button("Отклонить", "reject"); reject.addEventListener("click", () => openDecision(event, "reject"));
  actions.append(confirm, reject); card.append(actions);
  return card;
}

export async function loadHighQueue({ silent = false } = {}) {
  const root = document.querySelector("#high-list");
  const status = document.querySelector("#high-state");
  if (!silent) setState(status, "Загрузка очереди…", "loading");
  try {
    const result = await api("/alerts/high?status=pending&limit=100");
    notifyNew(result.items);
    root.replaceChildren();
    for (const event of result.items) root.append(highCard(event));
    document.querySelector("#high-count").textContent = String(result.items.length);
    setState(status, result.items.length ? "" : "Новых high-наблюдений нет.");
  } catch (error) { if (!silent) setState(status, error.message, "error"); }
}

export function installAlerts(onRefresh) {
  refreshCallback = onRefresh;
  const notificationButton = document.querySelector("#notifications-button");
  if ("Notification" in window) {
    notificationButton.hidden = false;
    notificationButton.textContent = Notification.permission === "granted" ? "Уведомления включены" : "Включить уведомления";
    notificationButton.disabled = Notification.permission === "denied";
    notificationButton.addEventListener("click", async () => {
      const permission = await Notification.requestPermission();
      notificationButton.textContent = permission === "granted" ? "Уведомления включены" : "Уведомления запрещены";
      notificationButton.disabled = permission !== "default";
    });
  }
  document.querySelector("#decision-form").addEventListener("submit", async (formEvent) => {
    formEvent.preventDefault();
    if (!pendingDecision) return;
    const submit = document.querySelector("#decision-submit"); submit.disabled = true;
    const errorNode = document.querySelector("#decision-error"); errorNode.hidden = true;
    try {
      await api(`/alerts/${pendingDecision.eventId}/${pendingDecision.action}`, jsonOptions("POST", { note: document.querySelector("#decision-note").value }));
      document.querySelector("#decision-dialog").close(); pendingDecision = null;
      await Promise.all([loadHighQueue(), refreshCallback?.()]);
    } catch (error) { errorNode.textContent = error.message; errorNode.hidden = false; }
    finally { submit.disabled = false; }
  });
  loadHighQueue();
  return window.setInterval(() => loadHighQueue({ silent: true }), 10000);
}
