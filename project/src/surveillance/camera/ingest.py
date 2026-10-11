"""Local-camera worker: preview → YOLO/ByteTrack → PostgreSQL event + outbox."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import cv2

from surveillance.camera.crop import crop_jpeg
from surveillance.camera.deduplication import RedisPresenceDeduplicator, deduplication_key
from surveillance.camera.overlay import draw_tracks
from surveillance.camera.preview import RedisCameraPreview
from surveillance.camera.source import LocalCamera
from surveillance.camera.tracker import ByteTrackAdapter
from surveillance.config import Settings
from surveillance.events.models import DetectedEvent
from surveillance.events.service import EventService
from surveillance.storage.postgres import PostgresEventRepository


def build_camera(config: Settings) -> LocalCamera:
    return LocalCamera(config.camera_device_index, config.camera_width, config.camera_height)


def run(config: Settings) -> None:
    """Run on the host that owns the physical camera, not in the FastAPI process."""
    labels = {value.strip() for value in config.yolo_classes.split(",") if value.strip()}
    camera = build_camera(config)
    preview = RedisCameraPreview(config.redis_url)
    tracker = ByteTrackAdapter(config.yolo_model_path, config.tracker_config,
                               config.yolo_confidence_threshold, labels, config.yolo_device,
                               config.yolo_model_manifest, config.tracker_id_reset_missing_frames,
                               config.tracker_id_iou_threshold)
    events = EventService(PostgresEventRepository(config.database_url))
    dedupe = RedisPresenceDeduplicator(config.redis_url, config.event_presence_timeout_seconds)
    preview.publish_status({"state": "starting", "camera_id": "local-camera", "model": Path(config.yolo_model_path).name})
    camera.start()
    sequence = 0
    failure = ""
    try:
        while camera.connected:
            next_frame = camera.next_frame(sequence)
            if next_frame is None:
                continue
            sequence, frame = next_frame
            now = datetime.now(UTC)
            tracks = tracker.update(frame)
            annotated = draw_tracks(frame, tracks)
            ok, preview_jpeg = cv2.imencode(
                ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, config.preview_jpeg_quality]
            )
            if ok:
                preview.publish_frame(preview_jpeg.tobytes())
            preview.publish_status({
                "state": "online", "camera_id": "local-camera", "frame_sequence": sequence,
                "detections": len(tracks), "model": Path(config.yolo_model_path).name, **camera.status(),
            })
            for track in tracks:
                if (now - track.first_seen_at).total_seconds() < config.event_min_track_age_seconds:
                    continue
                if not dedupe.allow("local-camera", track, now):
                    continue
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.preview_jpeg_quality])
                if not ok:
                    continue
                events.record(DetectedEvent(
                    event_id=uuid4(), camera_id="local-camera", track_id=track.track_id,
                    occurred_at=now, object_type=track.label, confidence=track.confidence,
                    bbox=list(track.bbox), frame_jpeg=encoded.tobytes(),
                    object_crop_jpeg=crop_jpeg(frame, track.bbox, config.preview_jpeg_quality),
                    model_version=config.yolo_model_path,
                    deduplication_key=deduplication_key("local-camera", track),
                ))
        failure = camera.error or "Поток камеры остановлен"
    except Exception as error:
        failure = str(error)
        preview.publish_status({"state": "error", "camera_id": "local-camera", "error": failure})
        raise
    finally:
        camera.stop()
        preview.publish_status({"state": "offline", "camera_id": "local-camera", "error": failure or camera.error})
