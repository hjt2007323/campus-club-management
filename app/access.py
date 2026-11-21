import json
import os
import re
from dataclasses import dataclass
from hmac import compare_digest
from time import monotonic
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .models import Activity, ActivitySchedule, Club

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    id: str
    role: str


def configured_accounts() -> dict[str, Actor]:
    extra_students = json.loads(os.getenv("CAMPUS_STUDENT_TOKENS", "{}"))
    if not isinstance(extra_students, dict):
        raise ValueError("CAMPUS_STUDENT_TOKENS 必须是账号到令牌的 JSON 对象")
    accounts = {}
    for role in ("admin", "student"):
        token = os.getenv(f"CAMPUS_{role.upper()}_TOKEN", "")
        if token:
            if token in accounts:
                raise ValueError("管理员与学生必须使用不同的令牌")
            accounts[token] = Actor(role, role)
    for student_id, token in extra_students.items():
        if (not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", student_id)
                or student_id in {"student", "admin"}
                or not isinstance(token, str) or not token or token in accounts):
            raise ValueError("请为每个附加学生配置独立账号和唯一令牌")
        accounts[token] = Actor(student_id, "student")
    return accounts


def account_for_token(token: str, accounts: dict[str, Actor]) -> Actor | None:
    token_bytes = token.encode()
    for configured, actor in accounts.items():
        if compare_digest(token_bytes, configured.encode()):
            return actor
    return None


def session_cookie_name(request: Request) -> str:
    default_port = 443 if request.url.scheme == "https" else 80
    return f"campus_session_{request.url.port or default_port}"


def browser_actor(request: Request) -> Actor | None:
    session_id = request.cookies.get(session_cookie_name(request))
    if session_id:
        session = request.app.state.browser_sessions.get(session_id)
        if session:
            actor, expires_at = session
            if expires_at > monotonic():
                return actor
            request.app.state.browser_sessions.pop(session_id, None)
    return None


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "请从当前应用页面操作")


async def identity(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials:
        actor = account_for_token(credentials.credentials, request.app.state.accounts)
    else:
        actor = browser_actor(request)
        if actor and request.method not in {"GET", "HEAD", "OPTIONS"}:
            require_same_origin(request)
    if actor:
        return actor
    raise HTTPException(401, "请先登录或提供有效的账号令牌", headers={"WWW-Authenticate": "Bearer"})


SignedIn = Annotated[Actor, Depends(identity)]


def require_admin(actor: SignedIn):
    if actor.role != "admin":
        raise HTTPException(403, "此操作需要管理员权限")
    return actor


def require_student(actor: SignedIn):
    if actor.role != "student":
        raise HTTPException(403, "此操作需要学生权限")
    return actor


Admin = Annotated[Actor, Depends(require_admin)]
Student = Annotated[Actor, Depends(require_student)]


def get_or_404(db: Session, model, identifier, message: str):
    record = db.get(model, identifier)
    if record is None:
        raise HTTPException(404, message)
    return record


def owned_club(db: Session, club_id: int, actor: Actor):
    club = get_or_404(db, Club, club_id, "社团不存在")
    if actor.role != "student" or club.owner != actor.id:
        raise HTTPException(403, "此操作需要该社团负责人的权限")
    if club.status != "approved":
        raise HTTPException(409, "社团尚未通过审核")
    return club


def get_activity(db: Session, activity_id: int) -> Activity:
    return get_or_404(db, Activity, activity_id, "活动不存在")


def get_schedule(db: Session, activity_id: int) -> ActivitySchedule:
    schedule = db.get(ActivitySchedule, activity_id)
    if schedule is None:
        raise HTTPException(409, "活动尚未安排时间")
    return schedule
