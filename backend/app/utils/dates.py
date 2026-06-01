from datetime import date, datetime, time, timedelta, timezone


def to_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
    return start, end


def previous_day_bounds() -> tuple[datetime, datetime]:
    yesterday = datetime.now(tz=timezone.utc).date() - timedelta(days=1)
    return to_day_bounds(yesterday)
