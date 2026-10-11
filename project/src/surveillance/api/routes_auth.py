from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response

from surveillance.api.auth import CurrentUser
from surveillance.config import settings
from surveillance.events.models import LoginRequest
from surveillance.security import new_session_token, token_hash
from surveillance.storage.postgres import PostgresEventRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict:
    cfg = settings()
    repository = PostgresEventRepository(cfg.database_url)
    user = repository.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "message": "Неверный логин или пароль."})
    token = new_session_token()
    now = datetime.now(UTC)
    repository.create_session(token_hash(token), user.id, now + timedelta(hours=cfg.auth_session_hours),
                              now + timedelta(minutes=cfg.auth_idle_minutes))
    response.set_cookie(cfg.auth_session_cookie_name, token, httponly=True, secure=cfg.auth_cookie_secure,
                        samesite="strict", max_age=cfg.auth_session_hours * 3600, path="/")
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    cfg = settings()
    token = request.cookies.get(cfg.auth_session_cookie_name)
    if token:
        PostgresEventRepository(cfg.database_url).revoke_session(token_hash(token))
    response.delete_cookie(cfg.auth_session_cookie_name, path="/")
    return {"status": "logged_out"}


@router.get("/me")
def me(request: Request) -> dict:
    user: CurrentUser | None = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Требуется вход."})
    return {"username": user.username, "role": user.role}
