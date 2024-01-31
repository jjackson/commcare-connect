from django import template

register = template.Library()


@register.filter
def duration_minutes(td):
    total_seconds = int(td.total_seconds())
    minutes = total_seconds // 60

    return f"{minutes} minutes"
