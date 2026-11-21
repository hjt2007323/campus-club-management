from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session


def sqlite_engine(url: str):
    engine = create_engine(url, connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def database(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


Db = Annotated[Session, Depends(database)]


@contextmanager
def write_transaction(db: Session):
    # Serialize writes before reading capacity, attendance, or room availability.
    with db.begin():
        db.execute(text("BEGIN IMMEDIATE"))
        yield
