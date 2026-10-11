from datetime import UTC, datetime

import numpy as np

from surveillance.camera.models import TrackedObject
from surveillance.camera.overlay import draw_tracks


def test_overlay_draws_bounding_box_without_changing_source() -> None:
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    now = datetime.now(UTC)
    track = TrackedObject("7", "person", 0.88, (10, 10, 90, 60), now, now)
    preview = draw_tracks(frame, [track])
    assert np.array_equal(frame, np.zeros((80, 120, 3), dtype=np.uint8))
    assert not np.array_equal(preview, frame)
