from dataclasses import dataclass
from datetime import UTC, datetime

from surveillance.camera.models import TrackedObject
from surveillance.model_registry import validate_model


def _iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    right_area = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


@dataclass
class _StableTrack:
    stable_id: str
    raw_id: str
    label: str
    bbox: tuple[int, int, int, int]
    first_seen_at: datetime
    last_seen_at: datetime
    last_seen_frame: int


class TrackIdStabilizer:
    """Keeps an ID through short ByteTrack dropouts without replacing ByteTrack."""

    def __init__(self, reset_missing_frames: int = 15, iou_threshold: float = 0.5) -> None:
        self.reset_missing_frames = reset_missing_frames
        self.iou_threshold = iou_threshold
        self.frame_index = 0
        self._tracks: dict[str, _StableTrack] = {}
        self._raw_to_stable: dict[str, str] = {}
        self._collision_counter = 0

    def update(self, detections: list[tuple[str, str, float, tuple[int, int, int, int]]],
               now: datetime) -> list[TrackedObject]:
        self.frame_index += 1
        self._expire_missing_tracks()
        assigned: set[str] = set()
        output: list[TrackedObject] = []
        for raw_id, label, confidence, bbox in detections:
            stable_id = self._raw_to_stable.get(raw_id)
            state = self._tracks.get(stable_id) if stable_id else None
            if not state or stable_id in assigned or state.label != label:
                state = self._find_match(label, bbox, assigned)
            if state is None:
                state = self._new_track(raw_id, label, bbox, now)
            else:
                self._raw_to_stable[raw_id] = state.stable_id
                state.raw_id, state.bbox = raw_id, bbox
                state.last_seen_at, state.last_seen_frame = now, self.frame_index
            assigned.add(state.stable_id)
            output.append(TrackedObject(state.stable_id, label, confidence, bbox,
                                        state.first_seen_at, now))
        return output

    def _expire_missing_tracks(self) -> None:
        for stable_id, state in list(self._tracks.items()):
            missing_frames = self.frame_index - state.last_seen_frame - 1
            if missing_frames >= self.reset_missing_frames:
                self._tracks.pop(stable_id)
                self._raw_to_stable = {raw: mapped for raw, mapped in self._raw_to_stable.items()
                                       if mapped != stable_id}

    def _find_match(self, label: str, bbox: tuple[int, int, int, int], assigned: set[str]) -> _StableTrack | None:
        candidates = [track for track in self._tracks.values()
                      if track.label == label and track.stable_id not in assigned]
        if not candidates:
            return None
        best = max(candidates, key=lambda track: _iou(track.bbox, bbox))
        return best if _iou(best.bbox, bbox) >= self.iou_threshold else None

    def _new_track(self, raw_id: str, label: str, bbox: tuple[int, int, int, int], now: datetime) -> _StableTrack:
        stable_id = raw_id
        if stable_id in self._tracks:
            self._collision_counter += 1
            stable_id = f"{raw_id}-{self._collision_counter}"
        state = _StableTrack(stable_id, raw_id, label, bbox, now, now, self.frame_index)
        self._tracks[stable_id] = state
        self._raw_to_stable[raw_id] = stable_id
        return state


class ByteTrackAdapter:
    """Uses the IDs produced by Ultralytics ByteTrack; no custom tracker is maintained."""

    def __init__(self, model_path: str, tracker_config: str, confidence: float, allowed_classes: set[str], device: str = "mps", manifest_path: str = "models/manifest/yolo26n.json", reset_missing_frames: int = 15, iou_threshold: float = 0.5) -> None:
        from ultralytics import YOLO

        self.manifest = validate_model(model_path, manifest_path)
        self.model = YOLO(model_path)
        self.tracker_config = tracker_config
        self.confidence = confidence
        self.allowed_classes = allowed_classes
        self.device = device
        self.stabilizer = TrackIdStabilizer(reset_missing_frames, iou_threshold)

    def update(self, frame) -> list[TrackedObject]:
        result = self.model.track(frame, persist=True, tracker=self.tracker_config,
                                  conf=self.confidence, device=self.device, verbose=False)[0]
        now = datetime.now(UTC)
        if result.boxes is None or result.boxes.id is None:
            return self.stabilizer.update([], now)
        names = result.names
        raw_detections: list[tuple[str, str, float, tuple[int, int, int, int]]] = []
        for box, raw_id in zip(result.boxes, result.boxes.id.tolist(), strict=True):
            label = str(names[int(box.cls[0])])
            if self.allowed_classes and label not in self.allowed_classes:
                continue
            x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
            raw_detections.append((str(int(raw_id)), label, float(box.conf[0]), (x1, y1, x2, y2)))
        return self.stabilizer.update(raw_detections, now)
