import datetime

from django.utils.timezone import now


def is_date_before(date: datetime.datetime, days: int):
    before_date = now() - datetime.timedelta(days=days)
    return date.date() == before_date.date()
