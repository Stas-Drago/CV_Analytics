import base64
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from surveillance.api.auth import CurrentUser, require_role
from surveillance.config import settings
from surveillance.storage.postgres import PostgresEventRepository

router = APIRouter(prefix="/api/events", tags=["events"])


def _cursor_decode(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        timestamp, event_id = json.loads(decoded)
        return datetime.fromisoformat(timestamp), str(event_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_cursor", "message": "Некорректный курсор."})


def _cursor_encode(value: tuple[datetime, str] | None) -> str | None:
    if not value:
        return None
    return base64.urlsafe_b64encode(json.dumps([value[0].isoformat(), value[1]]).encode()).decode().rstrip("=")


def card_payload(card: dict, media_allowed: bool) -> dict:
    event, assessment, task = card["event"], card["assessment"], card["task"]
    return {
            "event_id": event.event_id, "camera_id": event.camera_id,
            "occurred_at": event.occurred_at.isoformat(), "object_type": event.object_type,
            "confidence": event.confidence, "description": event.description,
            "risk_level": event.risk_level, "alert_status": event.alert_status,
            "crop_url": f"/api/events/{event.event_id}/crop" if media_allowed and event.object_crop else None,
            "frame_url": f"/api/events/{event.event_id}/frame" if media_allowed else None,
            "risk": None if not assessment else {
                "probabilities": assessment.probabilities, "model_version": assessment.model_version,
                "mapping_version": assessment.mapping_version,
                "threshold_policy_version": assessment.threshold_policy_version, "mode": assessment.mode,
            },
            "shadow_task": None if not task else {
                "id": task.id, "status": task.status, "operator_label": task.operator_label,
                "operator_note": task.operator_note,
            },
    }


@router.get("")
def list_events(limit: int = Query(default=10, ge=1, le=100), cursor: str | None = None,
                user: CurrentUser = Depends(require_role("viewer", "operator", "supervisor"))) -> dict:
    cards, next_cursor = PostgresEventRepository(settings().database_url).list_events_page(limit, _cursor_decode(cursor))
    return {"items": [card_payload(card, user.role in {"operator", "supervisor"}) for card in cards],
            "next_cursor": _cursor_encode(next_cursor)}


@router.get("/{event_id}/frame")
def event_frame(event_id: str, _user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> Response:
    event = PostgresEventRepository(settings().database_url).get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return Response(event.frame_data, media_type=event.frame_media_type)


@router.get("/{event_id}/crop")
def event_crop(event_id: str, _user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> Response:
    event = PostgresEventRepository(settings().database_url).get_event(event_id)
    if not event or not event.object_crop:
        raise HTTPException(status_code=404, detail="Object crop not found")
    return Response(event.object_crop, media_type=event.frame_media_type)
