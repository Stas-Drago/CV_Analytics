import { api, jsonOptions } from "./api.js?v=stage7-2";
import { element, formatTime, setState } from "./ui.js?v=stage7-2";

function evidenceCard(item) {
  const card = element("article", "", "evidence-card");
  card.append(element("strong", item.object_type || "Событие"));
  card.append(element("p", item.description || "Описание отсутствует."));
  card.append(element("p", `${formatTime(item.occurred_at)} · ${item.camera_id} · ${item.event_id}`, "event-meta"));
  if (item.score !== null && item.score !== undefined) card.append(element("p", `Semantic score: ${Number(item.score).toFixed(3)}`, "event-meta"));
  return card;
}

function dataTable(rows) {
  const table = element("table", "", "result-table");
  if (!rows.length) return table;
  const columns = Object.keys(rows[0]);
  const head = document.createElement("thead"); const headRow = document.createElement("tr");
  for (const column of columns) headRow.append(element("th", column)); head.append(headRow); table.append(head);
  const body = document.createElement("tbody");
  for (const row of rows) { const tr = document.createElement("tr"); for (const column of columns) tr.append(element("td", row[column])); body.append(tr); }
  table.append(body); return table;
}

function renderResult(result) {
  const root = document.querySelector("#search-results"); root.replaceChildren();
  const answer = element("section", "", "answer-card");
  answer.append(element("p", result.answer_ru || "Система не сформировала резюме.")); root.append(answer);
  if (result.route === "vector") {
    const grid = element("div", "", "evidence-grid");
    for (const item of result.evidence || []) grid.append(evidenceCard(item));
    if (grid.childElementCount) root.append(grid);
  } else if (result.route === "sql") {
    if (typeof result.data?.count === "number") root.append(element("div", result.data.count, "result-count"));
    if (Array.isArray(result.data?.rows)) root.append(dataTable(result.data.rows));
  }
}

export function installSearch() {
  document.querySelector("#search-form").addEventListener("submit", async (formEvent) => {
    formEvent.preventDefault();
    const request = document.querySelector("#request").value.trim(); if (!request) return;
    const status = document.querySelector("#search-state"); const submit = document.querySelector("#search-submit");
    submit.disabled = true; document.querySelector("#search-results").replaceChildren(); setState(status, "Выполняется поиск…", "loading");
    try { const result = await api("/query", jsonOptions("POST", { request })); renderResult(result); setState(status, ""); }
    catch (error) {
      const message = error.code === "clarification_required" ? "Уточните временной период или недостающие параметры запроса." : error.message;
      setState(status, message, "error");
    } finally { submit.disabled = false; }
  });
}
