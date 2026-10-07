"""Qt date/time defaults on the lab's clock (see utils/lab_time.py)."""

from PySide6.QtCore import QDate, QTime

from ..utils.lab_time import lab_now, lab_today


def lab_qdate() -> QDate:
    """Today's lab date, for QDateEdit defaults (instead of QDate.currentDate())."""
    today = lab_today()
    return QDate(today.year, today.month, today.day)


def lab_qtime() -> QTime:
    """The lab's current time, for QTimeEdit defaults (instead of QTime.currentTime())."""
    now = lab_now()
    return QTime(now.hour, now.minute, now.second)
