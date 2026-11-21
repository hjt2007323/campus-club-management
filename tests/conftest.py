from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.times import current_time


def headers(token):
    return {"Authorization": f"Bearer {token}"}


ADMIN = headers("test-admin")
STUDENT = headers("test-student")
SECOND = headers("test-second")
THIRD = headers("test-third")
PLAN = {
    "title": "校园编程赛", "summary": "面向初学者",
    "goals": ["练习编程"], "agenda": ["组队比赛"], "participants": 20,
    "duration_minutes": 60, "venue_capacity": 20, "equipment": ["投影"], "notes": [],
}
SCHEDULE = {
    "starts_at": "2035-11-22T14:00:00+08:00", "ends_at": "2035-11-22T15:00:00+08:00",
    "semester": "2035 秋", "category": "实践",
}


@pytest.fixture
def campus(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPUS_STUDENT_TOKEN", "test-student")
    monkeypatch.setenv("CAMPUS_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("CAMPUS_STUDENT_TOKENS", '{"student-2":"test-second","student-3":"test-third"}')
    app = create_app(f"sqlite:///{(tmp_path / 'campus.db').as_posix()}")
    clock = SimpleNamespace(now=datetime(2035, 11, 21, 0, 0))
    app.dependency_overrides[current_time] = lambda: clock.now
    with TestClient(app) as client:
        yield client, clock


def expect(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def approved_club(client, actor=STUDENT, name="编程社"):
    club = expect(client.post("/clubs", headers=actor, json={"name": name}), 201)
    expect(client.post(f"/clubs/{club['id']}/review", headers=ADMIN, json={"status": "approved"}))
    return club["id"]


def create_draft(client, club_id, actor=STUDENT, **plan_changes):
    return expect(client.post("/activities", headers=actor, json={
        "club_id": club_id, "confirmed": True, "plan": {**PLAN, **plan_changes},
    }), 201)["id"]


def approved_activity(client, club_id, actor=STUDENT, schedule=None, priority=0, **plan_changes):
    activity_id = create_draft(client, club_id, actor, **plan_changes)
    expect(client.post(f"/activities/{activity_id}/submit", headers=actor, json=schedule or SCHEDULE))
    expect(client.post(f"/activities/{activity_id}/review", headers=ADMIN, json={
        "status": "approved", "priority": priority,
    }))
    return activity_id


def create_venue(client, name, capacity=30, equipment=None):
    return expect(client.post("/venues", headers=ADMIN, json={
        "name": name, "capacity": capacity, "equipment": equipment if equipment is not None else ["投影"],
    }), 201)["id"]


def make_reservation(client, activity_id, venue_id, actor=STUDENT, approved=False):
    reservation = expect(client.post("/reservations", headers=actor, json={
        "activity_id": activity_id, "venue_id": venue_id,
    }), 201)
    if approved:
        reservation = expect(client.post(f"/reservations/{reservation['id']}/review", headers=ADMIN,
                                         json={"status": "approved"}))
    return reservation
