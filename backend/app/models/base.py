"""Shared helpers and column types for ORM models."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator


def utcnow() -> datetime:
    """Timezone-aware current UTC time. All timestamps are stored in UTC."""
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """Stores naive-UTC and always returns timezone-aware UTC datetimes.

    SQLite has no native timezone support and SQLAlchemy hands back naive
    datetimes, which would break aware/naive comparisons (e.g. expiry checks).
    This decorator normalises on the way in and out so the application layer
    only ever sees aware UTC, on both SQLite and PostgreSQL.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
