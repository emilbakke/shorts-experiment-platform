from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_utc(value: Any) -> str | None:
    if value is None:
        return None
    if not hasattr(value, "isoformat"):
        return str(value)
    if isinstance(value, datetime):
        value = ensure_utc_datetime(value)
    return value.isoformat()
