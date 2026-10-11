from surveillance.camera.models import Detection


class YoloDetector:
    """Worker-only Ultralytics adapter with an explicit allowlist of object classes."""

    def __init__(self, model_path: str, confidence: float, allowed_classes: set[str]) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.confidence = confidence
        self.allowed_classes = allowed_classes

    def detect(self, frame) -> list[Detection]:
        result = self.model(frame, conf=self.confidence, verbose=False)[0]
        names = result.names
        detections: list[Detection] = []
        for box in result.boxes:
            label = str(names[int(box.cls[0])])
            if label not in self.allowed_classes:
                continue
            x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
            detections.append(Detection(label, float(box.conf[0]), (x1, y1, x2, y2)))
        return detections
