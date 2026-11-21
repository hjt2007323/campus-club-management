import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from .access import SignedIn, browser_actor, configured_accounts
from .database import Db, sqlite_engine
from .models import Base
from .routers import activities, clubs, outcomes, session, venues

logger = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent


def create_app(database_url: str | None = None, *, demo_login: bool = False) -> FastAPI:
    engine = sqlite_engine(database_url or os.getenv("DATABASE_URL", "sqlite:///campus.db"))

    @asynccontextmanager
    async def lifespan(app):
        try:
            app.state.accounts = configured_accounts()
            app.state.browser_sessions = {}
            app.state.engine = engine
            Base.metadata.create_all(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="高校社团活动全流程管理系统", lifespan=lifespan)
    app.state.demo_login = demo_login
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    for router in (session.router, clubs.router, activities.router, venues.router, outcomes.router):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def homepage(request: Request, guest: bool = False):
        headers = {"Cache-Control": "no-store"}
        if demo_login and not guest and browser_actor(request) is None:
            return RedirectResponse("/login", status_code=303, headers=headers)
        return FileResponse(APP_DIR / "index.html", headers=headers)

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return FileResponse(APP_DIR / "login.html", headers={"Cache-Control": "no-store"})

    @app.get("/health")
    def health(db: Db):
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/me")
    def me(actor: SignedIn):
        return {"id": actor.id, "role": actor.role}

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, exc: SQLAlchemyError):
        if isinstance(exc, IntegrityError):
            return JSONResponse(status_code=409, content={"detail": "记录重复或已发生变化，请刷新后重试"})
        if isinstance(exc, OperationalError) and "database is locked" in str(exc.orig):
            return JSONResponse(status_code=503, content={"detail": "数据库正在处理其他操作，请重试"})
        logger.error("Database error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "数据库操作失败"})

    return app


app = create_app()
