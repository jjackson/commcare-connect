from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def gtm_var(name, value):
    """
    Renders a hidden element with data-name and data-value
    for JavaScript to pick up later.
    """
    if value is None:
        value = ""
    html = f'<div data-name="{escape(name)}" data-value="{escape(value)}"></div>'
    return mark_safe(html)
