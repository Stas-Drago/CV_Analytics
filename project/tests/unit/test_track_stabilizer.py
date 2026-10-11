from datetime import UTC, datetime, timedelta

from surveillance.camera.tracker import TrackIdStabilizer


def detection(raw_id: str, bbox: tuple[int, int, int, int] = (10, 10, 50, 50)):
    return [(raw_id, "person", 0.9, bbox)]


def test_new_bytetrack_id_keeps_stable_id_after_short_dropout() -> None:
    stabilizer = TrackIdStabilizer(reset_missing_frames=15, iou_threshold=0.5)
    now = datetime.now(UTC)
    first = stabilizer.update(detection("7"), now)[0]
    stabilizer.update([], now + timedelta(milliseconds=30))
    stabilizer.update([], now + timedelta(milliseconds=60))
    reassigned = stabilizer.update(detection("19", (11, 11, 51, 51)), now + timedelta(milliseconds=90))[0]
    assert reassigned.track_id == "7"
    assert reassigned.first_seen_at == first.first_seen_at


def test_new_id_is_created_after_fifteen_missing_frames() -> None:
    stabilizer = TrackIdStabilizer(reset_missing_frames=15, iou_threshold=0.5)
    now = datetime.now(UTC)
    first = stabilizer.update(detection("7"), now)[0]
    for frame in range(15):
        stabilizer.update([], now + timedelta(milliseconds=30 * (frame + 1)))
    after_gap = stabilizer.update(detection("19"), now + timedelta(milliseconds=240))[0]
    assert after_gap.track_id == "19"
    assert after_gap.first_seen_at != first.first_seen_at


def test_nearby_same_class_objects_do_not_merge_without_iou() -> None:
    stabilizer = TrackIdStabilizer(reset_missing_frames=15, iou_threshold=0.5)
    now = datetime.now(UTC)
    first = stabilizer.update(detection("7"), now)[0]
    second = stabilizer.update(detection("19", (100, 100, 140, 140)), now + timedelta(milliseconds=30))[0]
    assert second.track_id != first.track_id
