"""The lab clock (utils/lab_time.py) is America/New_York, independent of the host."""

from datetime import date, datetime, timezone

from metazebrobot.utils import lab_time


class FrozenDatetime(datetime):
    """datetime whose now(tz) returns a fixed UTC instant converted to tz."""

    instant = datetime(2026, 7, 22, 0, 6, tzinfo=timezone.utc)  # 20:06 EDT on 07-21

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)


def test_lab_now_and_today_use_new_york(monkeypatch):
    monkeypatch.setattr(lab_time, "datetime", FrozenDatetime)
    assert lab_time.lab_today() == date(2026, 7, 21)
    now = lab_time.lab_now()
    assert (now.year, now.month, now.day, now.hour, now.minute) == (2026, 7, 21, 20, 6)
    assert now.tzinfo is None  # stored form: naive lab wall-clock


def test_lab_calendar_date_of_instants():
    assert lab_time.lab_calendar_date(datetime(2026, 7, 22, 0, 6, tzinfo=timezone.utc)) == date(2026, 7, 21)
    assert lab_time.lab_calendar_date(datetime(2026, 7, 22, 4, 0)) == date(2026, 7, 22)


def test_api_server_reexports_lab_time():
    from metazebrobot import api_server

    assert api_server.LAB_TIMEZONE is lab_time.LAB_TIMEZONE
    assert api_server.lab_calendar_date is lab_time.lab_calendar_date


def test_agarose_expiration_crosses_month_end(monkeypatch):
    """Was replace(day=day + n), which raised ValueError past month end."""
    from metazebrobot.models import agarose

    monkeypatch.setattr(agarose, "lab_now", lambda: datetime(2026, 1, 30, 9, 0))
    solution = agarose.AgaroseSolution.create_new(
        concentration=0.02, agarose_bottle_id="B1", fish_water_batch_id="FW1",
        volume_prepared_mL=50, expiration_days=60,
    )
    assert solution.date_prepared == "20260130"
    assert solution.storage.expiration == "20260331"
