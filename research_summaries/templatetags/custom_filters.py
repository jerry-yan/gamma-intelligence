from django import template

register = template.Library()

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces"""
    return value.replace('_', ' ')