import { api, jsonOptions } from "./api.js?v=stage7-2";
import { installAlerts } from "./alerts.js?v=stage7-2";
import { updateCameraStatus } from "./camera.js?v=stage7-2";
import { installEvents, refreshEvents } from "./events.js?v=stage7-2";
import { installSearch } from "./search.js?v=stage7-2";

let intervals = [];
let initialized = false;

function clearRuntime() {
  for (const interval of intervals) window.clearInterval(interval);
  intervals = [];
  const stream = document.querySelector("#camera-stream");
  stream.removeAttribute("src");
}

function showLogin(message = "") {
  clearRuntime();
  document.querySelector("#dashboard").hidden = true;
  document.querySelector("#login-view").hidden = false;
  const error = document.querySelector("#login-error"); error.textContent = message; error.hidden = !message;
}

function showDashboard(user) {
  document.querySelector("#login-view").hidden = true;
  document.querySelector("#dashboard").hidden = false;
  document.querySelector("#current-user").textContent = user.username;
  document.querySelector("#current-role").textContent = user.role;
  const operational = user.role === "operator" || user.role === "supervisor";
  document.querySelector("#camera-panel").hidden = !operational;
  document.querySelector("#high-panel").hidden = !operational;
  document.querySelector("#camera-status").hidden = !operational;
  if (operational) {
    document.querySelector("#camera-stream").src = "/api/camera/stream";
    updateCameraStatus().catch(() => {});
    intervals.push(window.setInterval(() => updateCameraStatus().catch(() => {}), 2000));
  }
  if (!initialized) {
    installSearch();
    installEvents(user.role, refreshEvents);
    intervals.push(window.setInterval(() => refreshEvents({ silent: true }).catch(() => {}), 10000));
    if (operational) intervals.push(installAlerts(refreshEvents));
    initialized = true;
  }
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = document.querySelector("#login-submit"); const error = document.querySelector("#login-error");
  submit.disabled = true; error.hidden = true;
  try {
    await api("/auth/login", jsonOptions("POST", { username: document.querySelector("#login-username").value.trim(), password: document.querySelector("#login-password").value }));
    window.location.reload();
  } catch (failure) { error.textContent = failure.message; error.hidden = false; submit.disabled = false; }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } finally { window.location.reload(); }
});

for (const close of document.querySelectorAll("[data-close-dialog]")) {
  close.addEventListener("click", () => document.querySelector(`#${close.dataset.closeDialog}`).close());
}
for (const cancel of document.querySelectorAll("#decision-dialog [value=cancel]")) {
  cancel.addEventListener("click", (event) => {
    event.preventDefault(); document.querySelector("#decision-dialog").close();
  });
}
window.addEventListener("auth:required", () => showLogin("Сессия завершена. Войдите снова."));

api("/auth/me").then(showDashboard).catch(() => showLogin());
