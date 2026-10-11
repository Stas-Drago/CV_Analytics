import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from surveillance.camera.preview import RedisCameraPreview
from surveillance.config import settings


router = APIRouter(prefix="/api/camera", tags=["camera"])


@router.get("/status")
def status(request: Request) -> dict:
    return RedisCameraPreview(settings().redis_url).status()


@router.get("/stream")
def stream(request: Request) -> StreamingResponse:
    preview = RedisCameraPreview(settings().redis_url)

    def frames():
        while True:
            image = preview.frame()
            if image is None:
                time.sleep(0.1)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")
