"""Read-only availability against the complete stored account calendar snapshot."""

from datetime import datetime, time, timedelta, timezone

from .recurrence import format_instant, parse_date, parse_instant, zone


def availability(store, day, tzid, start_minute, end_minute, duration):
    date, tz = parse_date(day), zone(tzid)
    if not 0 <= start_minute < end_minute <= 1440 or not 1 <= duration <= 1440:
        raise ValueError("Invalid day window or duration.")

    def local_instant(minute):
        naive = datetime.combine(date, time()) + timedelta(minutes=minute)
        aware = naive.replace(tzinfo=tz)
        # Do not silently choose an ambiguous or nonexistent local boundary.
        if (
            aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive
            or aware.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset()
        ):
            raise ValueError("Choose an unambiguous local time outside the clock change.")
        return aware.astimezone(timezone.utc)

    start, end = local_instant(start_minute), local_instant(end_minute)
    snapshot = store.occurrences(start, end, tzid)
    rows = snapshot["occurrences"]
    if len(rows) > 1000:
        raise ValueError("Too many occurrences to calculate safely.")
    busy = []
    for row in rows:
        if row.all_day:
            # Existing calendar convention: all-day dates occupy the viewed day.
            a = datetime.combine(parse_date(row.start), time(), tz).astimezone(timezone.utc)
            b = datetime.combine(parse_date(row.end), time(), tz).astimezone(timezone.utc)
        else:
            a, b = parse_instant(row.start), parse_instant(row.end)
        a, b = max(start, a), min(end, b)
        if a < b:
            busy.append((a, b, row.id))
    busy.sort()
    titles = {row.id: row.title for row in rows}
    conflicts = []
    for i, (a, b, identity) in enumerate(busy):
        for c, d, other in busy[i + 1 :]:
            if c >= b:
                break
            conflicts.append(
                {
                    "start": format_instant(c),
                    "end": format_instant(min(b, d)),
                    "occurrence_ids": [identity, other],
                    "titles": [titles[identity], titles[other]],
                }
            )
            if len(conflicts) > 1000:
                raise ValueError("Too many conflicts; narrow the time window.")
    cursor, free = start, []
    for a, b, _ in busy:
        if a > cursor and (a - cursor).total_seconds() >= duration * 60:
            free.append({"start": format_instant(cursor), "end": format_instant(a)})
        cursor = max(cursor, b)
    if end > cursor and (end - cursor).total_seconds() >= duration * 60:
        free.append({"start": format_instant(cursor), "end": format_instant(end)})
    return {
        "date": day,
        "tz": tzid,
        "revision": snapshot["revision"],
        "free": free,
        "conflicts": conflicts,
        "busy_count": len(busy),
        "duration_minutes": duration,
        "source": "stored_account_calendar",
        "external_sync_verified": False,
        "writes_performed": False,
        "all_events_protected": True,
    }
