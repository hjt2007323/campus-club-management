from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..access import Admin, SignedIn, Student, get_activity, get_schedule, owned_club
from ..database import Db, write_transaction
from ..models import Activity, ActivitySchedule, Club, Evaluation, Registration, Reservation, Venue
from ..schemas import ActivityDecision, AttendanceInput, DraftChange, DraftInput, Plan, ScheduleInput
from ..times import Now, timestamp, utc_value
from .outcomes import award_credits, credit_recipient_count

router = APIRouter(tags=["活动管理"])


def activity_data(activity: Activity, schedule: ActivitySchedule | None):
    dates = None
    if schedule:
        dates = {
            "starts_at": timestamp(schedule.starts_at), "ends_at": timestamp(schedule.ends_at),
            "semester": schedule.semester, "category": schedule.category, "priority": schedule.priority,
        }
    return {
        "id": activity.id, "club_id": activity.club_id, "status": activity.status,
        "plan": Plan.model_validate_json(activity.plan_json), "schedule": dates,
    }


def registration_data(registration: Registration):
    return {
        "activity_id": registration.activity_id, "student_id": registration.student_id,
        "status": registration.status, "signed_at": timestamp(registration.signed_at),
    }


@router.post("/activities", status_code=201)
def save_draft(body: DraftInput, actor: Student, db: Db):
    with write_transaction(db):
        owned_club(db, body.club_id, actor)
        activity = Activity(club_id=body.club_id, plan_json=body.plan.model_dump_json())
        db.add(activity)
        db.flush()
        return activity_data(activity, None)


@router.patch("/activities/{activity_id}")
def edit_draft(activity_id: int, body: DraftChange, actor: Student, db: Db):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        owned_club(db, activity.club_id, actor)
        if activity.status not in {"draft", "rejected"}:
            raise HTTPException(409, "只能编辑草稿或被退回的活动")
        activity.plan_json = body.plan.model_dump_json()
        return activity_data(activity, db.get(ActivitySchedule, activity_id))


@router.post("/activities/{activity_id}/submit")
def submit(activity_id: int, body: ScheduleInput, actor: Student, db: Db, now: Now):
    starts_at, ends_at = utc_value(body.starts_at), utc_value(body.ends_at)
    if starts_at <= now:
        raise HTTPException(422, "提交的活动必须在未来开始")
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        owned_club(db, activity.club_id, actor)
        if activity.status not in {"draft", "rejected"}:
            raise HTTPException(409, "活动已提交或已结束")
        schedule = db.get(ActivitySchedule, activity_id)
        if schedule is None:
            schedule = ActivitySchedule(activity_id=activity_id)
            db.add(schedule)
        schedule.starts_at = starts_at
        schedule.ends_at = ends_at
        schedule.semester = body.semester
        schedule.category = body.category
        schedule.priority = 0
        activity.status = "submitted"
        return activity_data(activity, schedule)


