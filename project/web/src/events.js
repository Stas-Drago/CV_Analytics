import { api, jsonOptions } from "./api.js?v=stage7-2";
import { button, element, formatTime, safeMediaUrl, setState } from "./ui.js?v=stage7-2";

const state = { cursor: null, nextCursor: null, history: [], page: 1, role: "viewer", onDecision: null };

function riskBars(probabilities) {
  const root = element("div", "", "risk-bars");
  for (const level of ["low", "medium", "high"]) {
    const value = Math.max(0, Math.min(1, Number(probabilities?.[level] || 0)));
    const row = element("div", "", `risk-row ${level}`);
    row.append(element("span", level));
    const track = element("div", "", "risk-track");
    const fill = element("div", "", "risk-fill");
    fill.style.width = `${(value * 100).toFixed(1)}%`;
    track.append(fill);
    row.append(track, element("span", `${(value * 100).toFixed(0)}%`));
    root.append(row);
  }
  return root;
}

export function openFrame(url, title) {
  const safe = safeMediaUrl(url);
  if (!safe) return;
  const dialog = document.querySelector("#frame-dialog");
  document.querySelector("#frame-dialog-title").textContent = title;
  document.querySelector("#frame-dialog-image").src = safe;
  dialog.showModal();
}

function shadowForm(event, card) {
  const form = element("form", "", "shadow-form");
  const select = document.createElement("select");
  for (const value of ["low", "medium", "high"]) {
    const option = element("option", value); option.value = value; select.append(option);
  }
  const note = document.createElement("input"); note.placeholder = "Комментарий"; note.maxLength = 2000;
  const submit = button("Сохранить метку", "ghost"); submit.type = "submit";
  form.append(select, note, submit);
  form.addEventListener("submit", async (formEvent) => {
    formEvent.preventDefault(); submit.disabled = true;
    try {
      await api(`/alerts/shadow/${event.shadow_task.id}/label`, jsonOptions("POST", { label: select.value, note: note.value }));
      form.replaceWith(element("p", "Shadow-метка сохранена. Это не подтверждённый инцидент.", "muted"));
      state.onDecision?.();
    } catch (error) {
      submit.disabled = false;
      card.append(element("p", error.message, "inline-error"));
    }
  });
  return form;
}

export function eventCard(event, { allowMedia = false, allowActions = false } = {}) {
  const card = element("article", "", "event-card");
  const media = element("div", "", "event-media");
  const crop = allowMedia ? safeMediaUrl(event.crop_url) : null;
  if (crop) { const image = document.createElement("img"); image.src = crop; image.alt = `Crop: ${event.object_type}`; media.append(image); }
  else media.append(element("span", allowMedia ? "Crop отсутствует" : "Только метаданные", "event-placeholder"));

  const content = element("div", "", "event-content");
  const description = element("div");
  description.append(element("h3", event.object_type || "Объект"));
  description.append(element("p", `${formatTime(event.occurred_at)} · ${event.camera_id || "камера неизвестна"} · event ${event.event_id}`, "event-meta"));
  description.append(element("p", event.description || "Описание ещё не готово.", "event-description"));
  const actions = element("div", "", "event-actions");
  const frame = allowMedia ? safeMediaUrl(event.frame_url) : null;
  if (frame) { const frameButton = button("Полный кадр"); frameButton.addEventListener("click", () => openFrame(frame, `${event.object_type} · ${formatTime(event.occurred_at)}`)); actions.append(frameButton); }
  if (actions.childElementCount) description.append(actions);
  if (allowActions && event.shadow_task?.status === "pending") description.append(shadowForm(event, card));

  const risk = element("div", "", "risk-panel");
  const status = event.alert_status || event.shadow_task?.status || "not_required";
  risk.append(element("span", status === "pending" ? "Требует проверки" : status, `risk-chip ${status}`));
  risk.append(riskBars(event.risk?.probabilities));
  risk.append(element("span", event.risk ? `${event.risk.model_version} · ${event.risk.mode}` : "Ожидает risk-оценки", "event-meta"));
  content.append(description, risk); card.append(media, content);
  return card;
}

export async function loadEvents(cursor = null, { silent = false } = {}) {
  const root = document.querySelector("#events");
  const status = document.querySelector("#events-state");
  if (!silent) setState(status, "Загрузка событий…", "loading");
  try {
    const query = new URLSearchParams({ limit: "10" }); if (cursor) query.set("cursor", cursor);
    const result = await api(`/events?${query}`);
    root.replaceChildren();
    for (const event of result.items) root.append(eventCard(event, { allowMedia: state.role !== "viewer", allowActions: state.role !== "viewer" }));
    setState(status, result.items.length ? "" : "На этой странице событий нет.");
    state.cursor = cursor; state.nextCursor = result.next_cursor;
    document.querySelector("#events-next").disabled = !state.nextCursor;
    document.querySelector("#events-previous").disabled = state.history.length === 0;
    document.querySelector("#events-page").textContent = `Страница ${state.page}`;
  } catch (error) { if (!silent) setState(status, error.message, "error"); }
}

export function installEvents(role, onDecision) {
  state.role = role; state.onDecision = onDecision;
  document.querySelector("#events-next").addEventListener("click", () => {
    if (!state.nextCursor) return; state.history.push(state.cursor); state.page += 1; loadEvents(state.nextCursor);
  });
  document.querySelector("#events-previous").addEventListener("click", () => {
    if (!state.history.length) return; const previous = state.history.pop(); state.page -= 1; loadEvents(previous);
  });
  return loadEvents();
}

export function refreshEvents(options) { return loadEvents(state.cursor, options); }
