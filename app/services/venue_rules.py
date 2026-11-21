import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Reservation, Venue, VenueBlock, VenueClosure
from ..schemas import Plan

LOCKING_STATUSES = ("pending", "approved")


def room_fits(capacity: int, equipment: list[str], plan: Plan) -> bool:
    return capacity >= max(plan.venue_capacity, plan.participants) and set(plan.equipment).issubset(equipment)


def occupied_venues(db: Session, starts_at: datetime, ends_at: datetime, exclude_reservation_id: int | None = None):
    bookings = select(Reservation.venue_id).where(
        Reservation.status.in_(LOCKING_STATUSES),
        Reservation.starts_at < ends_at, starts_at < Reservation.ends_at,
    )
    if exclude_reservation_id is not None:
        bookings = bookings.where(Reservation.id != exclude_reservation_id)
    closures = select(VenueClosure.venue_id).join(VenueBlock).where(
        VenueBlock.starts_at < ends_at, starts_at < VenueBlock.ends_at,
    )
    return set(db.scalars(bookings.union(closures)))


def candidate_venues(db: Session, plan: Plan, starts_at: datetime, ends_at: datetime,
                     excluded_id: int | None = None) -> list[Venue]:
    unavailable = occupied_venues(db, starts_at, ends_at)
    query = select(Venue).order_by(Venue.id)
    return [
        venue for venue in db.scalars(query)
        if venue.id != excluded_id and venue.id not in unavailable
        and room_fits(venue.capacity, json.loads(venue.equipment_json), plan)
    ]
