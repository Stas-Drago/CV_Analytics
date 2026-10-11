from fastapi import APIRouter, Depends, HTTPException

from surveillance.api.auth import CurrentUser, require_role
from surveillance.config import settings
from surveillance.events.models import RevokeModelRequest
from surveillance.storage.postgres import PostgresEventRepository

router = APIRouter(prefix="/api/models/danger", tags=["models"])


def _release(row) -> dict:
    return {"id": row.id, "version": row.version, "checksum": row.checksum, "status": row.status,
            "mapping_version": row.mapping_version, "threshold_policy_version": row.threshold_policy_version,
            "dataset_version": row.dataset_version, "approved_by": row.approved_by,
            "approved_at": None if not row.approved_at else row.approved_at.isoformat(),
            "revoke_reason": row.revoke_reason}


@router.get("")
def releases(_user: CurrentUser = Depends(require_role("supervisor"))) -> dict:
    return {"items": [_release(row) for row in PostgresEventRepository(settings().database_url).list_model_releases()]}


@router.post("/{release_id}/approve")
def approve(release_id: int, user: CurrentUser = Depends(require_role("supervisor"))) -> dict:
    release = PostgresEventRepository(settings().database_url).approve_model_release(release_id, user.username)
    if not release:
        raise HTTPException(status_code=409, detail={"code": "approval_requirements_not_met", "message": "Релиз не соответствует критериям shadow mode."})
    return _release(release)


@router.post("/{release_id}/revoke")
def revoke(release_id: int, body: RevokeModelRequest, user: CurrentUser = Depends(require_role("supervisor"))) -> dict:
    release = PostgresEventRepository(settings().database_url).revoke_model_release(release_id, user.username, body.reason)
    if not release:
        raise HTTPException(status_code=409, detail={"code": "release_not_approved", "message": "Релиз не утверждён."})
    return _release(release)
