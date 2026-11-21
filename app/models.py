from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    owner: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")


class AnnualReview(Base):
    __tablename__ = "annual_reviews"
    __table_args__ = (UniqueConstraint("club_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    year: Mapped[int]
    materials: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    plan_json: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft")


class ActivitySchedule(Base):
    __tablename__ = "activity_schedules"
    __table_args__ = (CheckConstraint("ends_at > starts_at"),)

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    semester: Mapped[str] = mapped_column(index=True)
    category: Mapped[str]
    priority: Mapped[int] = mapped_column(default=0)


class Registration(Base):
    __tablename__ = "registrations"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    student_id: Mapped[str] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(default="active")
    signed_at: Mapped[datetime | None]


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    capacity: Mapped[int]
    equipment_json: Mapped[str]


class VenueBlock(Base):
    __tablename__ = "venue_blocks"
    __table_args__ = (CheckConstraint("ends_at > starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    reason: Mapped[str]


class VenueClosure(Base):
    __tablename__ = "venue_closures"

    block_id: Mapped[int] = mapped_column(ForeignKey("venue_blocks.id"), primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), primary_key=True, index=True)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at"),
        Index("ix_reservation_venue_time", "venue_id", "starts_at", "ends_at"),
        Index("uq_current_activity_reservation", "activity_id", unique=True,
              sqlite_where=text("status IN ('pending', 'approved', 'affected')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(default="pending")
    block_id: Mapped[int | None] = mapped_column(ForeignKey("venue_blocks.id"), index=True)
    replaces_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"), unique=True)


class CreditRule(Base):
    __tablename__ = "credit_rules"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    hundredths: Mapped[int]


class CreditRecord(Base):
    __tablename__ = "credit_records"
    __table_args__ = (
        ForeignKeyConstraint(["activity_id", "student_id"], ["registrations.activity_id", "registrations.student_id"]),
    )

    activity_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    hundredths: Mapped[int]
    awarded_at: Mapped[datetime]


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5"),
        ForeignKeyConstraint(["activity_id", "student_id"], ["registrations.activity_id", "registrations.student_id"]),
    )

    activity_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(primary_key=True)
    rating: Mapped[int]
    comment: Mapped[str]
    submitted_at: Mapped[datetime]
