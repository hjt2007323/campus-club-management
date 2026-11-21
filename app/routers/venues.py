import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import Admin, SignedIn, Student, get_activity, get_or_404, get_schedule, owned_club
from ..database import Db, write_transaction
from ..models import Activity, Club, Reservation, Venue, VenueBlock, VenueClosure
from ..schemas import CoordinationInput, Decision, Plan, ReservationInput, VenueBlockInput, VenueInput
from ..services import venue_matching
from ..services.venue_rules import LOCKING_STATUSES, candidate_venues, occupied_venues, room_fits
from ..times import Now, timestamp, utc_value

router = APIRouter(tags=["场地管理"])


def venue_data(venue: Venue):
    return {
        "id": venue.id, "name": venue.name, "capacity": venue.capacity,
        "equipment": json.loads(venue.equipment_json),
    }


def reservation_data(reservation: Reservation):
    return {
        "id": reservation.id, "activity_id": reservation.activity_id, "venue_id": reservation.venue_id,
        "starts_at": timestamp(reservation.starts_at), "ends_at": timestamp(reservation.ends_at),
        "status": reservation.status, "block_id": reservation.block_id,
        "replaces_id": reservation.replaces_id,
    }


def check_venue(db: Session, venue: Venue, plan: Plan, starts_at: datetime, ends_at: datetime,
                exclude_id: int | None = None):
    if not room_fits(venue.capacity, json.loads(venue.equipment_json), plan):
        raise HTTPException(409, "场地容量或设备不满足活动需求")
    if venue.id in occupied_venues(db, starts_at, ends_at, exclude_id):
        raise HTTPException(409, "该场地在原定时间已有预约或被征用")


@router.get("/venues")
def venues(db: Db):
    return [venue_data(venue) for venue in db.scalars(select(Venue).order_by(Venue.id))]


@router.post("/venues", status_code=201)
def create_venue(body: VenueInput, _actor: Admin, db: Db):
    with write_transaction(db):
        venue = Venue(name=body.name, capacity=body.capacity,
                      equipment_json=json.dumps(body.equipment, ensure_ascii=False))
        db.add(venue)
        db.flush()
        return venue_data(venue)


