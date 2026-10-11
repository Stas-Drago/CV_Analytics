"""Rendering for the annotated live preview; persisted event images stay untouched."""

import hashlib

import cv2

from surveillance.camera.models import TrackedObject


def _color(label: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    return (int(digest[0]), int(digest[1]), int(digest[2]))


def draw_tracks(frame, tracks: list[TrackedObject]):
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    for track in tracks:
        x1, y1, x2, y2 = track.bbox
        x1, x2 = max(0, min(x1, width - 1)), max(0, min(x2, width - 1))
        y1, y2 = max(0, min(y1, height - 1)), max(0, min(y2, height - 1))
        color = _color(track.label)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        caption = f"{track.label} {track.confidence:.0%} #{track.track_id}"
        baseline_y = max(18, y1 - 6)
        (text_width, text_height), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(canvas, (x1, baseline_y - text_height - 5), (x1 + text_width + 4, baseline_y + 3), color, -1)
        cv2.putText(canvas, caption, (x1 + 2, baseline_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas
