from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
PositiveId = Annotated[int, Field(strict=True, gt=0)]


class ClubInput(BaseModel):
    name: ShortText


class Decision(BaseModel):
    status: Literal["approved", "rejected"]


class AnnualReviewInput(BaseModel):
    year: int = Field(ge=2000, le=9999)
    materials: LongText


class Proposal(BaseModel):
    description: LongText


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: ShortText
    summary: LongText
    goals: list[ShortText] = Field(min_length=1, max_length=12)
    agenda: list[ShortText] = Field(min_length=1, max_length=20)
    participants: int = Field(gt=0)
    duration_minutes: int = Field(gt=0)
    venue_capacity: int = Field(gt=0)
    equipment: list[ShortText] = Field(max_length=20)
    notes: list[ShortText] = Field(max_length=20)


class DraftChange(BaseModel):
    confirmed: Annotated[Literal[True], Field(description="负责人确认活动草稿")]
    plan: Plan

    @model_validator(mode="before")
    @classmethod
    def require_confirmation(cls, data):
        if isinstance(data, dict) and data.get("confirmed") is not True:
            raise ValueError("请确认草稿后保存")
        return data


class DraftInput(DraftChange):
    club_id: PositiveId


class TimeRange(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def check_order(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class ScheduleInput(TimeRange):
    semester: ShortText
    category: ShortText


class ActivityDecision(Decision):
    priority: int = Field(default=0, ge=0, le=5)


class AttendanceInput(BaseModel):
    student_id: ShortText


class VenueInput(BaseModel):
    name: ShortText
    capacity: int = Field(gt=0)
    equipment: list[ShortText] = Field(default_factory=list, max_length=30)


class ReservationInput(BaseModel):
    activity_id: PositiveId
    venue_id: PositiveId


class VenueBlockInput(TimeRange):
    venue_ids: list[PositiveId] = Field(min_length=1, max_length=30)
    reason: LongText


class AssignmentInput(BaseModel):
    reservation_id: PositiveId
    venue_id: PositiveId


class CoordinationInput(BaseModel):
    assignments: list[AssignmentInput] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_reservations(self):
        if len({item.reservation_id for item in self.assignments}) != len(self.assignments):
            raise ValueError("每条预约只能指定一个替代场地")
        return self


class CreditRuleInput(BaseModel):
    credits: Decimal = Field(gt=0, max_digits=5, decimal_places=2)


class EvaluationInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)
