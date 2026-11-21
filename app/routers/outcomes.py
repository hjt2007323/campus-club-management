from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..access import Admin, Student, get_activity
from ..database import Db, write_transaction
from ..models import Activity, ActivitySchedule, Club, CreditRecord, CreditRule, Evaluation, Registration
from ..schemas import CreditRuleInput, EvaluationInput, Plan, ShortText
from ..times import Now, timestamp

router = APIRouter()
DEFAULT_CREDIT_HUNDREDTHS = 100


def credit_recipient_count(db: Session, activity_id: int) -> int:
    return db.scalar(select(func.count()).select_from(CreditRecord).where(
        CreditRecord.activity_id == activity_id,
    ))


def award_credits(db: Session, activity_id: int, now: datetime) -> int:
    rule = db.get(CreditRule, activity_id)
    amount = rule.hundredths if rule else DEFAULT_CREDIT_HUNDREDTHS
    students = db.scalars(select(Registration.student_id).where(
        Registration.activity_id == activity_id,
        Registration.status == "active",
        Registration.signed_at.is_not(None),
    )).all()
    db.add_all([
        CreditRecord(activity_id=activity_id, student_id=student_id, hundredths=amount, awarded_at=now)
        for student_id in students
    ])
    return len(students)


@router.put("/activities/{activity_id}/credit-rule", tags=["学分管理"])
def set_credit_rule(activity_id: int, body: CreditRuleInput, _actor: Admin, db: Db):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        if activity.status == "completed":
            raise HTTPException(409, "已完成活动的学分记录已确定")
        rule = db.get(CreditRule, activity_id)
        if rule is None:
            rule = CreditRule(activity_id=activity_id)
            db.add(rule)
        rule.hundredths = int(body.credits * 100)
        return {"activity_id": activity_id, "credits": rule.hundredths / 100}


@router.get("/me/credits", tags=["学分管理"])
def my_credits(actor: Student, db: Db, semester: ShortText | None = None):
    query = (
        select(CreditRecord, ActivitySchedule.semester, Activity.plan_json)
        .join(ActivitySchedule, CreditRecord.activity_id == ActivitySchedule.activity_id)
        .join(Activity, CreditRecord.activity_id == Activity.id)
        .where(CreditRecord.student_id == actor.id)
        .order_by(CreditRecord.awarded_at.desc(), CreditRecord.activity_id)
    )
    if semester:
        query = query.where(ActivitySchedule.semester == semester)
    rows = db.execute(query).all()
    totals = {}
    records = []
    for credit, term, plan_json in rows:
        totals[term] = totals.get(term, 0) + credit.hundredths
        records.append({
            "activity_id": credit.activity_id, "activity_title": Plan.model_validate_json(plan_json).title,
            "semester": term, "credits": credit.hundredths / 100, "awarded_at": timestamp(credit.awarded_at),
        })
    return {
        "records": records, "total": sum(totals.values()) / 100,
        "by_semester": {term: amount / 100 for term, amount in sorted(totals.items())},
    }


def evaluation_data(record: Evaluation):
    return {
        "student_id": record.student_id, "rating": record.rating,
        "comment": record.comment, "submitted_at": timestamp(record.submitted_at),
    }


@router.post("/activities/{activity_id}/evaluations", status_code=201, tags=["评价管理"])
def add_evaluation(activity_id: int, body: EvaluationInput, actor: Student, db: Db, now: Now):
    with write_transaction(db):
        activity = get_activity(db, activity_id)
        registration = db.get(Registration, (activity_id, actor.id))
        if activity.status != "completed":
            raise HTTPException(409, "活动完成后开放评价")
        if registration is None or registration.status != "active" or registration.signed_at is None:
            raise HTTPException(403, "只有已签到的参与者可评价")
        if db.get(Evaluation, (activity_id, actor.id)) is not None:
            raise HTTPException(409, "你已评价过本活动")
        record = Evaluation(
            activity_id=activity_id, student_id=actor.id, rating=body.rating,
            comment=body.comment.strip(), submitted_at=now,
        )
        db.add(record)
        return evaluation_data(record)


@router.get("/activities/{activity_id}/evaluations", tags=["评价管理"])
def activity_evaluations(activity_id: int, _actor: Admin, db: Db):
    get_activity(db, activity_id)
    query = select(Evaluation).where(Evaluation.activity_id == activity_id).order_by(Evaluation.student_id)
    records = list(db.scalars(query))
    average = sum(record.rating for record in records) / len(records) if records else None
    return {"records": [evaluation_data(record) for record in records], "average": average}


@router.get("/statistics", tags=["统计管理"])
def statistics(_actor: Admin, db: Db, semester: ShortText | None = None):
    published = (
        select(Activity.id, Activity.club_id, ActivitySchedule.semester, ActivitySchedule.category)
        .join(ActivitySchedule)
        .where(Activity.status.in_(("approved", "completed")))
    )
    if semester:
        published = published.where(ActivitySchedule.semester == semester)
    events = published.cte("published_activities")
    activity_totals = db.execute(select(
        events.c.semester, func.count(),
    ).group_by(events.c.semester).order_by(events.c.semester)).all()
    club_totals = db.execute(select(
        Club.id, Club.name, func.count(),
    ).join(events, events.c.club_id == Club.id).group_by(Club.id, Club.name).order_by(Club.id)).all()
    category_totals = db.execute(select(
        events.c.category, func.count(),
    ).group_by(events.c.category).order_by(events.c.category)).all()
    participation = db.execute(select(
        func.count(), func.count(Registration.signed_at), func.count(func.distinct(Registration.student_id)),
    ).select_from(Registration).join(events, events.c.id == Registration.activity_id)
        .where(Registration.status == "active")).one()
    credits = db.execute(select(
        events.c.semester, func.sum(CreditRecord.hundredths), func.count(),
    ).join(CreditRecord, CreditRecord.activity_id == events.c.id)
        .group_by(events.c.semester).order_by(events.c.semester)).all()
    return {
        "activity_count": sum(count for _, count in activity_totals),
        "activities_by_semester": dict(activity_totals),
        "activities_by_club": [{"id": club_id, "name": name, "count": count} for club_id, name, count in club_totals],
        "activities_by_category": dict(category_totals),
        "registrations": participation[0],
        "attendances": participation[1],
        "unique_students": participation[2],
        "credit_total": sum(amount for _, amount, _ in credits) / 100,
        "credits_by_semester": {term: {"credits": amount / 100, "records": count} for term, amount, count in credits},
    }