@router.patch("/venues/{venue_id}")
def edit_venue(venue_id: int, body: VenueInput, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        venue = get_or_404(db, Venue, venue_id, "场地不存在")
        reservations = select(Reservation).where(
            Reservation.venue_id == venue_id, Reservation.status.in_(LOCKING_STATUSES),
            Reservation.ends_at > now,
        )
        for reservation in db.scalars(reservations):
            plan = Plan.model_validate_json(get_activity(db, reservation.activity_id).plan_json)
            if not room_fits(body.capacity, body.equipment, plan):
                raise HTTPException(409, "修改后的场地条件与现有预约不符")
        venue.name = body.name
        venue.capacity = body.capacity
        venue.equipment_json = json.dumps(body.equipment, ensure_ascii=False)
        return venue_data(venue)


@router.get("/activities/{activity_id}/venue-options")
def available_venues(activity_id: int, actor: SignedIn, db: Db, now: Now, exclude_venue_id: int | None = None):
    activity = get_activity(db, activity_id)
    if actor.role == "student":
        owned_club(db, activity.club_id, actor)
    if activity.status != "approved":
        raise HTTPException(409, "仅审批通过的活动可以预约")
    schedule = get_schedule(db, activity_id)
    if schedule.starts_at <= now:
        raise HTTPException(409, "活动已经开始，请联系管理员")
    plan = Plan.model_validate_json(activity.plan_json)
    return [venue_data(venue) for venue in candidate_venues(
        db, plan, schedule.starts_at, schedule.ends_at, exclude_venue_id,
    )]


@router.get("/reservations")
def reservations(actor: SignedIn, db: Db):
    query = select(Reservation).order_by(Reservation.id)
    if actor.role == "student":
        query = query.join(Activity).join(Club).where(Club.owner == actor.id)
    return [reservation_data(reservation) for reservation in db.scalars(query)]


@router.post("/reservations", status_code=201)
def reserve(body: ReservationInput, actor: Student, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, body.activity_id)
        owned_club(db, activity.club_id, actor)
        if activity.status != "approved":
            raise HTTPException(409, "仅审批通过的活动可以预约")
        schedule = get_schedule(db, activity.id)
        if schedule.starts_at <= now:
            raise HTTPException(409, "活动已经开始，请联系管理员")
        existing = db.scalar(select(Reservation.id).where(
            Reservation.activity_id == activity.id, Reservation.status.in_((*LOCKING_STATUSES, "affected")),
        ))
        if existing is not None:
            raise HTTPException(409, "该活动已有预约待处理")
        venue = get_or_404(db, Venue, body.venue_id, "场地不存在")
        plan = Plan.model_validate_json(activity.plan_json)
        check_venue(db, venue, plan, schedule.starts_at, schedule.ends_at)
        reservation = Reservation(activity_id=activity.id, venue_id=venue.id,
                                  starts_at=schedule.starts_at, ends_at=schedule.ends_at)
        db.add(reservation)
        db.flush()
        return reservation_data(reservation)


@router.post("/reservations/{reservation_id}/review")
def review_reservation(reservation_id: int, body: Decision, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        reservation = get_or_404(db, Reservation, reservation_id, "预约不存在")
        if reservation.status == "affected" and body.status == "rejected":
            reservation.status = "rejected"
            return reservation_data(reservation)
        if reservation.status != "pending":
            raise HTTPException(409, "预约当前不在待审批状态")
        if body.status == "approved":
            if reservation.starts_at <= now:
                raise HTTPException(409, "活动已经开始，无法确认该预约")
            venue = get_or_404(db, Venue, reservation.venue_id, "场地不存在")
            plan = Plan.model_validate_json(get_activity(db, reservation.activity_id).plan_json)
            check_venue(db, venue, plan, reservation.starts_at, reservation.ends_at, reservation.id)
        reservation.status = body.status
        return reservation_data(reservation)


@router.get("/reservations/{reservation_id}/alternatives")
def alternatives(reservation_id: int, actor: SignedIn, db: Db, now: Now):
    reservation = get_or_404(db, Reservation, reservation_id, "预约不存在")
    activity = get_activity(db, reservation.activity_id)
    if actor.role == "student":
        owned_club(db, activity.club_id, actor)
    if reservation.ends_at <= now:
        return []
    plan = Plan.model_validate_json(activity.plan_json)
    return [venue_data(venue) for venue in candidate_venues(
        db, plan, reservation.starts_at, reservation.ends_at, reservation.venue_id,
    )]


@router.get("/venue-blocks")
def venue_blocks(_actor: Admin, db: Db):
    rows = db.execute(select(VenueBlock, VenueClosure.venue_id)
                      .join(VenueClosure).order_by(VenueBlock.id, VenueClosure.venue_id))
    blocks = {}
    for block, venue_id in rows:
        if block.id not in blocks:
            blocks[block.id] = {
                "id": block.id, "venue_ids": [], "starts_at": timestamp(block.starts_at),
                "ends_at": timestamp(block.ends_at), "reason": block.reason,
            }
        blocks[block.id]["venue_ids"].append(venue_id)
    return list(blocks.values())


@router.post("/venue-blocks", status_code=201)
def requisition(body: VenueBlockInput, _actor: Admin, db: Db, now: Now):
    starts_at, ends_at = utc_value(body.starts_at), utc_value(body.ends_at)
    if ends_at <= now:
        raise HTTPException(422, "征用时段已经结束")
    venue_ids = sorted(set(body.venue_ids))
    with write_transaction(db):
        existing = set(db.scalars(select(Venue.id).where(Venue.id.in_(venue_ids))))
        if existing != set(venue_ids):
            raise HTTPException(404, "征用清单包含不存在的场地")
        block = VenueBlock(starts_at=starts_at, ends_at=ends_at, reason=body.reason)
        db.add(block)
        db.flush()
        db.add_all([VenueClosure(block_id=block.id, venue_id=venue_id) for venue_id in venue_ids])
        affected = db.scalars(select(Reservation).where(
            Reservation.venue_id.in_(venue_ids),
            Reservation.status.in_(LOCKING_STATUSES),
            Reservation.starts_at < ends_at, starts_at < Reservation.ends_at,
            Reservation.ends_at > now,
        ).order_by(Reservation.id)).all()
        for reservation in affected:
            reservation.status = "affected"
            reservation.block_id = block.id
        return {"id": block.id, "venue_ids": venue_ids,
                "affected_reservation_ids": [reservation.id for reservation in affected]}


def affected_reservations(db: Session, block_id: int):
    get_or_404(db, VenueBlock, block_id, "征用记录不存在")
    query = select(Reservation).where(
        Reservation.block_id == block_id, Reservation.status == "affected",
    ).order_by(Reservation.id)
    return list(db.scalars(query))


@router.get("/venue-blocks/{block_id}/coordination")
def preview_coordination(block_id: int, _actor: Admin, db: Db, now: Now):
    rooms_by_reservation = []
    matching_requests = []
    for reservation in affected_reservations(db, block_id):
        activity = get_activity(db, reservation.activity_id)
        schedule = get_schedule(db, activity.id)
        plan = Plan.model_validate_json(activity.plan_json)
        rooms = []
        if activity.status == "approved" and reservation.ends_at > now:
            rooms = candidate_venues(db, plan, reservation.starts_at, reservation.ends_at, reservation.venue_id)
        rooms_by_reservation.append({
            **reservation_data(reservation), "title": plan.title, "priority": schedule.priority,
            "candidates": [venue_data(room) for room in rooms],
        })
        matching_requests.append(venue_matching.VenueMatchRequest(
            reservation.id, reservation.starts_at, reservation.ends_at,
            schedule.priority, tuple(room.id for room in rooms),
        ))
    proposal = venue_matching.recommend_venues(matching_requests)
    suggested_assignments = None if proposal is None else [
        {"reservation_id": reservation_id, "venue_id": venue_id}
        for reservation_id, venue_id in sorted(proposal.items())
    ]
    return {"block_id": block_id, "affected": rooms_by_reservation, "suggested_assignments": suggested_assignments}


@router.post("/venue-blocks/{block_id}/coordinate")
def confirm_coordination(block_id: int, body: CoordinationInput, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        pending = {reservation.id: reservation for reservation in affected_reservations(db, block_id)}
        confirmed = []
        for assignment in body.assignments:
            old = pending.pop(assignment.reservation_id, None)
            if old is None:
                raise HTTPException(409, "预约已处理或不属于本次征用，请刷新")
            activity = get_activity(db, old.activity_id)
            if old.ends_at <= now or activity.status != "approved":
                raise HTTPException(409, "预约时段已结束或活动已完成")
            if assignment.venue_id == old.venue_id:
                raise HTTPException(409, "请选择不同的替代场地")
            venue = get_or_404(db, Venue, assignment.venue_id, "场地不存在")
            plan = Plan.model_validate_json(activity.plan_json)
            check_venue(db, venue, plan, old.starts_at, old.ends_at)
            old.status = "superseded"
            db.flush()
            replacement = Reservation(
                venue_id=venue.id, activity_id=old.activity_id,
                starts_at=old.starts_at, ends_at=old.ends_at, status="approved", replaces_id=old.id,
            )
            db.add(replacement)
            db.flush()
            confirmed.append(reservation_data(replacement))
        return {"confirmed": confirmed, "unassigned_reservation_ids": sorted(pending)}
