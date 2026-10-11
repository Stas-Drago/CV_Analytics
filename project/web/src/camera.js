import { api } from "./api.js?v=stage7-2";

export async function updateCameraStatus() {
  const status = await api("/camera/status");
  const node = document.querySelector("#camera-status");
  const online = status.state === "online" && status.connected;
  node.textContent = online ? "Камера подключена" : (status.error || "Камера недоступна");
  node.className = online ? "ok" : "error";
  const meta = document.querySelector("#camera-meta");
  if (status.state === "online") {
    meta.textContent = `YOLO: ${status.model}; объектов в кадре: ${status.detections ?? 0}`;
  } else {
    meta.textContent = `Состояние: ${status.state || "offline"}. Автопереподключение отключено.`;
  }
}
