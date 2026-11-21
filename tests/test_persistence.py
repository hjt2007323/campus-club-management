import json
import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import PLAN, STUDENT, expect


def test_first_batch_database_remains_usable(tmp_path, monkeypatch):
    db_path = tmp_path / "first-batch.db"
    with closing(sqlite3.connect(db_path)) as database, database:
        database.executescript("""
            CREATE TABLE clubs (
                id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, owner VARCHAR NOT NULL, status VARCHAR NOT NULL
            );
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id),
                plan_json VARCHAR NOT NULL, status VARCHAR NOT NULL
            );
        """)
        database.execute("INSERT INTO clubs VALUES (1, '原社团', 'student', 'approved')")
        database.execute("INSERT INTO activities VALUES (1, 1, ?, 'draft')", (json.dumps(PLAN),))

    monkeypatch.setenv("CAMPUS_STUDENT_TOKEN", "test-student")
    monkeypatch.setenv("CAMPUS_STUDENT_TOKENS", "{}")
    app = create_app(f"sqlite:///{db_path.as_posix()}")
    with TestClient(app) as client:
        activities = expect(client.get("/managed/activities", headers=STUDENT))
        assert [(row["id"], row["status"], row["schedule"]) for row in activities] == [(1, "draft", None)]
        result = expect(client.patch("/activities/1", headers=STUDENT, json={
            "confirmed": True, "plan": {**PLAN, "title": "沿用旧草稿"},
        }))
        assert result["plan"]["title"] == "沿用旧草稿"
    with TestClient(create_app(f"sqlite:///{db_path.as_posix()}")) as client:
        assert expect(client.get("/managed/activities", headers=STUDENT))[0]["plan"]["title"] == "沿用旧草稿"
