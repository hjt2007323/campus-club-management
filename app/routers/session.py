from secrets import token_urlsafe
from time import monotonic

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..access import account_for_token, require_same_origin, session_cookie_name

router = APIRouter(prefix="/session", include_in_schema=False)
SESSION_SECONDS = 8 * 60 * 60
DEMO_PROFILES = (
    {"id": "student", "name": "编程社负责人", "detail": "策划活动、提交申请、预约场地"},
    {"id": "network-club", "name": "网络技术社负责人", "detail": "管理本社活动，也可以报名参加其他活动"},
    {"id": "admin", "name": "校方管理员", "detail": "审核申请、协调场地、查看统计"},
)


class SignIn(BaseModel):
    account_id: str | None = Field(None, min_length=1, max_length=40)
    token: str | None = Field(None, min_length=1, max_length=512)


@router.get("/options")
async def options(request: Request):
    if not request.app.state.demo_login:
        return {"mode": "token", "accounts": []}
    available = {actor.id for actor in request.app.state.accounts.values()}
    return {"mode": "demo", "accounts": [profile for profile in DEMO_PROFILES if profile["id"] in available]}


@router.post("")
async def sign_in(body: SignIn, request: Request, response: Response):
    require_same_origin(request)
    accounts = request.app.state.accounts
    if body.account_id is not None and body.token is not None:
        raise HTTPException(422, "请选择一种登录方式")
    if body.account_id is not None:
        if not request.app.state.demo_login:
            raise HTTPException(403, "当前环境需要使用账号令牌登录")
        allowed_ids = {profile["id"] for profile in DEMO_PROFILES}
        if body.account_id not in allowed_ids:
            raise HTTPException(404, "该演示账号不可用")
        actor = next((item for item in accounts.values() if item.id == body.account_id), None)
    else:
        actor = account_for_token(body.token or "", accounts)
    if actor is None:
        raise HTTPException(401, "请选择可用账号或输入有效令牌")

    name = session_cookie_name(request)
    sessions = request.app.state.browser_sessions
    now = monotonic()
    for session_id, (_, expires_at) in list(sessions.items()):
        if expires_at <= now:
            sessions.pop(session_id)
    sessions.pop(request.cookies.get(name), None)
    session_id = token_urlsafe(32)
    sessions[session_id] = (actor, now + SESSION_SECONDS)
    response.set_cookie(name, session_id, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"id": actor.id, "role": actor.role}


@router.delete("")
async def sign_out(request: Request, response: Response):
    require_same_origin(request)
    name = session_cookie_name(request)
    request.app.state.browser_sessions.pop(request.cookies.get(name), None)
    response.delete_cookie(name, httponly=True, secure=request.url.scheme == "https", samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"status": "signed_out"}
