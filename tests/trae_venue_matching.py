from datetime import datetime

import pytest

from app.services.venue_matching import VenueMatchRequest, recommend_venues
from conftest import (
    ADMIN, SCHEDULE, SECOND, approved_activity, approved_club, create_venue, expect, make_reservation,
)


def request(reservation_id, candidates, *, start=9, end=10, priority=0):
    return VenueMatchRequest(
        reservation_id, datetime(2035, 11, 22, start), datetime(2035, 11, 22, end),
        priority, tuple(candidates),
    )


def test_overlap_maximum_then_priority_and_application_order():
    flexible = request(1, [1, 2])
    only_room_one = request(2, [1])
    no_candidate = request(3, [], priority=5)
    assert recommend_venues([flexible, only_room_one, no_candidate]) == {1: 2, 2: 1}
    assert recommend_venues([only_room_one, no_candidate, flexible]) == {1: 2, 2: 1}

    later_but_higher_priority = request(3, [1], priority=3)
    assert recommend_venues([only_room_one, later_but_higher_priority]) == {3: 1}
    assert recommend_venues([request(5, [1]), only_room_one]) == {2: 1}

    # One higher-priority event uses the room for both shorter activities.
    # Keeping two events takes precedence over keeping one higher-priority one.
    assert recommend_venues([
        request(1, [1], start=9, end=11, priority=5),
        request(2, [1], start=9, end=10),
        request(3, [1], start=10, end=11),
    ]) == {2: 1, 3: 1}


@pytest.mark.parametrize("requests, expected", [
    ([], {}),
    ([request(1, [])], {}),
    ([request(1, [2, 1])], {1: 1}),
    ([request(1, [1]), request(2, [1], start=10, end=11)], {1: 1, 2: 1}),
    ([request(1, [3, 2]), request(2, [3, 2])], {1: 2, 2: 3}),
])
def test_boundaries_and_stable_choices(requests, expected):
    assert recommend_venues(requests) == expected


def test_earlier_activity_takes_precedence_over_smaller_room_id():
    flexible = request(1, [1, 2])
    earlier = request(2, [1])
    later = request(3, [2])
    assert recommend_venues([flexible, earlier, later]) == {1: 2, 2: 1}


def test_requisition_proposal_uses_the_matcher_and_requires_admin_confirmation(campus):
    client, _ = campus
    flexible = approved_activity(client, approved_club(client), equipment=["投影"])
    restricted = approved_activity(client, approved_club(client, SECOND), SECOND, equipment=["网络"])
    originals = [
        create_venue(client, "原投影教室"),
        create_venue(client, "原网络教室", equipment=["网络"]),
    ]
    shared = create_venue(client, "投影网络教室", equipment=["投影", "网络"])
    flexible_only = create_venue(client, "替补投影教室")
    first = make_reservation(client, flexible, originals[0], approved=True)
    second = make_reservation(client, restricted, originals[1], SECOND, approved=True)
    block = expect(client.post("/venue-blocks", headers=ADMIN, json={
        "venue_ids": originals, "starts_at": SCHEDULE["starts_at"], "ends_at": SCHEDULE["ends_at"],
        "reason": "学校临时考试",
    }), 201)
    path = f"/venue-blocks/{block['id']}"
    preview = expect(client.get(f"{path}/coordination", headers=ADMIN))
    assert preview["suggested_assignments"] == [
        {"reservation_id": first["id"], "venue_id": flexible_only},
        {"reservation_id": second["id"], "venue_id": shared},
    ]
    assert [row["status"] for row in expect(client.get("/reservations", headers=ADMIN))] == [
        "affected", "affected",
    ]
    confirmed = expect(client.post(f"{path}/coordinate", headers=ADMIN, json={
        "assignments": preview["suggested_assignments"],
    }))
    assert confirmed["unassigned_reservation_ids"] == []
    assert [(row["replaces_id"], row["venue_id"]) for row in confirmed["confirmed"]] == [
        (first["id"], flexible_only), (second["id"], shared),
    ]
