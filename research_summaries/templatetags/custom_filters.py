from django import template

register = template.Library()

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces"""
    return value.replace('_', ' ')


@register.filter
def can_iterate(value):
    """
    Check if a value can be iterated over like a list.
    Returns True for lists, tuples, sets, etc.
    Returns False for strings, numbers, None, and dicts.
    """
    # Exclude strings and dicts even though they're technically iterable
    if isinstance(value, (str, dict)) or value is None:
        return False

    # Check if it's iterable
    try:
        iter(value)
        return True
    except TypeError:
        return False