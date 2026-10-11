from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from surveillance.api.routes_camera import router as camera_router
from surveillance.api.routes_events import router as events_router
from surveillance.api.routes_query import router as query_router
from surveillance.api.routes_alerts import router as alerts_router
from surveillance.api.routes_auth import router as auth_router
from surveillance.api.routes_models import router as models_router
from surveillance.api.auth import CurrentUser
from surveillance.config import settings
from surveillance.security import token_hash
from surveillance.storage.postgres import PostgresEventRepository


def create_app() -> FastAPI:
    app = FastAPI(title="Surveillance API", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def authentication_and_request_id(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        public = {"/health", "/api/auth/login", "/api/auth/logout"}
        if request.url.path.startswith("/api/") and request.url.path not in public:
            cfg = settings()
            token = request.cookies.get(cfg.auth_session_cookie_name)
            if not token:
                return JSONResponse(status_code=401, content={"error": {"code": "unauthorized",
                    "message": "Требуется вход.", "request_id": request_id, "details": []}})
            user = PostgresEventRepository(cfg.database_url).session_user(
                token_hash(token), cfg.auth_idle_minutes * 60)
            if not user:
                return JSONResponse(status_code=401, content={"error": {"code": "unauthorized",
                    "message": "Сессия истекла.", "request_id": request_id, "details": []}})
            request.state.user = CurrentUser(user.id, user.username, user.role)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _error: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_failed",
            "message": "Некорректные параметры запроса.", "request_id": request.state.request_id, "details": []}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, dict) else {"message": "Запрос не выполнен."}
        return JSONResponse(status_code=error.status_code, content={"error": {
            "code": detail.get("code", "request_failed"), "message": detail.get("message", "Запрос не выполнен."),
            "request_id": request.state.request_id, "details": []}})

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _error: Exception):
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
            "message": "Внутренняя ошибка сервиса.", "request_id": request.state.request_id, "details": []}})

    app.include_router(camera_router)
    app.include_router(events_router)
    app.include_router(query_router)
    app.include_router(alerts_router)
    app.include_router(auth_router)
    app.include_router(models_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
