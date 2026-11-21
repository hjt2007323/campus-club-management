from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends


def utc_value(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def current_time() -> datetime:
    return utc_value(datetime.now(UTC))


def timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat()


Now = Annotated[datetime, Depends(current_time)]
