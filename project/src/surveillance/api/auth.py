from dataclasses import dataclass
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    username: str
    role: str


ROLE_ORDER = {"viewer": 1, "operator": 2, "supervisor": 3}


def current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Требуется вход."})
    return user


def require_role(*roles: str):
    def dependency(request: Request) -> CurrentUser:
        user = current_user(request)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Недостаточно прав."})
        return user
    return dependency
