"""Минимальный сервер локальной камеры: поток, запись и контроль FPS."""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


class CameraService:
    def __init__(self, device: int, width: int, height: int):
        self.device = device
        self.width = width
        self.height = height
        self.capture: cv2.VideoCapture | None = None
        self.frame = None
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.connected = False
        self.last_error = ""

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if not self._open_devices():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
        self._close_devices()

    def _open_devices(self) -> bool:
        # AVFoundation is the native camera backend on macOS; CAP_ANY handles other OSes.
        backend = cv2.CAP_AVFOUNDATION if hasattr(cv2, "CAP_AVFOUNDATION") else cv2.CAP_ANY
        capture = cv2.VideoCapture(self.device, backend)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not capture.isOpened():
            capture.release()
            self.connected = False
            self.last_error = f"Не удалось открыть камеру {self.device}"
            return False

        self.capture = capture
        self.connected = True
        self.last_error = ""
        return True

    def _close_devices(self) -> None:
        if self.capture:
            self.capture.release()
        self.capture = None
        self.connected = False

    def _run(self) -> None:
        while not self.stop_event.is_set():
            ok, frame = self.capture.read() if self.capture else (False, None)
            if not ok or frame is None:
                self._close_devices()
                self.last_error = "Поток камеры прерван"
                return
            with self.lock:
                self.frame = frame.copy()
        self._close_devices()

    def jpeg(self) -> bytes | None:
        with self.lock:
            frame = None if self.frame is None else self.frame.copy()
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "device": self.device,
            "width": self.width,
            "height": self.height,
            "error": self.last_error,
        }


def create_app(service: CameraService) -> FastAPI:
    app = FastAPI(title="Local Camera")
    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(web_dir / "index.html")

    @app.get("/camera/status")
    def status():
        return service.status()

    @app.post("/camera/start")
    def start():
        service.start()
        return service.status()

    @app.post("/camera/stop")
    def stop():
        service.stop()
        return service.status()

    @app.get("/camera/stream")
    def stream():
        def frames():
            while True:
                image = service.jpeg()
                if image is None:
                    time.sleep(0.1)
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
                time.sleep(0.01)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальная камера с MJPEG-потоком")
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    service = CameraService(args.device, args.width, args.height)
    service.start()
    try:
        uvicorn.run(create_app(service), host="127.0.0.1", port=args.port)
    finally:
        service.stop()


if __name__ == "__main__":
    main()