@router.post("/activities/{activity_id}/review")
def review(activity_id: int, body: ActivityDecision, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        if activity.status != "submitted":
            raise HTTPException(409, "活动当前不在待审批状态")
        schedule = get_schedule(db, activity_id)
        if body.status == "approved" and schedule.starts_at <= now:
            raise HTTPException(409, "活动开始时间已过，请退回并重新排期")
        schedule.priority = body.priority if body.status == "approved" else 0
        activity.status = body.status
        return activity_data(activity, schedule)


@router.get("/activities")
def list_public_activities(db: Db, now: Now):
    current_reservation = Reservation.status.in_(("approved", "affected"))
    query = (
        select(Activity, ActivitySchedule, Reservation.status, Venue.name)
        .join(ActivitySchedule)
        .outerjoin(Reservation, (Reservation.activity_id == Activity.id) & current_reservation)
        .outerjoin(Venue, (Venue.id == Reservation.venue_id) & (Reservation.status == "approved"))
        .where(Activity.status.in_(("approved", "completed")))
        .order_by(ActivitySchedule.starts_at, Activity.id)
    )
    return [
        {
            **activity_data(activity, schedule), "venue_name": venue_name,
            "reservation_status": reservation_status,
            "registration_open": activity.status == "approved" and schedule.starts_at > now,
        }
        for activity, schedule, reservation_status, venue_name in db.execute(query)
    ]


@router.get("/managed/activities")
def list_managed_activities(actor: SignedIn, db: Db, now: Now):
    query = select(Activity, ActivitySchedule).outerjoin(ActivitySchedule).order_by(Activity.id)
    if actor.role == "student":
        query = query.join(Club, Activity.club_id == Club.id).where(Club.owner == actor.id)
    return [
        {
            **activity_data(activity, schedule),
            "can_check_in": bool(schedule and activity.status == "approved" and schedule.starts_at <= now < schedule.ends_at),
            "can_complete": bool(schedule and activity.status == "approved" and schedule.ends_at <= now),
        }
        for activity, schedule in db.execute(query)
    ]


def ensure_registration_open(db: Session, activity: Activity, now: datetime):
    if activity.status != "approved":
        raise HTTPException(409, "仅审批通过且未开始的活动开放报名")
    if get_schedule(db, activity.id).starts_at <= now:
        raise HTTPException(409, "活动报名时间已结束")


@router.put("/activities/{activity_id}/registration")
def register(activity_id: int, actor: Student, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        ensure_registration_open(db, activity, now)
        registration = db.get(Registration, (activity_id, actor.id))
        if registration is not None and registration.status == "active":
            return registration_data(registration)
        participants = Plan.model_validate_json(activity.plan_json).participants
        active_count = db.scalar(select(func.count()).select_from(Registration).where(
            Registration.activity_id == activity_id, Registration.status == "active",
        ))
        if active_count >= participants:
            raise HTTPException(409, "活动名额已满")
        if registration is None:
            registration = Registration(activity_id=activity_id, student_id=actor.id)
            db.add(registration)
        registration.status = "active"
        return registration_data(registration)


@router.delete("/activities/{activity_id}/registration")
def cancel_registration(activity_id: int, actor: Student, db: Db, now: Now):
    with write_transaction(db):
        ensure_registration_open(db, get_activity(db, activity_id), now)
        registration = db.get(Registration, (activity_id, actor.id))
        if registration is None:
            raise HTTPException(404, "未找到报名记录")
        registration.status = "cancelled"
        return registration_data(registration)


@router.get("/me/registrations")
def my_registrations(actor: Student, db: Db):
    query = (
        select(Registration, Evaluation.activity_id)
        .outerjoin(Evaluation, (Evaluation.activity_id == Registration.activity_id)
                   & (Evaluation.student_id == Registration.student_id))
        .where(Registration.student_id == actor.id)
        .order_by(Registration.activity_id)
    )
    return [
        {**registration_data(registration), "evaluated": evaluation_id is not None}
        for registration, evaluation_id in db.execute(query)
    ]


@router.get("/activities/{activity_id}/registrations")
def roster(activity_id: int, _actor: Admin, db: Db):
    get_activity(db, activity_id)
    query = select(Registration).where(
        Registration.activity_id == activity_id, Registration.status == "active",
    ).order_by(Registration.student_id)
    return [registration_data(registration) for registration in db.scalars(query)]


@router.post("/activities/{activity_id}/attendance")
def check_in(activity_id: int, body: AttendanceInput, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        if activity.status != "approved":
            raise HTTPException(409, "只有审批通过的进行中活动可以签到")
        schedule = get_schedule(db, activity_id)
        if not schedule.starts_at <= now < schedule.ends_at:
            raise HTTPException(409, "当前不在活动签到时间内")
        registration = db.get(Registration, (activity_id, body.student_id))
        if registration is None or registration.status != "active":
            raise HTTPException(409, "没有有效报名，无法签到")
        if registration.signed_at is None:
            registration.signed_at = now
        return registration_data(registration)


@router.post("/activities/{activity_id}/complete")
def complete(activity_id: int, _actor: Admin, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        if activity.status == "completed":
            return {"id": activity_id, "status": activity.status, "credits_awarded": credit_recipient_count(db, activity_id)}
        if activity.status != "approved":
            raise HTTPException(409, "仅审批通过的活动可以完成")
        schedule = get_schedule(db, activity_id)
        if now < schedule.ends_at:
            raise HTTPException(409, "活动尚未结束")
        activity.status = "completed"
        count = award_credits(db, activity_id, now)
        return {"id": activity_id, "status": activity.status, "credits_awarded": count}
