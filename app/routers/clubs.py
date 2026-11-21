from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from .. import ai
from ..access import Admin, SignedIn, Student, get_or_404, owned_club
from ..database import Db, write_transaction
from ..models import AnnualReview, Club
from ..schemas import AnnualReviewInput, ClubInput, Decision, Plan, Proposal

router = APIRouter(tags=["社团管理"])


def club_data(club: Club):
    return {"id": club.id, "name": club.name, "status": club.status}


def annual_review_data(review: AnnualReview):
    return {
        "id": review.id, "club_id": review.club_id, "year": review.year,
        "materials": review.materials, "status": review.status,
    }


@router.post("/clubs", status_code=201)
def apply(body: ClubInput, actor: Student, db: Db):
    with write_transaction(db):
        club = Club(name=body.name, owner=actor.id)
        db.add(club)
        db.flush()
        return club_data(club)


@router.get("/clubs")
def clubs(db: Db):
    query = select(Club).where(Club.status == "approved").order_by(Club.id)
    return [club_data(club) for club in db.scalars(query)]


@router.get("/managed/clubs")
def managed_clubs(actor: SignedIn, db: Db):
    query = select(Club).order_by(Club.id)
    if actor.role == "student":
        query = query.where(Club.owner == actor.id)
    return [club_data(club) for club in db.scalars(query)]


@router.post("/clubs/{club_id}/review")
def review(club_id: int, body: Decision, _actor: Admin, db: Db):
    with write_transaction(db):
        club = get_or_404(db, Club, club_id, "社团不存在")
        if club.status != "pending":
            raise HTTPException(409, "申请已处理")
        club.status = body.status
        return club_data(club)


@router.post("/clubs/{club_id}/annual-reviews", status_code=201)
def submit_annual_review(club_id: int, body: AnnualReviewInput, actor: Student, db: Db):
    with write_transaction(db):
        owned_club(db, club_id, actor)
        existing = db.scalar(select(AnnualReview).where(
            AnnualReview.club_id == club_id, AnnualReview.year == body.year,
        ))
        if existing:
            raise HTTPException(409, "该年度已提交年审")
        review = AnnualReview(club_id=club_id, year=body.year, materials=body.materials)
        db.add(review)
        db.flush()
        return annual_review_data(review)


@router.get("/clubs/{club_id}/annual-reviews")
def annual_reviews(club_id: int, actor: SignedIn, db: Db):
    if actor.role == "admin":
        get_or_404(db, Club, club_id, "社团不存在")
    else:
        owned_club(db, club_id, actor)
    query = select(AnnualReview).where(AnnualReview.club_id == club_id).order_by(AnnualReview.year.desc())
    return [annual_review_data(review) for review in db.scalars(query)]


@router.post("/annual-reviews/{review_id}/decision")
def decide_annual_review(review_id: int, body: Decision, _actor: Admin, db: Db):
    with write_transaction(db):
        review = get_or_404(db, AnnualReview, review_id, "年审申请不存在")
        if review.status != "pending":
            raise HTTPException(409, "年审申请已处理")
        review.status = body.status
        return annual_review_data(review)


@router.post("/clubs/{club_id}/ai-plan", tags=["AI 策划"])
def ai_plan(club_id: int, body: Proposal, actor: Student, db: Db) -> Plan:
    owned_club(db, club_id, actor)
    db.rollback()
    try:
        return ai.generate_plan(body.description)
    except ai.PlanningError as exc:
        raise HTTPException(*exc.args) from exc
