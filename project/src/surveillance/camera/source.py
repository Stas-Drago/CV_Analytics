from __future__ import annotations

import threading
import time

import cv2


class LocalCamera:
    """Single owner of a local camera device; it neither records video nor serves HTTP."""

    def __init__(self, device_index: int, width: int, height: int) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self._capture: cv2.VideoCapture | None = None
        self._frame = None
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._sequence = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error = ""

    @property
    def connected(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        backend = cv2.CAP_AVFOUNDATION if hasattr(cv2, "CAP_AVFOUNDATION") else cv2.CAP_ANY
        capture = cv2.VideoCapture(self.device_index, backend)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not capture.isOpened():
            capture.release()
            self.error = f"Не удалось открыть локальную камеру {self.device_index}"
            return
        self._capture = capture
        self.error = ""
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name="local-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._capture:
            self._capture.release()
        self._capture = None

    def latest_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def next_frame(self, after_sequence: int, timeout: float = 1.0):
        """Wait for one newer frame, preventing repeated inference on the same image."""
        with self._new_frame:
            self._new_frame.wait_for(lambda: self._sequence > after_sequence or self._stop.is_set(), timeout)
            if self._sequence <= after_sequence or self._frame is None:
                return None
            return self._sequence, self._frame.copy()

    def latest_jpeg(self, quality: int = 80) -> bytes | None:
        frame = self.latest_frame()
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return encoded.tobytes() if ok else None

    def status(self) -> dict[str, object]:
        return {"connected": self.connected, "device": self.device_index,
                "width": self.width, "height": self.height, "error": self.error}

    def _read_loop(self) -> None:
        while not self._stop.is_set() and self._capture:
            ok, frame = self._capture.read()
            if not ok or frame is None:
                self.error = "Поток камеры прерван"
                if self._capture:
                    self._capture.release()
                self._capture = None
                with self._new_frame:
                    self._new_frame.notify_all()
                return
            with self._new_frame:
                self._frame = frame.copy()
                self._sequence += 1
                self._new_frame.notify_all()
            time.sleep(0.001)
