import datetime

from django.utils.timezone import now


def is_date_before(date, days: int):
    return date <= now() - datetime.timedelta(days=days)
