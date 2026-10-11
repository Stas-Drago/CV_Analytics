from fastapi import APIRouter, Depends, HTTPException, Query

from surveillance.api.auth import CurrentUser, require_role
from surveillance.api.routes_events import card_payload
from surveillance.config import settings
from surveillance.events.models import DecisionRequest, ShadowLabelRequest
from surveillance.storage.postgres import PostgresEventRepository

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _decide(task_id: int, action: str, label: str | None, note: str, user: CurrentUser) -> dict:
    task = PostgresEventRepository(settings().database_url).decide_task(
        task_id, action, label, note, user.user_id, user.username)
    if not task:
        raise HTTPException(status_code=409, detail={"code": "task_not_pending", "message": "Задача уже обработана или не существует."})
    return {"id": task.id, "status": task.status, "operator_label": task.operator_label}


@router.get("/high")
def high_queue(limit: int = Query(default=20, ge=1, le=100), cursor: int | None = Query(default=None, ge=1),
               status: str = Query(default="pending", pattern="^(pending|confirmed|rejected|reviewed)$"),
               _user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> dict:
    cards, next_cursor = PostgresEventRepository(settings().database_url).list_high_tasks(limit, cursor, status)
    return {"items": [card_payload(card, True) for card in cards], "next_cursor": next_cursor}


@router.post("/shadow/{task_id}/label")
def label_shadow_task(task_id: int, body: ShadowLabelRequest,
                      user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> dict:
    return _decide(task_id, "label", body.label.value, body.note, user)


def _task_for_event(event_id: str):
    repository = PostgresEventRepository(settings().database_url)
    return repository.pending_high_task_for_event(event_id)


@router.post("/{event_id}/confirm")
def confirm(event_id: str, body: DecisionRequest,
            user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> dict:
    task = _task_for_event(event_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "High-задача не найдена."})
    return _decide(task.id, "confirm", None, body.note, user)


@router.post("/{event_id}/reject")
def reject(event_id: str, body: DecisionRequest,
           user: CurrentUser = Depends(require_role("operator", "supervisor"))) -> dict:
    task = _task_for_event(event_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "High-задача не найдена."})
    return _decide(task.id, "reject", None, body.note, user)
