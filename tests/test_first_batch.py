import os
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai
from app.main import create_app

STUDENT = {"Authorization": "Bearer test-student"}
ADMIN = {"Authorization": "Bearer test-admin"}
PLAN = {
    "title": "校园编程赛", "summary": "面向初学者",
    "goals": ["练习编程"], "agenda": ["组队比赛"], "participants": 20,
    "duration_minutes": 90, "venue_capacity": 20, "equipment": ["投影"], "notes": [],
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPUS_STUDENT_TOKEN", "test-student")
    monkeypatch.setenv("CAMPUS_ADMIN_TOKEN", "test-admin")
    database = tmp_path / "test.db"
    return f"sqlite:///{database.as_posix()}", database


def approve_club(client):
    result = client.post("/clubs", headers=STUDENT, json={"name": "编程社"})
    assert result.status_code == 201
    club_id = result.json()["id"]
    assert result.json()["status"] == "pending"
    assert client.get("/clubs").json() == []
    path = f"/clubs/{club_id}/review"
    assert client.post(path, headers=STUDENT, json={"status": "approved"}).status_code == 403
    draft = {"club_id": club_id, "confirmed": True, "plan": PLAN}
    assert client.post("/activities", headers=STUDENT, json=draft).status_code == 409
    assert client.post(path, headers=ADMIN, json={"status": "approved"}).status_code == 200
    assert client.post(path, headers=ADMIN, json={"status": "rejected"}).status_code == 409
    return club_id


def verify_ai_flow(client, database, club_id):
    response = client.post(f"/clubs/{club_id}/ai-plan", headers=STUDENT,
                           json={"description": "为20名学生规划一场90分钟的校园编程赛，需要投影。"})
    assert response.status_code == 200, response.json()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM activities").fetchone() == (0,)
    plan = response.json()
    plan["title"] = "人工确认后的活动标题"
    draft = {"club_id": club_id, "plan": plan}
    assert client.post("/activities", headers=STUDENT, json=draft).status_code == 422
    result = client.post("/activities", headers=STUDENT, json={**draft, "confirmed": True})
    assert result.status_code == 201
    assert result.json()["status"] == "draft"
    assert result.json()["plan"]["title"] == plan["title"]


def test_first_batch(project, monkeypatch):
    url, database = project

    def response(*args, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", args[0]), json={
            "choices": [{"message": {"content": ai.Plan(**PLAN).model_dump_json()}}]
        })

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai.httpx, "post", response)
    with TestClient(create_app(url)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/clubs", json={"name": "匿名"}).status_code == 401
        club_id = approve_club(client)
        verify_ai_flow(client, database, club_id)
    with TestClient(create_app(url)) as client:
        assert client.get("/clubs").json()[0]["id"] == club_id
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT status FROM activities").fetchone() == ("draft",)


@pytest.mark.parametrize("failure, expected", [("timeout", 504), ("invalid", 502)])
def test_ai_failure(project, monkeypatch, failure, expected):
    url, database = project

    def response(*args, **kwargs):
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout")
        return httpx.Response(200, request=httpx.Request("POST", args[0]), json={
            "choices": [{"message": {"content": "{}"}}]
        })

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai.httpx, "post", response)
    with TestClient(create_app(url)) as client:
        club_id = approve_club(client)
        result = client.post(f"/clubs/{club_id}/ai-plan", headers=STUDENT,
                             json={"description": "校园编程赛"})
        assert result.status_code == expected
        assert client.get("/health").status_code == 200
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM activities").fetchone() == (0,)


@pytest.mark.skipif(os.getenv("RUN_DEEPSEEK_LIVE") != "1", reason="需要显式启用真实计费调用")
def test_deepseek_live(project):
    url, database = project
    with TestClient(create_app(url)) as client:
        verify_ai_flow(client, database, approve_club(client))
