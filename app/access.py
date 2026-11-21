import json
import os
import re
from dataclasses import dataclass
from hmac import compare_digest
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


def identity(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials:
        token = credentials.credentials.encode()
        for configured, actor in request.app.state.accounts.items():
            if compare_digest(token, configured.encode()):
                return actor
    raise HTTPException(401, "请提供有效的演示账号令牌", headers={"WWW-Authenticate": "Bearer"})


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
