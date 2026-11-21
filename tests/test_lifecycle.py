from datetime import datetime

from conftest import ADMIN, PLAN, SCHEDULE, SECOND, STUDENT, THIRD, approved_club, create_draft, expect


def test_full_lifecycle_and_statistics(campus):
    client, clock = campus
    club_id = approved_club(client)
    activity_id = create_draft(client, club_id, participants=2)
    activity = f"/activities/{activity_id}"
    evaluations = f"{activity}/evaluations"
    registration = f"{activity}/registration"

    assert expect(client.get("/activities")) == []
    assert client.put(registration, headers=SECOND).status_code == 409
    body = {"confirmed": True, "plan": {**PLAN, "title": "修订后的校园编程赛", "participants": 2}}
    assert client.patch(activity, json=body, headers=SECOND).status_code == 403
    assert expect(client.patch(activity, json=body, headers=STUDENT))["plan"]["title"] == body["plan"]["title"]

    invalid_schedule = {**SCHEDULE, "starts_at": "2035-11-22T16:00:00+08:00"}
    assert client.post(f"{activity}/submit", headers=STUDENT, json=invalid_schedule).status_code == 422
    assert expect(client.post(f"{activity}/submit", headers=STUDENT, json=SCHEDULE))["status"] == "submitted"
    assert client.post(f"{activity}/review", headers=STUDENT, json={"status": "approved"}).status_code == 403
    expect(client.post(f"{activity}/review", headers=ADMIN, json={"status": "rejected"}))
    assert expect(client.get("/activities")) == []
    expect(client.post(f"{activity}/submit", headers=STUDENT, json=SCHEDULE))
    expect(client.post(f"{activity}/review", headers=ADMIN, json={"status": "approved", "priority": 2}))

    upcoming = expect(client.get("/activities"))
    assert [item["id"] for item in upcoming if item["registration_open"]] == [activity_id]
    assert upcoming[0]["schedule"]["starts_at"] == "2035-11-22T06:00:00+00:00"
    assert client.patch(activity, headers=STUDENT, json=body).status_code == 409
    assert expect(client.get("/managed/activities", headers=SECOND)) == []

    result = expect(client.put(registration, headers=STUDENT))
    assert expect(client.put(registration, headers=STUDENT)) == result
    expect(client.put(registration, headers=SECOND))
    assert client.put(registration, headers=THIRD).status_code == 409
    assert expect(client.delete(registration, headers=SECOND))["status"] == "cancelled"
    assert expect(client.get("/me/registrations", headers=SECOND))[0]["status"] == "cancelled"
    expect(client.put(registration, headers=THIRD))
    assert client.put(registration, headers=SECOND).status_code == 409
    assert client.get(f"{activity}/registrations", headers=SECOND).status_code == 403
    assert [row["student_id"] for row in expect(client.get(f"{activity}/registrations", headers=ADMIN))] == [
        "student", "student-3",
    ]
    assert client.post(f"{activity}/attendance", headers=ADMIN, json={"student_id": "student"}).status_code == 409
    assert client.post(evaluations, headers=STUDENT, json={"rating": 4}).status_code == 409
    assert client.post(f"{activity}/complete", headers=ADMIN).status_code == 409

    rule = f"{activity}/credit-rule"
    assert client.put(rule, headers=THIRD, json={"credits": "1.25"}).status_code == 403
    expect(client.put(rule, headers=ADMIN, json={"credits": "1.25"}))
    clock.now = datetime(2035, 11, 22, 6, 15)
    assert client.put(registration, headers=SECOND).status_code == 409
    assert client.delete(registration, headers=STUDENT).status_code == 409
    attendance = f"{activity}/attendance"
    assert client.post(attendance, headers=SECOND, json={"student_id": "student"}).status_code == 403
    assert client.post(attendance, headers=ADMIN, json={"student_id": "student-2"}).status_code == 409
    signed = expect(client.post(attendance, headers=ADMIN, json={"student_id": "student"}))
    clock.now = datetime(2035, 11, 22, 6, 30)
    assert expect(client.post(attendance, headers=ADMIN, json={"student_id": "student"})) == signed
    assert expect(client.get("/me/credits", headers=STUDENT))["records"] == []

    clock.now = datetime(2035, 11, 22, 7)
    completion = expect(client.post(f"{activity}/complete", headers=ADMIN))
    assert completion == {"id": activity_id, "status": "completed", "credits_awarded": 1}
    assert expect(client.post(f"{activity}/complete", headers=ADMIN)) == completion
    assert client.put(rule, headers=ADMIN, json={"credits": 2}).status_code == 409
    assert client.put(registration, headers=SECOND).status_code == 409
    records = expect(client.get("/me/credits", headers=STUDENT, params={"semester": SCHEDULE["semester"]}))
    assert records["total"] == 1.25
    assert records["by_semester"] == {SCHEDULE["semester"]: 1.25}
    assert [(item["activity_id"], item["awarded_at"]) for item in records["records"]] == [
        (activity_id, "2035-11-22T07:00:00+00:00"),
    ]
    assert expect(client.get("/me/credits", headers=SECOND))["records"] == []
    assert expect(client.get("/me/credits", headers=THIRD))["records"] == []

    assert client.post(evaluations, headers=THIRD, json={"rating": 5}).status_code == 403
    expect(client.post(evaluations, headers=STUDENT, json={"rating": 4, "comment": "流程顺畅"}), 201)
    assert client.post(evaluations, headers=STUDENT, json={"rating": 5}).status_code == 409
    review = expect(client.get(evaluations, headers=ADMIN))
    assert review["average"] == 4
    assert review["records"][0]["comment"] == "流程顺畅"

    assert client.get("/statistics", headers=STUDENT).status_code == 403
    stats = expect(client.get("/statistics", headers=ADMIN))
    assert stats == {
        "activity_count": 1, "activities_by_semester": {SCHEDULE["semester"]: 1},
        "activities_by_club": [{"id": club_id, "name": "编程社", "count": 1}],
        "activities_by_category": {"实践": 1}, "registrations": 2, "attendances": 1, "unique_students": 2,
        "credit_total": 1.25, "credits_by_semester": {SCHEDULE["semester"]: {"credits": 1.25, "records": 1}},
    }
    assert expect(client.get("/statistics", headers=ADMIN, params={"semester": "其他学期"}))["activity_count"] == 0


def test_annual_review_permissions_and_status(campus):
    client, _ = campus
    club_id = approved_club(client)
    path = f"/clubs/{club_id}/annual-reviews"
    body = {"year": 2035, "materials": "活动总结与负责人信息"}
    assert client.post(path, headers=SECOND, json=body).status_code == 403
    record = expect(client.post(path, headers=STUDENT, json=body), 201)
    assert record["status"] == "pending"
    assert client.post(path, headers=STUDENT, json=body).status_code == 409
    review = f"/annual-reviews/{record['id']}/decision"
    assert client.post(review, headers=STUDENT, json={"status": "approved"}).status_code == 403
    assert expect(client.post(review, headers=ADMIN, json={"status": "approved"}))["status"] == "approved"
    assert expect(client.get(path, headers=STUDENT))[0]["status"] == "approved"
