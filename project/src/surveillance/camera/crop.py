import cv2


def crop_jpeg(frame, bbox: tuple[int, int, int, int], quality: int = 80) -> bytes | None:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    ok, encoded = cv2.imencode(".jpg", frame[y1:y2, x1:x2], [cv2.IMWRITE_JPEG_QUALITY, quality])
    return encoded.tobytes() if ok else None
