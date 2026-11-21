from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from conftest import (
    ADMIN, SCHEDULE, SECOND, STUDENT, THIRD, approved_activity, approved_club, create_venue, expect,
    make_reservation,
)


def test_venue_workflow_checks_capacity_equipment_and_time(campus):
    client, _ = campus
    club = approved_club(client)
    second_club = approved_club(client, SECOND, "摄影社")
    event = approved_activity(client, club)
    other = approved_activity(client, second_club, SECOND)
    adjacent = approved_activity(client, second_club, SECOND, schedule={
        **SCHEDULE, "starts_at": "2035-11-22T07:00:00Z", "ends_at": "2035-11-22T08:00:00Z",
    })
    assert client.post("/venues", headers=SECOND, json={"name": "新馆", "capacity": 50}).status_code == 403
    original = create_venue(client, "第一教室")
    too_small = create_venue(client, "小教室", capacity=19)
    no_projector = create_venue(client, "无投影教室", equipment=["白板"])
    alternative = create_venue(client, "第二教室")
    assert len(expect(client.get("/venues"))) == 4
    assert expect(client.patch(f"/venues/{alternative}", headers=ADMIN, json={
        "name": "第二教室", "capacity": 35, "equipment": ["白板", "投影"],
    }))["capacity"] == 35

    for room in (too_small, no_projector):
        assert client.post("/reservations", headers=STUDENT, json={
            "activity_id": event, "venue_id": room,
        }).status_code == 409
    assert client.post("/reservations", headers=SECOND, json={
        "activity_id": event, "venue_id": original,
    }).status_code == 403
    booking = make_reservation(client, event, original)
    assert booking["status"] == "pending"
    assert client.post("/reservations", headers=SECOND, json={
        "activity_id": other, "venue_id": original,
    }).status_code == 409
    assert client.patch(f"/venues/{original}", headers=ADMIN, json={
        "name": "第一教室", "capacity": 18, "equipment": ["投影"],
    }).status_code == 409
    assert [room["id"] for room in expect(client.get(f"/activities/{other}/venue-options", headers=SECOND))] == [
        alternative,
    ]

    review = f"/reservations/{booking['id']}/review"
    assert client.post(review, headers=STUDENT, json={"status": "approved"}).status_code == 403
    assert expect(client.post(review, headers=ADMIN, json={"status": "approved"}))["status"] == "approved"
    assert [room["id"] for room in expect(client.get(
        f"/reservations/{booking['id']}/alternatives", headers=STUDENT,
    ))] == [alternative]
    assert make_reservation(client, adjacent, original, SECOND, approved=True)["status"] == "approved"
    assert expect(client.get("/activities"))[0]["venue_name"] == "第一教室"


def test_concurrent_overlapping_requests_only_one_succeeds(campus):
    client, _ = campus
    first = approved_activity(client, approved_club(client))
    second = approved_activity(client, approved_club(client, SECOND), SECOND)
    venue_id = create_venue(client, "礼堂")
    barrier = Barrier(2, timeout=10)

    def reserve(activity_id, actor):
        barrier.wait()
        return client.post("/reservations", headers=actor, json={
            "activity_id": activity_id, "venue_id": venue_id,
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_request = executor.submit(reserve, first, STUDENT)
        second_request = executor.submit(reserve, second, SECOND)
        assert sorted([first_request.result(), second_request.result()]) == [201, 409]
    assert len(expect(client.get("/reservations", headers=ADMIN))) == 1


def test_concurrent_registration_does_not_overbook(campus):
    client, _ = campus
    activity = approved_activity(client, approved_club(client), participants=1)
    barrier = Barrier(2, timeout=10)

    def register(actor):
        barrier.wait()
        return client.put(f"/activities/{activity}/registration", headers=actor).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = [executor.submit(register, actor) for actor in (SECOND, THIRD)]
        assert sorted(request.result() for request in requests) == [200, 409]
    assert len(expect(client.get(f"/activities/{activity}/registrations", headers=ADMIN))) == 1


def test_requisition_preview_and_atomic_manual_confirmation(campus):
    client, _ = campus
    flexible = approved_activity(client, approved_club(client), equipment=["投影"])
    restricted = approved_activity(client, approved_club(client, SECOND), SECOND, equipment=["网络"], priority=3)
    original_first = create_venue(client, "被征用一室")
    original_second = create_venue(client, "被征用二室", equipment=["网络"])
    shared = create_venue(client, "投影网络教室", equipment=["投影", "网络"])
    flexible_only = create_venue(client, "投影教室")
    create_venue(client, "小教室", capacity=18, equipment=["投影", "网络"])
    first = make_reservation(client, flexible, original_first, approved=True)
    second = make_reservation(client, restricted, original_second, SECOND, approved=True)

    body = {
        "venue_ids": [original_first, original_second],
        "starts_at": SCHEDULE["starts_at"], "ends_at": SCHEDULE["ends_at"], "reason": "学校临时考试",
    }
    assert client.post("/venue-blocks", headers=STUDENT, json=body).status_code == 403
    block = expect(client.post("/venue-blocks", headers=ADMIN, json=body), 201)
    assert block["affected_reservation_ids"] == [first["id"], second["id"]]
    preview = expect(client.get(f"/venue-blocks/{block['id']}/coordination", headers=ADMIN))
    assert {row["id"]: [venue["id"] for venue in row["candidates"]] for row in preview["affected"]} == {
        first["id"]: [shared, flexible_only], second["id"]: [shared],
    }
    assert all(activity["venue_name"] is None for activity in expect(client.get("/activities")))
    path = f"/venue-blocks/{block['id']}/coordinate"

    def assignments(venue_id):
        return {"assignments": [
            {"reservation_id": first["id"], "venue_id": venue_id},
            {"reservation_id": second["id"], "venue_id": shared},
        ]}

    assert client.post(path, headers=SECOND, json=assignments(flexible_only)).status_code == 403
    assert client.post(path, headers=ADMIN, json=assignments(shared)).status_code == 409
    assert [row["status"] for row in expect(client.get("/reservations", headers=ADMIN))] == [
        "affected", "affected",
    ]
    later_event = approved_activity(client, approved_club(client, THIRD), THIRD)
    later_booking = make_reservation(client, later_event, flexible_only, THIRD)
    assert client.post(path, headers=ADMIN, json=assignments(flexible_only)).status_code == 409
    expect(client.post(f"/reservations/{later_booking['id']}/review", headers=ADMIN,
                       json={"status": "rejected"}))

    result = expect(client.post(path, headers=ADMIN, json=assignments(flexible_only)))
    assert result["unassigned_reservation_ids"] == []
    assert [row["venue_id"] for row in result["confirmed"]] == [flexible_only, shared]
    assert [row["starts_at"] for row in result["confirmed"]] == [first["starts_at"], second["starts_at"]]
    assert [row["replaces_id"] for row in result["confirmed"]] == [first["id"], second["id"]]
    assert client.post(path, headers=ADMIN, json=assignments(flexible_only)).status_code == 409
