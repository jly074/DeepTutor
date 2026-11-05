"""Synthetic account calendar reads, never external provider access."""

from tests.api.test_calendar import client as client
from tests.api.test_calendar import event, h
from tests.multi_user.conftest import mu_isolated_root as mu_isolated_root


def read(client, **params):
    return client.get(
        "/api/calendar/availability", headers=h(), params={"day": "2026-10-17", **params}
    )


def test_empty_is_explicitly_local_and_readonly(client):
    assert client.get("/api/calendar/availability?day=2026-10-17").status_code == 401
    data = read(client).json()
    assert data["free"] == [{"start": "2026-10-17T01:00:00Z", "end": "2026-10-17T10:00:00Z"}]
    assert data["external_sync_verified"] is False and data["writes_performed"] is False


def test_overlap_hidden_and_touching_events_preserved(client):
    cal = client.post(
        "/api/calendar/calendars",
        headers=h(),
        json={"name": "Synthetic hidden", "color": "#112233"},
    ).json()["calendar"]["id"]
    client.patch("/api/calendar/calendars/" + cal, headers=h(), json={"visible": False})
    for start, end in [("01:00", "02:00"), ("01:30", "03:00"), ("03:00", "04:00")]:
        client.post(
            "/api/calendar/events",
            headers=h(),
            json=event(
                calendar_id=cal, start=f"2026-10-17T{start}:00Z", end=f"2026-10-17T{end}:00Z"
            ),
        )
    before = client.get(
        "/api/calendar/events",
        headers=h(),
        params={"start": "2026-10-17T00:00:00Z", "end": "2026-10-18T00:00:00Z"},
    ).json()
    data = read(client).json()
    assert data["busy_count"] == 3 and len(data["conflicts"]) == 1
    assert data["free"] == [{"start": "2026-10-17T04:00:00Z", "end": "2026-10-17T10:00:00Z"}]
    assert data["revision"] == before["revision"] and data["all_events_protected"]
    assert (
        client.get(
            "/api/calendar/events",
            headers=h(),
            params={"start": "2026-10-17T00:00:00Z", "end": "2026-10-18T00:00:00Z"},
        ).json()
        == before
    )
    other = client.get("/api/calendar/availability?day=2026-10-17", headers=h("bob")).json()
    assert other["busy_count"] == 0


def test_all_day_exclusive_end_and_recurrence(client):
    client.post(
        "/api/calendar/events",
        headers=h(),
        json=event(all_day=True, start="2026-10-17", end="2026-10-18"),
    )
    assert read(client).json()["free"] == []
    assert read(client, day="2026-10-18").json()["busy_count"] == 0
    client.post("/api/calendar/events", headers=h(), json=event(rrule="FREQ=DAILY;COUNT=3"))
    data = read(client, day="2026-10-19").json()
    assert data["busy_count"] == 1 and data["free"][0]["start"] == "2026-10-19T02:00:00Z"


def test_duration_invalid_window_and_dst_boundary(client):
    assert read(client, duration=541).json()["free"] == []
    assert read(client, day="bad").status_code == 400
    assert read(client, tz="Bad/Zone").status_code == 400
    assert read(client, start_minute=600, end_minute=540).status_code == 400
    assert read(client, duration=0).status_code == 422
    assert (
        read(client, day="2026-03-08", tz="America/New_York", start_minute=150).status_code == 400
    )
    assert read(client, day="2026-11-01", tz="America/New_York", start_minute=90).status_code == 400
    data = read(client, day="2026-03-08", tz="America/New_York").json()
    assert data["free"][0]["start"] == "2026-03-08T13:00:00Z"

