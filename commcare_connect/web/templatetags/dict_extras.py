from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """
    Template filter to look up a value in a dictionary.
    Usage: {{ dict|lookup:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''


@register.filter
def get_item(dictionary, key):
    """
    Alternative name for lookup filter.
    Usage: {{ dict|get_item:key }}
    """
    return lookup(dictionary, key)
